"""Cost tracking and budget enforcement.

Shared across all agents to:
- Record inference calls and GPU time
- Enforce per-feature budget limits (circuit breaker)
- Generate cost summaries for the weekly report
- Trigger human escalation when budget exceeded
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.shared.config import CostLimits, get_config
from pipeline.shared.metrics import (
    cost_total_gauge,
    gpu_minutes_gauge,
    inference_calls_gauge,
)
from pipeline.shared.retry import CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    """Record of a single LLM inference call."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_seconds: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class CostTracker:
    """Per-feature cost tracker with circuit breaker enforcement.

    Used by all agents via the LLM client and Temporal activity wrappers.
    Ensures no single feature exceeds budget limits defined in config.
    """

    def __init__(
        self,
        feature_id: str,
        limits: CostLimits | None = None,
    ) -> None:
        self._feature_id = feature_id
        self._limits = limits or get_config().cost_limits
        self._calls: list[LLMCallRecord] = []
        self._gpu_minutes: float = 0.0
        self._retries: int = 0

        # Circuit breakers for each budget dimension
        self._inference_breaker = CircuitBreaker(
            name=f"inference_calls:{feature_id}",
            threshold=float(self._limits.max_inference_calls_per_feature),
        )
        self._gpu_breaker = CircuitBreaker(
            name=f"gpu_minutes:{feature_id}",
            threshold=self._limits.max_gpu_minutes_per_feature,
        )
        self._retry_breaker = CircuitBreaker(
            name=f"retries:{feature_id}",
            threshold=float(self._limits.max_retries_global),
        )

    @property
    def feature_id(self) -> str:
        return self._feature_id

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self._calls)

    @property
    def total_inference_calls(self) -> int:
        return len(self._calls)

    @property
    def total_gpu_minutes(self) -> float:
        return self._gpu_minutes

    @property
    def total_retries(self) -> int:
        return self._retries

    def check_budget(self) -> None:
        """Check all circuit breakers. Raises BudgetExceededError if tripped."""
        self._inference_breaker.check()
        self._gpu_breaker.check()
        self._retry_breaker.check()

    def record_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_seconds: float,
    ) -> None:
        """Record an LLM inference call and update circuit breakers."""
        record = LLMCallRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_seconds=latency_seconds,
        )
        self._calls.append(record)
        self._inference_breaker.record()

        # Estimate GPU minutes from latency
        gpu_min = latency_seconds / 60.0
        self._gpu_minutes += gpu_min
        self._gpu_breaker.record(gpu_min)

        # Update Prometheus gauges
        inference_calls_gauge.labels(feature_id=self._feature_id).set(
            self.total_inference_calls
        )
        gpu_minutes_gauge.labels(feature_id=self._feature_id).set(self._gpu_minutes)
        cost_total_gauge.labels(feature_id=self._feature_id).set(self.total_cost_usd)

        logger.debug(
            "LLM call recorded: feature=%s model=%s cost=$%.4f total=$%.4f",
            self._feature_id,
            model,
            cost_usd,
            self.total_cost_usd,
        )

    def record_retry(self) -> None:
        """Record a retry attempt."""
        self._retries += 1
        self._retry_breaker.record()

    def get_summary(self) -> dict[str, float | int | str]:
        """Generate cost summary for reporting."""
        return {
            "feature_id": self._feature_id,
            "total_inference_calls": self.total_inference_calls,
            "total_gpu_minutes": round(self._gpu_minutes, 2),
            "total_retries": self._retries,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "avg_latency_seconds": round(
                (sum(c.latency_seconds for c in self._calls) / len(self._calls))
                if self._calls
                else 0.0,
                2,
            ),
        }
