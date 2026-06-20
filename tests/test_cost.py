"""Tests for cost tracking utilities."""

import pytest

from pipeline.shared.config import CostLimits
from pipeline.shared.cost import CostTracker
from pipeline.shared.retry import BudgetExceededError


def test_cost_tracker_records_calls() -> None:
    tracker = CostTracker(
        feature_id="feat_001",
        limits=CostLimits(
            max_inference_calls_per_feature=100,
            max_gpu_minutes_per_feature=1000.0,
            max_retries_global=10,
        ),
    )
    tracker.record_llm_call(
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        latency_seconds=2.0,
    )
    assert tracker.total_inference_calls == 1
    assert tracker.total_cost_usd == 0.01
    assert tracker.total_gpu_minutes == pytest.approx(2.0 / 60.0, rel=1e-2)


def test_cost_tracker_budget_exceeded() -> None:
    tracker = CostTracker(
        feature_id="feat_002",
        limits=CostLimits(
            max_inference_calls_per_feature=2,
            max_gpu_minutes_per_feature=1000.0,
            max_retries_global=10,
        ),
    )
    tracker.record_llm_call(
        model="m",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
        latency_seconds=1.0,
    )
    tracker.record_llm_call(
        model="m",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
        latency_seconds=1.0,
    )
    with pytest.raises(BudgetExceededError):
        tracker.check_budget()


def test_cost_tracker_retry_limit() -> None:
    tracker = CostTracker(
        feature_id="feat_003",
        limits=CostLimits(
            max_inference_calls_per_feature=100,
            max_gpu_minutes_per_feature=1000.0,
            max_retries_global=2,
        ),
    )
    tracker.record_retry()
    tracker.record_retry()
    with pytest.raises(BudgetExceededError):
        tracker.check_budget()


def test_cost_tracker_summary() -> None:
    tracker = CostTracker(
        feature_id="feat_004",
        limits=CostLimits(
            max_inference_calls_per_feature=100,
            max_gpu_minutes_per_feature=1000.0,
            max_retries_global=10,
        ),
    )
    tracker.record_llm_call(
        model="m",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.02,
        latency_seconds=3.0,
    )
    summary = tracker.get_summary()
    assert summary["feature_id"] == "feat_004"
    assert summary["total_inference_calls"] == 1
    assert summary["total_cost_usd"] == 0.02
