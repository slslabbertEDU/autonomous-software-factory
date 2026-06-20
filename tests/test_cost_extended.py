"""Extended tests for pipeline/shared/cost.py — covers lines 73, 89 and record_retry."""

from unittest.mock import MagicMock, patch

from pipeline.shared.cost import CostTracker, LLMCallRecord


class TestCostTrackerProperties:
    @patch("pipeline.shared.cost.get_config")
    def test_feature_id_property(self, mock_config: MagicMock) -> None:
        mock_limits = MagicMock()
        mock_limits.max_inference_calls_per_feature = 50
        mock_limits.max_gpu_minutes_per_feature = 120.0
        mock_limits.max_retries_global = 3
        mock_config.return_value.cost_limits = mock_limits

        tracker = CostTracker(feature_id="feat_abc")
        assert tracker.feature_id == "feat_abc"

    @patch("pipeline.shared.cost.get_config")
    def test_total_retries_property(self, mock_config: MagicMock) -> None:
        mock_limits = MagicMock()
        mock_limits.max_inference_calls_per_feature = 50
        mock_limits.max_gpu_minutes_per_feature = 120.0
        mock_limits.max_retries_global = 10
        mock_config.return_value.cost_limits = mock_limits

        tracker = CostTracker(feature_id="feat_xyz")
        assert tracker.total_retries == 0
        tracker.record_retry()
        assert tracker.total_retries == 1
        tracker.record_retry()
        assert tracker.total_retries == 2

    @patch("pipeline.shared.cost.get_config")
    def test_get_summary(self, mock_config: MagicMock) -> None:
        mock_limits = MagicMock()
        mock_limits.max_inference_calls_per_feature = 50
        mock_limits.max_gpu_minutes_per_feature = 120.0
        mock_limits.max_retries_global = 10
        mock_config.return_value.cost_limits = mock_limits

        tracker = CostTracker(feature_id="feat_sum")
        tracker.record_llm_call(
            model="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            latency_seconds=2.0,
        )
        summary = tracker.get_summary()
        assert summary["feature_id"] == "feat_sum"
        assert summary["total_inference_calls"] == 1
        assert summary["total_retries"] == 0
        assert summary["total_cost_usd"] == 0.01

    @patch("pipeline.shared.cost.get_config")
    def test_get_summary_empty(self, mock_config: MagicMock) -> None:
        mock_limits = MagicMock()
        mock_limits.max_inference_calls_per_feature = 50
        mock_limits.max_gpu_minutes_per_feature = 120.0
        mock_limits.max_retries_global = 10
        mock_config.return_value.cost_limits = mock_limits

        tracker = CostTracker(feature_id="feat_empty")
        summary = tracker.get_summary()
        assert summary["avg_latency_seconds"] == 0.0


class TestLLMCallRecord:
    def test_creation(self) -> None:
        record = LLMCallRecord(
            model="qwen3",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            latency_seconds=1.5,
        )
        assert record.model == "qwen3"
        assert record.prompt_tokens == 100
        assert record.timestamp is not None
