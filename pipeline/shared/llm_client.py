"""Unified LLM client for vLLM OpenAI-compatible endpoints.

Both the Coder Agent and QA Agent (hostile audit) call vLLM endpoints.
This module provides a single client with:
- Configurable model routing (primary coder model vs. reasoning model)
- Token budget enforcement
- Cost tracking integration
- Structured output parsing
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from openai import AsyncOpenAI
from pydantic import BaseModel

from pipeline.shared.config import LLMConfig, get_config
from pipeline.shared.cost import CostTracker
from pipeline.shared.metrics import llm_call_counter, llm_latency_histogram


class ModelRole(str, Enum):
    """Which model to route to."""

    CODER = "coder"
    REASONING = "reasoning"


@dataclass(frozen=True)
class LLMResponse:
    """Standardized response from an LLM call."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    cost_usd: float


class LLMClient:
    """Unified client for all LLM interactions in the pipeline.

    Provides a single interface used by:
    - Coder Agent: code generation (primary model)
    - QA Agent: hostile audit (reasoning model)
    - Intake Agent: domain research and spec generation (primary model)
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self._config = config or get_config().llm
        self._cost_tracker = cost_tracker
        self._clients: dict[ModelRole, AsyncOpenAI] = {}

    def _get_client(self, role: ModelRole) -> AsyncOpenAI:
        if role not in self._clients:
            if role == ModelRole.CODER:
                base_url = self._config.coder_endpoint
                api_key = self._config.coder_api_key
            else:
                base_url = self._config.reasoning_endpoint
                api_key = self._config.reasoning_api_key
            self._clients[role] = AsyncOpenAI(base_url=base_url, api_key=api_key)
        return self._clients[role]

    def _get_model_name(self, role: ModelRole) -> str:
        if role == ModelRole.CODER:
            return self._config.coder_model
        return self._config.reasoning_model

    async def complete(
        self,
        messages: list[dict[str, str]],
        role: ModelRole = ModelRole.CODER,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        """Send a completion request to the appropriate model.

        Args:
            messages: Chat messages in OpenAI format.
            role: Which model to use (coder or reasoning).
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.
            stop: Stop sequences.

        Returns:
            Standardized LLMResponse with content and usage metadata.
        """
        client = self._get_client(role)
        model = self._get_model_name(role)
        max_tokens = max_tokens or self._config.default_max_tokens

        start = time.monotonic()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )
        latency = time.monotonic() - start

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = prompt_tokens + completion_tokens

        cost = self._estimate_cost(role, prompt_tokens, completion_tokens)

        llm_call_counter.labels(model=model, role=role.value).inc()
        llm_latency_histogram.labels(model=model, role=role.value).observe(latency)

        if self._cost_tracker:
            self._cost_tracker.record_llm_call(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
                latency_seconds=latency,
            )

        content = response.choices[0].message.content or ""
        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=latency,
            cost_usd=cost,
        )

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        role: ModelRole = ModelRole.CODER,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, LLMResponse]:
        """Complete and parse the response as a Pydantic model.

        Used by hostile audit (JSON output) and spec generation.
        """
        response = await self.complete(
            messages=messages,
            role=role,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        parsed = response_model.model_validate_json(
            self._extract_json(response.content)
        )
        return parsed, response

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from model output that may include markdown fences."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _estimate_cost(
        self, role: ModelRole, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Estimate cost based on model pricing (self-hosted GPU minutes)."""
        if role == ModelRole.CODER:
            rate = self._config.coder_cost_per_1k_tokens
        else:
            rate = self._config.reasoning_cost_per_1k_tokens
        total_tokens = prompt_tokens + completion_tokens
        return (total_tokens / 1000.0) * rate


def build_prompt_with_context(
    system_prompt: str,
    user_content: str,
    context_files: list[dict[str, str]] | None = None,
    dependency_constraint: str | None = None,
) -> list[dict[str, str]]:
    """Build a standardized prompt with context injection.

    This pattern is shared across:
    - Coder Agent (code generation with file context)
    - QA Agent hostile audit (spec + diff context)
    - Intake Agent (domain research context)

    Args:
        system_prompt: The agent's system-level instructions.
        user_content: The main user/task content.
        context_files: Optional list of {"path": ..., "content": ...} dicts.
        dependency_constraint: Optional dependency manifest constraint text.

    Returns:
        Messages list ready for LLMClient.complete().
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    context_parts: list[str] = []
    if context_files:
        for f in context_files:
            context_parts.append(f"### {f['path']}\n```\n{f['content']}\n```")

    if dependency_constraint:
        context_parts.append(
            f"DEPENDENCY CONSTRAINTS — NON-NEGOTIABLE:\n{dependency_constraint}"
        )

    if context_parts:
        context_block = "\n\n".join(context_parts)
        messages.append({"role": "user", "content": f"CONTEXT:\n{context_block}"})

    messages.append({"role": "user", "content": user_content})
    return messages


def estimate_token_count(text: str) -> int:
    """Rough token estimate (4 chars per token heuristic).

    Used for context budget enforcement before sending to model.
    """
    return len(text) // 4
