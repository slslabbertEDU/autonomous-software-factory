"""Unit tests for pipeline/shared/temporal_helpers.py — 0% coverage prior."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from pipeline.shared.models import ComplexityBucket, FeatureRequest
from pipeline.shared.retry import BudgetExceededError
from pipeline.shared.temporal_helpers import (
    EscalationRequiredError,
    classify_error,
    get_activity_timeout,
    get_heartbeat_interval,
    heartbeat_loop,
    tracked_activity,
)


class TestGetActivityTimeout:
    def test_nano_timeout(self) -> None:
        timeout = get_activity_timeout(ComplexityBucket.NANO)
        assert timeout == timedelta(hours=4)

    def test_micro_timeout(self) -> None:
        timeout = get_activity_timeout(ComplexityBucket.MICRO)
        assert timeout == timedelta(hours=8)

    def test_standard_timeout(self) -> None:
        timeout = get_activity_timeout(ComplexityBucket.STANDARD)
        assert timeout == timedelta(hours=16)

    def test_complex_timeout(self) -> None:
        timeout = get_activity_timeout(ComplexityBucket.COMPLEX)
        assert timeout == timedelta(hours=24)

    def test_critical_timeout(self) -> None:
        timeout = get_activity_timeout(ComplexityBucket.CRITICAL)
        assert timeout == timedelta(hours=48)


class TestGetHeartbeatInterval:
    def test_is_one_tenth_of_timeout(self) -> None:
        interval = get_heartbeat_interval(ComplexityBucket.STANDARD)
        timeout = get_activity_timeout(ComplexityBucket.STANDARD)
        assert interval == timedelta(seconds=timeout.total_seconds() / 10)

    def test_nano_interval(self) -> None:
        interval = get_heartbeat_interval(ComplexityBucket.NANO)
        # 4 hours / 10 = 24 minutes
        assert interval == timedelta(minutes=24)


class TestEscalationRequiredError:
    def test_creation(self) -> None:
        exc = EscalationRequiredError(reason="Budget exceeded", feature_id="feat_001")
        assert exc.reason == "Budget exceeded"
        assert exc.feature_id == "feat_001"
        assert "feat_001" in str(exc)
        assert "Budget exceeded" in str(exc)


class TestClassifyError:
    def test_budget_exceeded_escalates(self) -> None:
        exc = BudgetExceededError("gpu", 150.0, 120.0)
        assert classify_error(exc) == "escalate"

    def test_escalation_required_escalates(self) -> None:
        exc = EscalationRequiredError("reason", "feat_001")
        assert classify_error(exc) == "escalate"

    def test_connection_error_retries(self) -> None:
        exc = ConnectionError("connection refused")
        assert classify_error(exc) == "retry"

    def test_timeout_error_retries(self) -> None:
        exc = TimeoutError("timed out")
        assert classify_error(exc) == "retry"

    def test_os_error_retries(self) -> None:
        exc = OSError("network unreachable")
        assert classify_error(exc) == "retry"

    def test_unknown_error_is_fatal(self) -> None:
        exc = ValueError("unexpected")
        assert classify_error(exc) == "fatal"

    def test_runtime_error_is_fatal(self) -> None:
        exc = RuntimeError("crash")
        assert classify_error(exc) == "fatal"


class TestHeartbeatLoop:
    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.activity")
    async def test_heartbeat_sends(self, mock_activity: MagicMock) -> None:
        mock_activity.heartbeat = MagicMock()
        await heartbeat_loop(timedelta(seconds=10), details="working")
        mock_activity.heartbeat.assert_called_once_with("working")

    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.activity")
    async def test_heartbeat_empty_details(self, mock_activity: MagicMock) -> None:
        mock_activity.heartbeat = MagicMock()
        await heartbeat_loop(timedelta(seconds=5))
        mock_activity.heartbeat.assert_called_once_with("")


class TestTrackedActivity:
    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.get_config")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_duration")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_status")
    async def test_successful_activity(
        self,
        mock_status: MagicMock,
        mock_duration: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        mock_config = MagicMock()
        mock_config.cost_limits = MagicMock()
        mock_get_config.return_value = mock_config

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.check_budget = MagicMock()

        feature = FeatureRequest(id="feat_001")

        @tracked_activity("test_stage")
        async def my_activity(f: FeatureRequest) -> FeatureRequest:
            return f

        ct = "pipeline.shared.temporal_helpers.CostTracker"
        with patch(ct, return_value=mock_cost_tracker):
            result = await my_activity(feature)

        assert result.id == "feat_001"
        mock_duration.labels.assert_called()
        mock_status.labels.assert_called()

    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.get_config")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_duration")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_status")
    async def test_budget_exceeded_escalates(
        self,
        mock_status: MagicMock,
        mock_duration: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        mock_config = MagicMock()
        mock_config.cost_limits = MagicMock()
        mock_get_config.return_value = mock_config

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.check_budget.side_effect = BudgetExceededError(
            "inference", 55.0, 50.0
        )

        feature = FeatureRequest(id="feat_002")

        @tracked_activity("test_stage")
        async def my_activity(f: FeatureRequest) -> FeatureRequest:
            return f

        ct = "pipeline.shared.temporal_helpers.CostTracker"
        with (
            patch(ct, return_value=mock_cost_tracker),
            pytest.raises(EscalationRequiredError),
        ):
            await my_activity(feature)

    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.get_config")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_duration")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_status")
    async def test_general_exception_propagates(
        self,
        mock_status: MagicMock,
        mock_duration: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        mock_config = MagicMock()
        mock_config.cost_limits = MagicMock()
        mock_get_config.return_value = mock_config

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.check_budget = MagicMock()

        feature = FeatureRequest(id="feat_003")

        @tracked_activity("test_stage")
        async def my_activity(f: FeatureRequest) -> FeatureRequest:
            raise RuntimeError("something broke")

        ct = "pipeline.shared.temporal_helpers.CostTracker"
        with (
            patch(ct, return_value=mock_cost_tracker),
            pytest.raises(RuntimeError, match="something broke"),
        ):
            await my_activity(feature)

    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.get_config")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_duration")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_status")
    async def test_no_feature_in_args(
        self,
        mock_status: MagicMock,
        mock_duration: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        """When no FeatureRequest in args, should still work (no cost check)."""

        @tracked_activity("test_stage")
        async def my_activity(value: int) -> FeatureRequest:
            return FeatureRequest(id=f"feat_{value}")

        result = await my_activity(42)
        assert result.id == "feat_42"

    @pytest.mark.asyncio
    @patch("pipeline.shared.temporal_helpers.get_config")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_duration")
    @patch("pipeline.shared.temporal_helpers.pipeline_stage_status")
    async def test_feature_in_kwargs(
        self,
        mock_status: MagicMock,
        mock_duration: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        mock_config = MagicMock()
        mock_config.cost_limits = MagicMock()
        mock_get_config.return_value = mock_config

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.check_budget = MagicMock()

        feature = FeatureRequest(id="feat_kwarg")

        @tracked_activity("test_stage")
        async def my_activity(f: FeatureRequest) -> FeatureRequest:
            return f

        ct = "pipeline.shared.temporal_helpers.CostTracker"
        with patch(ct, return_value=mock_cost_tracker):
            result = await my_activity(f=feature)

        assert result.id == "feat_kwarg"
