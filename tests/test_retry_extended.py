"""Extended tests for pipeline/shared/retry.py."""

import time
from unittest.mock import AsyncMock

import pytest

from pipeline.shared.retry import (
    BudgetExceededError,
    CircuitBreaker,
    CircuitState,
    RetryConfig,
    retry_async,
)


class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open_after_timeout(self) -> None:
        breaker = CircuitBreaker(
            name="test",
            threshold=1.0,
            reset_timeout_seconds=0.01,
        )
        breaker.record(1.0)  # Trip it
        assert breaker.state == CircuitState.OPEN
        time.sleep(0.02)  # Wait past reset timeout
        assert breaker.state == CircuitState.HALF_OPEN

    def test_stays_open_before_timeout(self) -> None:
        breaker = CircuitBreaker(
            name="test",
            threshold=1.0,
            reset_timeout_seconds=100.0,
        )
        breaker.record(1.0)  # Trip it
        assert breaker.state == CircuitState.OPEN

    def test_reset_from_open(self) -> None:
        breaker = CircuitBreaker(name="test", threshold=5.0)
        breaker.record(5.0)
        assert breaker.is_open
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert not breaker.is_open


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self) -> None:
        func = AsyncMock(return_value="success")
        result = await retry_async(func, config=RetryConfig(max_attempts=3))
        assert result == "success"
        func.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self) -> None:
        func = AsyncMock(side_effect=[Exception("fail"), Exception("fail"), "ok"])
        config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(Exception,),
        )
        result = await retry_async(func, config=config)
        assert result == "ok"
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_all_attempts(self) -> None:
        func = AsyncMock(side_effect=ValueError("always fails"))
        config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(ValueError,),
        )
        with pytest.raises(ValueError, match="always fails"):
            await retry_async(func, config=config)
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks(self) -> None:
        func = AsyncMock(return_value="result")
        breaker = CircuitBreaker(name="test", threshold=1.0)
        breaker.record(1.0)  # Trip it

        with pytest.raises(BudgetExceededError):
            await retry_async(func, circuit_breaker=breaker)
        func.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_on_retry(self) -> None:
        """Circuit breaker records after each failed attempt."""
        func = AsyncMock(side_effect=[Exception("fail"), "ok"])
        breaker = CircuitBreaker(
            name="test", threshold=10.0, reset_timeout_seconds=0.01
        )
        # Ensure half_open so check() passes
        time.sleep(0.02)

        config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(Exception,),
        )
        result = await retry_async(func, config=config, circuit_breaker=breaker)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_exponential_backoff_capped(self) -> None:
        """Verify delay is capped at max_delay_seconds."""
        call_times: list[float] = []

        async def slow_fail(**kwargs: object) -> str:
            call_times.append(time.monotonic())
            raise ConnectionError("down")

        config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.01,
            max_delay_seconds=0.02,
            exponential_base=10.0,
            retryable_exceptions=(ConnectionError,),
        )

        with pytest.raises(ConnectionError):
            await retry_async(slow_fail, config=config)

        assert len(call_times) == 3
        # Second delay should be capped at max (0.02s), not 0.01 * 10 = 0.1s
        gap = call_times[2] - call_times[1]
        assert gap < 0.05  # Should be ~0.02s, definitely not 0.1s

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_caught(self) -> None:
        """Non-retryable exceptions are not caught by retry logic."""
        func = AsyncMock(side_effect=TypeError("not retryable"))
        config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(ValueError,),  # Only ValueError is retryable
        )
        with pytest.raises(TypeError, match="not retryable"):
            await retry_async(func, config=config)
        func.assert_called_once()  # Not retried


class TestRetryConfig:
    def test_defaults(self) -> None:
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay_seconds == 1.0
        assert config.max_delay_seconds == 60.0
        assert config.exponential_base == 2.0


class TestBudgetExceededError:
    def test_attributes(self) -> None:
        exc = BudgetExceededError("gpu_minutes", 150.0, 120.0)
        assert exc.resource == "gpu_minutes"
        assert exc.current == 150.0
        assert exc.limit == 120.0
        assert "gpu_minutes" in str(exc)
        assert "150.00" in str(exc)
        assert "120.00" in str(exc)
