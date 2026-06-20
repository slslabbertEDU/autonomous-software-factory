"""Unit tests for cost circuit breaker and cost ledger."""

import pytest

from autonomous_software_factory.pipeline.cost_ledger import (
    CostCategory,
    CostLimitExceededError,
    CostLimits,
    FeatureCostLedger,
)


class TestCostLimits:
    def test_default_limits(self) -> None:
        limits = CostLimits()
        assert limits.max_inference_calls_per_feature == 50
        assert limits.max_gpu_minutes_per_feature == 120.0
        assert limits.max_retries_global == 3
        assert limits.max_total_cost_usd == 50.0

    def test_check_inference_calls_within_limit(self) -> None:
        limits = CostLimits(max_inference_calls_per_feature=10)
        assert limits.check_inference_calls(5)
        assert limits.check_inference_calls(10)

    def test_check_inference_calls_exceeds_limit(self) -> None:
        limits = CostLimits(max_inference_calls_per_feature=10)
        assert not limits.check_inference_calls(11)

    def test_check_gpu_minutes_within_limit(self) -> None:
        limits = CostLimits(max_gpu_minutes_per_feature=60.0)
        assert limits.check_gpu_minutes(59.9)

    def test_check_gpu_minutes_exceeds_limit(self) -> None:
        limits = CostLimits(max_gpu_minutes_per_feature=60.0)
        assert not limits.check_gpu_minutes(60.1)

    def test_check_retries_within_limit(self) -> None:
        limits = CostLimits(max_retries_global=3)
        assert limits.check_retries(3)

    def test_check_retries_exceeds_limit(self) -> None:
        limits = CostLimits(max_retries_global=3)
        assert not limits.check_retries(4)

    def test_check_total_cost_within_limit(self) -> None:
        limits = CostLimits(max_total_cost_usd=100.0)
        assert limits.check_total_cost(99.99)

    def test_check_total_cost_exceeds_limit(self) -> None:
        limits = CostLimits(max_total_cost_usd=100.0)
        assert not limits.check_total_cost(100.01)


class TestFeatureCostLedger:
    def test_initial_state(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        assert ledger.total_cost_usd == 0.0
        assert not ledger.is_tripped
        assert ledger.trip_reason is None
        assert ledger.inference_call_count == 0
        assert ledger.gpu_minutes_used == 0.0

    def test_record_cost(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.record_cost(CostCategory.INFERENCE, 1.50, "GPT call", agent="coder")
        assert ledger.total_cost_usd == 1.50
        assert len(ledger.entries) == 1
        assert ledger.entries[0].category == CostCategory.INFERENCE

    def test_record_multiple_costs(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.record_cost(CostCategory.INFERENCE, 1.0, "call 1")
        ledger.record_cost(CostCategory.GPU_COMPUTE, 2.0, "gpu time")
        ledger.record_cost(CostCategory.STORAGE, 0.5, "storage")
        assert ledger.total_cost_usd == 3.5

    def test_cost_limit_trips_breaker(self) -> None:
        ledger = FeatureCostLedger(
            feature_id="feat_001",
            limits=CostLimits(max_total_cost_usd=5.0),
        )
        ledger.record_cost(CostCategory.INFERENCE, 3.0, "call 1")
        with pytest.raises(CostLimitExceededError) as exc_info:
            ledger.record_cost(CostCategory.INFERENCE, 3.0, "call 2")
        assert exc_info.value.limit_name == "total_cost_usd"
        assert ledger.is_tripped

    def test_record_inference_call(self) -> None:
        ledger = FeatureCostLedger(
            feature_id="feat_001",
            limits=CostLimits(max_inference_calls_per_feature=3),
        )
        ledger.record_inference_call()
        ledger.record_inference_call()
        ledger.record_inference_call()
        assert ledger.inference_call_count == 3
        with pytest.raises(CostLimitExceededError) as exc_info:
            ledger.record_inference_call()
        assert "inference_calls" in exc_info.value.limit_name
        assert ledger.is_tripped

    def test_record_gpu_minutes(self) -> None:
        ledger = FeatureCostLedger(
            feature_id="feat_001",
            limits=CostLimits(max_gpu_minutes_per_feature=10.0),
        )
        ledger.record_gpu_minutes(5.0)
        ledger.record_gpu_minutes(4.0)
        assert ledger.gpu_minutes_used == 9.0
        with pytest.raises(CostLimitExceededError):
            ledger.record_gpu_minutes(2.0)
        assert ledger.is_tripped

    def test_record_retry(self) -> None:
        ledger = FeatureCostLedger(
            feature_id="feat_001",
            limits=CostLimits(max_retries_global=2),
        )
        ledger.record_retry()
        ledger.record_retry()
        assert ledger.global_retry_count == 2
        with pytest.raises(CostLimitExceededError):
            ledger.record_retry()
        assert ledger.is_tripped

    def test_cost_by_category(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.record_cost(CostCategory.INFERENCE, 1.0, "call 1")
        ledger.record_cost(CostCategory.INFERENCE, 2.0, "call 2")
        ledger.record_cost(CostCategory.GPU_COMPUTE, 5.0, "gpu")
        by_cat = ledger.cost_by_category()
        assert by_cat[CostCategory.INFERENCE] == 3.0
        assert by_cat[CostCategory.GPU_COMPUTE] == 5.0

    def test_cost_by_agent(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.record_cost(CostCategory.INFERENCE, 1.0, "call", agent="coder")
        ledger.record_cost(CostCategory.INFERENCE, 2.0, "call", agent="qa")
        ledger.record_cost(CostCategory.INFERENCE, 0.5, "call", agent="coder")
        by_agent = ledger.cost_by_agent()
        assert by_agent["coder"] == 1.5
        assert by_agent["qa"] == 2.0

    def test_cost_by_agent_unknown(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.record_cost(CostCategory.INFERENCE, 1.0, "call")
        by_agent = ledger.cost_by_agent()
        assert by_agent["unknown"] == 1.0

    def test_cost_limit_exceeded_message(self) -> None:
        exc = CostLimitExceededError("gpu_minutes", 130.5, 120.0)
        assert "gpu_minutes" in str(exc)
        assert "130.50" in str(exc)
        assert "120.00" in str(exc)
