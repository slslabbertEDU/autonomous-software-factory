"""Tests for retry and circuit breaker utilities."""

import pytest

from pipeline.shared.retry import (
    BudgetExceededError,
    CircuitBreaker,
    CircuitState,
    RetryConfig,
    retry_async,
)


def test_circuit_breaker_starts_closed() -> None:
    cb = CircuitBreaker(name="test", threshold=5.0)
    assert cb.state == CircuitState.CLOSED
    assert not cb.is_open


def test_circuit_breaker_trips_on_threshold() -> None:
    cb = CircuitBreaker(name="test", threshold=3.0)
    cb.record(1.0)
    cb.record(1.0)
    assert not cb.is_open
    cb.record(1.0)
    assert cb.is_open


def test_circuit_breaker_check_raises_when_open() -> None:
    cb = CircuitBreaker(name="test", threshold=1.0)
    cb.record(2.0)
    with pytest.raises(BudgetExceededError) as exc_info:
        cb.check()
    assert exc_info.value.resource == "test"
    assert exc_info.value.current == 2.0
    assert exc_info.value.limit == 1.0


def test_circuit_breaker_reset() -> None:
    cb = CircuitBreaker(name="test", threshold=2.0)
    cb.record(3.0)
    assert cb.is_open
    cb.reset()
    assert not cb.is_open


@pytest.mark.asyncio
async def test_retry_async_succeeds_first_try() -> None:
    call_count = 0

    async def success() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(success, config=RetryConfig(max_attempts=3))
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_retries_on_failure() -> None:
    call_count = 0

    async def fail_then_succeed() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient")
        return "ok"

    config = RetryConfig(
        max_attempts=3,
        base_delay_seconds=0.01,
        retryable_exceptions=(ConnectionError,),
    )
    result = await retry_async(fail_then_succeed, config=config)
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausts_attempts() -> None:
    async def always_fail() -> str:
        raise ValueError("permanent")

    config = RetryConfig(
        max_attempts=2,
        base_delay_seconds=0.01,
        retryable_exceptions=(ValueError,),
    )
    with pytest.raises(ValueError, match="permanent"):
        await retry_async(always_fail, config=config)


@pytest.mark.asyncio
async def test_retry_async_respects_circuit_breaker() -> None:
    cb = CircuitBreaker(name="test", threshold=1.0)
    cb.record(2.0)  # Trip it

    async def noop() -> str:
        return "should not reach"

    with pytest.raises(BudgetExceededError):
        await retry_async(noop, circuit_breaker=cb)
