"""Retry logic and circuit breaker patterns.

Shared across all agents for:
- LLM call retries (transient failures)
- Activity-level retries (with cost budget enforcement)
- Circuit breaker (stops runaway loops before budget exhaustion)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from pipeline.shared.metrics import (
    circuit_breaker_trips_counter,
    retry_counter,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Tripped, rejecting calls
    HALF_OPEN = "half_open"  # Testing recovery


class BudgetExceededError(Exception):
    """Raised when cost budget circuit breaker trips."""

    def __init__(self, resource: str, current: float, limit: float) -> None:
        self.resource = resource
        self.current = current
        self.limit = limit
        super().__init__(
            f"Budget exceeded for {resource}: {current:.2f} >= {limit:.2f}"
        )


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)


@dataclass
class CircuitBreaker:
    """Circuit breaker that trips when budget/threshold is exceeded.

    Used by:
    - Cost tracking (max inference calls, max GPU minutes)
    - SRE Agent (consecutive failure threshold)
    - Coder Agent (max retries per file)
    """

    name: str
    threshold: float
    reset_timeout_seconds: float = 300.0
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _current_value: float = field(default=0.0, init=False)
    _last_trip_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_trip_time
            if elapsed >= self.reset_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def record(self, value: float = 1.0) -> None:
        """Record a value and trip if threshold exceeded."""
        self._current_value += value
        if self._current_value >= self.threshold:
            self._trip()

    def reset(self) -> None:
        """Reset the circuit breaker."""
        self._state = CircuitState.CLOSED
        self._current_value = 0.0

    def check(self) -> None:
        """Raise if circuit is open."""
        if self.is_open:
            raise BudgetExceededError(self.name, self._current_value, self.threshold)

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._last_trip_time = time.monotonic()
        circuit_breaker_trips_counter.labels(breaker=self.name).inc()
        logger.warning(
            "Circuit breaker tripped: %s (value=%.2f, threshold=%.2f)",
            self.name,
            self._current_value,
            self.threshold,
        )


_DEFAULT_RETRY_CONFIG = RetryConfig()


async def retry_async(
    func: Callable[..., Awaitable[T]],
    config: RetryConfig = _DEFAULT_RETRY_CONFIG,
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs: Any,
) -> T:
    """Execute an async function with retry logic and optional circuit breaker.

    Shared pattern used across all agents for:
    - LLM API calls (transient network errors)
    - File-level code generation retries
    - Deployment health checks

    Args:
        func: Async callable to execute.
        config: Retry configuration.
        circuit_breaker: Optional circuit breaker to check before each attempt.
        **kwargs: Arguments passed to func.

    Returns:
        Result of the successful function call.

    Raises:
        BudgetExceededError: If circuit breaker is tripped.
        Exception: The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        if circuit_breaker:
            circuit_breaker.check()

        try:
            result = await func(**kwargs)
            return result
        except config.retryable_exceptions as exc:
            last_exception = exc
            retry_counter.labels(operation=func.__name__, attempt=str(attempt)).inc()

            if attempt == config.max_attempts:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    config.max_attempts,
                    func.__name__,
                    exc,
                )
                break

            delay = min(
                config.base_delay_seconds * (config.exponential_base ** (attempt - 1)),
                config.max_delay_seconds,
            )
            logger.warning(
                "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                attempt,
                config.max_attempts,
                func.__name__,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

            if circuit_breaker:
                circuit_breaker.record()

    raise last_exception  # type: ignore[misc]
