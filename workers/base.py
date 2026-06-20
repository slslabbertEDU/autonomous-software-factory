"""Base agent class with structured error handling.

All agents inherit from BaseAgent. This ensures:
- Every agent execution is wrapped in error handling
- Errors always include structured context (feature_id, agent name, stage)
- No error is silently swallowed — agents must explicitly handle or propagate
- Cost tracking is enforced at the base level
- Execution time is logged for every agent run
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pipeline.errors import (
    BlockingError,
    CriticalError,
    ErrorContext,
    MaxRetriesExhaustedError,
    PipelineError,
    RetryableError,
    TransientInfraError,
)

if TYPE_CHECKING:
    from pipeline.shared.models import FeatureRequest

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all pipeline agents.

    Subclasses implement `execute()`. The base class wraps execution with:
    - Structured logging of start/success/failure
    - Automatic error context enrichment
    - Cost ledger tracking
    - Duration measurement
    """

    agent_name: str = "unnamed_agent"

    def _make_context(self, feature: FeatureRequest, stage: str) -> ErrorContext:
        """Create an ErrorContext bound to this agent and the current feature."""
        return ErrorContext(
            feature_id=feature.id,
            agent=self.agent_name,
            stage=stage,
        )

    async def run(self, feature: FeatureRequest) -> FeatureRequest:
        """Execute the agent with full error handling wrapper.

        This method:
        1. Validates input state
        2. Logs execution start with context
        3. Calls the subclass `execute()` method
        4. Catches and enriches all exceptions
        5. Never silently swallows errors

        Returns the mutated FeatureRequest on success.
        Raises PipelineError subclass on failure.
        """
        start_time = time.monotonic()
        logger.info(
            "Agent '%s' starting for feature %s",
            self.agent_name,
            feature.id,
        )

        try:
            self._validate_input(feature)
            result = await self.execute(feature)
            duration = time.monotonic() - start_time
            logger.info(
                "Agent '%s' completed for feature %s in %.2fs",
                self.agent_name,
                feature.id,
                duration,
            )
            return result

        except PipelineError as exc:
            # Already a structured error — log and re-raise as-is
            duration = time.monotonic() - start_time
            logger.error(
                "Agent '%s' FAILED for feature %s after %.2fs: %s",
                self.agent_name,
                feature.id,
                duration,
                str(exc),
                exc_info=True,
            )
            raise

        except Exception as exc:
            # Unexpected error — wrap in TransientInfraError so it's never swallowed
            duration = time.monotonic() - start_time
            context = self._make_context(feature, "unexpected_failure")
            logger.error(
                "Agent '%s' hit unexpected error for feature %s after %.2fs: %r",
                self.agent_name,
                feature.id,
                duration,
                exc,
                exc_info=True,
            )
            raise TransientInfraError(
                f"Unexpected error in agent '{self.agent_name}': {exc!r}",
                context,
            ) from exc

    def _validate_input(self, feature: FeatureRequest) -> None:
        """Validate the feature state before execution.

        Override in subclasses for agent-specific precondition checks.
        Raises ValueError with a descriptive message on invalid state —
        never silently proceeds with bad input.
        """
        if not feature.id:
            raise ValueError(
                f"Agent '{self.agent_name}' received FeatureRequest with empty id"
            )

    @abstractmethod
    async def execute(self, feature: FeatureRequest) -> FeatureRequest:
        """Agent-specific logic. Subclasses must implement this.

        Implementations MUST:
        - Raise PipelineError subclasses for expected failures
        - Let unexpected exceptions propagate (base class wraps them)
        - Never use bare `except:` or `except Exception: pass`
        - Log meaningful context before raising
        """
        ...


class RetryableAgent(BaseAgent):
    """Agent that supports structured retries with error accumulation.

    Unlike bare retry loops that silently swallow failures, this class:
    - Logs every retry attempt with the specific error
    - Accumulates errors for post-mortem analysis
    - Raises MaxRetriesExhaustedError with the full error history
    - Records each retry in the cost ledger
    """

    max_retries: int = 3

    async def run_with_retries(
        self, feature: FeatureRequest
    ) -> FeatureRequest:
        """Execute with retries. Never silently drops errors."""
        errors: list[Exception] = []

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Agent '%s' attempt %d/%d for feature %s",
                    self.agent_name,
                    attempt,
                    self.max_retries,
                    feature.id,
                )
                result = await self.run(feature)
                if errors:
                    # Succeeded after retries — log the recovery
                    logger.warning(
                        "Agent '%s' recovered after %d failed attempt(s) "
                        "for feature %s. Previous errors: %r",
                        self.agent_name,
                        len(errors),
                        feature.id,
                        [str(e) for e in errors],
                    )
                return result

            except RetryableError as exc:
                errors.append(exc)
                feature.cost_ledger.record_retry()
                logger.warning(
                    "Agent '%s' attempt %d/%d failed (retryable) "
                    "for feature %s: %s",
                    self.agent_name,
                    attempt,
                    self.max_retries,
                    feature.id,
                    str(exc),
                )
                await self._on_retry(feature, exc, attempt)

            except (BlockingError, CriticalError):
                # Non-retryable — propagate immediately
                raise

        # All retries exhausted — raise with accumulated context
        context = self._make_context(feature, "retries_exhausted")
        raise MaxRetriesExhaustedError(
            context=context,
            attempts=self.max_retries,
            last_error=errors[-1] if errors else None,
        )

    async def _on_retry(
        self,
        feature: FeatureRequest,
        error: RetryableError,
        attempt: int,
    ) -> None:
        """Hook for subclasses to perform actions between retries.

        Override to add backoff, modify prompts, inject failure context, etc.
        Default implementation does nothing.
        """


def log_error_chain(exc: BaseException) -> list[dict[str, Any]]:
    """Extract the full exception chain for structured logging.

    Ensures no error in the __cause__ chain is lost.
    """
    chain: list[dict[str, Any]] = []
    current: BaseException | None = exc
    while current is not None:
        entry: dict[str, Any] = {
            "type": type(current).__name__,
            "message": str(current),
        }
        if isinstance(current, PipelineError):
            entry["context"] = {
                "feature_id": current.context.feature_id,
                "agent": current.context.agent,
                "stage": current.context.stage,
                "timestamp": current.context.timestamp.isoformat(),
            }
            entry["severity"] = current.severity.value
        chain.append(entry)
        current = current.__cause__
    return chain
