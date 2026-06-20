"""Unit tests for fire drill (chaos engineering) gate."""


from autonomous_software_factory.pipeline.models import (
    ComplexityBucket,
    FireDrillResult,
    FireDrillStatus,
)
from autonomous_software_factory.workers.sre.fire_drill import (
    COMPLEXITY_FAULT_MAP,
    FaultType,
    FireDrillConfig,
    evaluate_fire_drill,
    get_fault_type_for_complexity,
)


class TestFaultTypeMapping:
    def test_nano_maps_to_kill_pod(self) -> None:
        assert get_fault_type_for_complexity(ComplexityBucket.NANO) == FaultType.KILL_POD

    def test_micro_maps_to_kill_pod(self) -> None:
        assert get_fault_type_for_complexity(ComplexityBucket.MICRO) == FaultType.KILL_POD

    def test_standard_maps_to_spike_cpu(self) -> None:
        assert get_fault_type_for_complexity(ComplexityBucket.STANDARD) == FaultType.SPIKE_CPU

    def test_complex_maps_to_block_database(self) -> None:
        assert get_fault_type_for_complexity(ComplexityBucket.COMPLEX) == FaultType.BLOCK_DATABASE

    def test_critical_maps_to_corrupt_header(self) -> None:
        assert (
            get_fault_type_for_complexity(ComplexityBucket.CRITICAL)
            == FaultType.CORRUPT_HEADER
        )

    def test_all_buckets_have_mapping(self) -> None:
        for bucket in ComplexityBucket:
            assert bucket in COMPLEXITY_FAULT_MAP


class TestEvaluateFireDrill:
    def test_not_run_fails(self) -> None:
        result = FireDrillResult(status=FireDrillStatus.NOT_RUN)
        evaluation = evaluate_fire_drill(result)
        assert not evaluation.passed
        assert not evaluation.can_promote
        assert "not been executed" in evaluation.failure_reasons[0]

    def test_passed_within_limits(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            fault_type="kill_pod",
            detection_time_seconds=100.0,
            revert_time_seconds=200.0,
        )
        evaluation = evaluate_fire_drill(result)
        assert evaluation.passed
        assert evaluation.can_promote
        assert evaluation.detection_passed
        assert evaluation.revert_passed
        assert evaluation.failure_reasons == []

    def test_failed_status(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.FAILED,
            fault_type="spike_cpu_to_95_percent",
            detection_time_seconds=100.0,
            revert_time_seconds=200.0,
        )
        evaluation = evaluate_fire_drill(result)
        assert not evaluation.passed
        assert not evaluation.can_promote
        assert any("failed" in r.lower() for r in evaluation.failure_reasons)

    def test_detection_time_exceeds_limit(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            detection_time_seconds=400.0,
            revert_time_seconds=200.0,
        )
        config = FireDrillConfig(max_detection_seconds=300.0)
        evaluation = evaluate_fire_drill(result, config)
        assert not evaluation.passed
        assert not evaluation.detection_passed
        assert evaluation.revert_passed

    def test_revert_time_exceeds_limit(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            detection_time_seconds=100.0,
            revert_time_seconds=700.0,
        )
        config = FireDrillConfig(max_revert_seconds=600.0)
        evaluation = evaluate_fire_drill(result, config)
        assert not evaluation.passed
        assert evaluation.detection_passed
        assert not evaluation.revert_passed

    def test_both_times_exceed_limits(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            detection_time_seconds=400.0,
            revert_time_seconds=700.0,
        )
        config = FireDrillConfig(max_detection_seconds=300.0, max_revert_seconds=600.0)
        evaluation = evaluate_fire_drill(result, config)
        assert not evaluation.passed
        assert len(evaluation.failure_reasons) == 2

    def test_disabled_config_always_passes(self) -> None:
        result = FireDrillResult(status=FireDrillStatus.NOT_RUN)
        config = FireDrillConfig(enabled=False)
        evaluation = evaluate_fire_drill(result, config)
        assert evaluation.passed
        assert evaluation.can_promote

    def test_unknown_fault_type_defaults(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            fault_type="unknown_fault",
            detection_time_seconds=100.0,
            revert_time_seconds=200.0,
        )
        evaluation = evaluate_fire_drill(result)
        assert evaluation.passed
        assert evaluation.fault_type == FaultType.KILL_POD


class TestFireDrillConfig:
    def test_default_config(self) -> None:
        config = FireDrillConfig()
        assert config.max_detection_seconds == 300.0
        assert config.max_revert_seconds == 600.0
        assert config.enabled

    def test_custom_config(self) -> None:
        config = FireDrillConfig(
            max_detection_seconds=60.0,
            max_revert_seconds=120.0,
            enabled=True,
        )
        assert config.max_detection_seconds == 60.0
        assert config.max_revert_seconds == 120.0
