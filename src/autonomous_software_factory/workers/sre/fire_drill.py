"""Fire drill (chaos engineering) gate for production promotion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autonomous_software_factory.pipeline.models import (
    ComplexityBucket,
    FireDrillResult,
    FireDrillStatus,
)


class FaultType(str, Enum):
    """Fault injection types mapped to complexity buckets."""

    KILL_POD = "kill_pod"
    SPIKE_CPU = "spike_cpu_to_95_percent"
    BLOCK_DATABASE = "block_database_port"
    CORRUPT_HEADER = "corrupt_single_response_header"


COMPLEXITY_FAULT_MAP: dict[ComplexityBucket, FaultType] = {
    ComplexityBucket.NANO: FaultType.KILL_POD,
    ComplexityBucket.MICRO: FaultType.KILL_POD,
    ComplexityBucket.STANDARD: FaultType.SPIKE_CPU,
    ComplexityBucket.COMPLEX: FaultType.BLOCK_DATABASE,
    ComplexityBucket.CRITICAL: FaultType.CORRUPT_HEADER,
}


@dataclass
class FireDrillConfig:
    """Configuration for fire drill execution."""

    max_detection_seconds: float = 300.0
    max_revert_seconds: float = 600.0
    enabled: bool = True


@dataclass
class FireDrillEvaluation:
    """Evaluation of whether a fire drill passed all criteria."""

    passed: bool
    fault_type: FaultType
    detection_passed: bool
    revert_passed: bool
    can_promote: bool
    failure_reasons: list[str]


def get_fault_type_for_complexity(bucket: ComplexityBucket) -> FaultType:
    """Determine the fault injection type based on feature complexity."""
    return COMPLEXITY_FAULT_MAP[bucket]


def evaluate_fire_drill(
    result: FireDrillResult,
    config: FireDrillConfig | None = None,
) -> FireDrillEvaluation:
    """Evaluate a fire drill result against configured limits.

    Returns an evaluation with pass/fail status and reasons.
    A failed fire drill means the feature MUST NOT be promoted to production.
    """
    if config is None:
        config = FireDrillConfig()

    failure_reasons: list[str] = []

    if not config.enabled:
        return FireDrillEvaluation(
            passed=True,
            fault_type=FaultType.KILL_POD,
            detection_passed=True,
            revert_passed=True,
            can_promote=True,
            failure_reasons=[],
        )

    if result.status == FireDrillStatus.NOT_RUN:
        return FireDrillEvaluation(
            passed=False,
            fault_type=FaultType.KILL_POD,
            detection_passed=False,
            revert_passed=False,
            can_promote=False,
            failure_reasons=["Fire drill has not been executed"],
        )

    if result.status == FireDrillStatus.FAILED:
        failure_reasons.append("Fire drill execution failed")

    detection_passed = result.detection_time_seconds <= config.max_detection_seconds
    if not detection_passed:
        failure_reasons.append(
            f"Detection time {result.detection_time_seconds:.1f}s exceeds "
            f"limit {config.max_detection_seconds:.1f}s"
        )

    revert_passed = result.revert_time_seconds <= config.max_revert_seconds
    if not revert_passed:
        failure_reasons.append(
            f"Revert time {result.revert_time_seconds:.1f}s exceeds "
            f"limit {config.max_revert_seconds:.1f}s"
        )

    overall_passed = (
        result.status == FireDrillStatus.PASSED
        and detection_passed
        and revert_passed
    )

    fault_type = FaultType.KILL_POD
    if result.fault_type:
        try:
            fault_type = FaultType(result.fault_type)
        except ValueError:
            pass

    return FireDrillEvaluation(
        passed=overall_passed,
        fault_type=fault_type,
        detection_passed=detection_passed,
        revert_passed=revert_passed,
        can_promote=overall_passed,
        failure_reasons=failure_reasons,
    )
