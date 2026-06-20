"""SRE Agent revert thresholds and anomaly detection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AnomalyType(str, Enum):
    """Types of anomalies the SRE agent detects."""

    ERROR_RATE = "error_rate"
    LATENCY_SPIKE = "latency_spike"
    CPU_SUSTAINED = "cpu_sustained"
    MEMORY_LEAK = "memory_leak"


class RevertDecision(str, Enum):
    """SRE agent revert decision outcome."""

    REVERT = "revert"
    MONITOR = "monitor"
    ESCALATE = "escalate"


@dataclass
class RevertThresholds:
    """Configurable thresholds that trigger automatic revert."""

    error_rate: float = 0.01
    p99_latency_increase: float = 2.0
    cpu_sustained: float = 0.90
    memory_leak_rate: float = 0.05

    def validate(self) -> list[str]:
        """Validate threshold values are within acceptable ranges."""
        errors: list[str] = []
        if not 0.0 < self.error_rate <= 1.0:
            errors.append(f"error_rate must be in (0, 1], got {self.error_rate}")
        if self.p99_latency_increase <= 1.0:
            errors.append(
                f"p99_latency_increase must be > 1.0, got {self.p99_latency_increase}"
            )
        if not 0.0 < self.cpu_sustained <= 1.0:
            errors.append(f"cpu_sustained must be in (0, 1], got {self.cpu_sustained}")
        if not 0.0 < self.memory_leak_rate <= 1.0:
            errors.append(
                f"memory_leak_rate must be in (0, 1], got {self.memory_leak_rate}"
            )
        return errors


@dataclass
class MetricsSnapshot:
    """Point-in-time metrics from production monitoring."""

    error_rate: float = 0.0
    p99_latency_ms: float = 0.0
    baseline_p99_latency_ms: float = 0.0
    cpu_utilization: float = 0.0
    memory_growth_rate: float = 0.0
    timestamp_epoch: float = 0.0


@dataclass
class AnomalyDetectionResult:
    """Result of analyzing a metrics snapshot against thresholds."""

    anomaly_detected: bool = False
    anomaly_type: AnomalyType | None = None
    decision: RevertDecision = RevertDecision.MONITOR
    severity_score: float = 0.0
    details: str = ""

    @property
    def requires_revert(self) -> bool:
        return self.decision == RevertDecision.REVERT

    @property
    def requires_escalation(self) -> bool:
        return self.decision == RevertDecision.ESCALATE


def detect_anomaly(
    snapshot: MetricsSnapshot,
    thresholds: RevertThresholds,
) -> AnomalyDetectionResult:
    """Analyze metrics snapshot against thresholds. Returns detection result.

    Priority order: error_rate > latency > CPU > memory leak.
    """
    if snapshot.error_rate >= thresholds.error_rate:
        severity = snapshot.error_rate / thresholds.error_rate
        return AnomalyDetectionResult(
            anomaly_detected=True,
            anomaly_type=AnomalyType.ERROR_RATE,
            decision=RevertDecision.REVERT,
            severity_score=min(severity, 10.0),
            details=(
                f"Error rate {snapshot.error_rate:.4f} exceeds "
                f"threshold {thresholds.error_rate:.4f}"
            ),
        )

    if snapshot.baseline_p99_latency_ms > 0:
        latency_ratio = snapshot.p99_latency_ms / snapshot.baseline_p99_latency_ms
        if latency_ratio >= thresholds.p99_latency_increase:
            return AnomalyDetectionResult(
                anomaly_detected=True,
                anomaly_type=AnomalyType.LATENCY_SPIKE,
                decision=RevertDecision.REVERT,
                severity_score=min(latency_ratio, 10.0),
                details=(
                    f"P99 latency {snapshot.p99_latency_ms:.1f}ms is "
                    f"{latency_ratio:.1f}x baseline {snapshot.baseline_p99_latency_ms:.1f}ms"
                ),
            )

    if snapshot.cpu_utilization >= thresholds.cpu_sustained:
        severity = snapshot.cpu_utilization / thresholds.cpu_sustained
        return AnomalyDetectionResult(
            anomaly_detected=True,
            anomaly_type=AnomalyType.CPU_SUSTAINED,
            decision=RevertDecision.REVERT,
            severity_score=min(severity, 10.0),
            details=(
                f"CPU utilization {snapshot.cpu_utilization:.2%} sustained above "
                f"threshold {thresholds.cpu_sustained:.2%}"
            ),
        )

    if snapshot.memory_growth_rate >= thresholds.memory_leak_rate:
        severity = snapshot.memory_growth_rate / thresholds.memory_leak_rate
        return AnomalyDetectionResult(
            anomaly_detected=True,
            anomaly_type=AnomalyType.MEMORY_LEAK,
            decision=RevertDecision.REVERT,
            severity_score=min(severity, 10.0),
            details=(
                f"Memory growth rate {snapshot.memory_growth_rate:.2%} exceeds "
                f"threshold {thresholds.memory_leak_rate:.2%}"
            ),
        )

    return AnomalyDetectionResult(
        anomaly_detected=False,
        decision=RevertDecision.MONITOR,
        severity_score=0.0,
        details="All metrics within normal thresholds",
    )
