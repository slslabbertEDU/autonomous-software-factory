"""Unit tests for SRE agent thresholds and anomaly detection."""


from autonomous_software_factory.workers.sre.thresholds import (
    AnomalyDetectionResult,
    AnomalyType,
    MetricsSnapshot,
    RevertDecision,
    RevertThresholds,
    detect_anomaly,
)


class TestRevertThresholds:
    def test_default_thresholds(self) -> None:
        thresholds = RevertThresholds()
        assert thresholds.error_rate == 0.01
        assert thresholds.p99_latency_increase == 2.0
        assert thresholds.cpu_sustained == 0.90
        assert thresholds.memory_leak_rate == 0.05

    def test_valid_thresholds_pass_validation(self) -> None:
        thresholds = RevertThresholds()
        errors = thresholds.validate()
        assert errors == []

    def test_invalid_error_rate_zero(self) -> None:
        thresholds = RevertThresholds(error_rate=0.0)
        errors = thresholds.validate()
        assert any("error_rate" in e for e in errors)

    def test_invalid_error_rate_above_one(self) -> None:
        thresholds = RevertThresholds(error_rate=1.5)
        errors = thresholds.validate()
        assert any("error_rate" in e for e in errors)

    def test_invalid_latency_at_one(self) -> None:
        thresholds = RevertThresholds(p99_latency_increase=1.0)
        errors = thresholds.validate()
        assert any("p99_latency_increase" in e for e in errors)

    def test_invalid_cpu_zero(self) -> None:
        thresholds = RevertThresholds(cpu_sustained=0.0)
        errors = thresholds.validate()
        assert any("cpu_sustained" in e for e in errors)

    def test_invalid_memory_leak_rate(self) -> None:
        thresholds = RevertThresholds(memory_leak_rate=1.5)
        errors = thresholds.validate()
        assert any("memory_leak_rate" in e for e in errors)

    def test_multiple_validation_errors(self) -> None:
        thresholds = RevertThresholds(
            error_rate=0.0,
            p99_latency_increase=0.5,
            cpu_sustained=2.0,
            memory_leak_rate=-0.1,
        )
        errors = thresholds.validate()
        assert len(errors) == 4


class TestDetectAnomaly:
    def test_healthy_metrics_no_anomaly(self) -> None:
        snapshot = MetricsSnapshot(
            error_rate=0.001,
            p99_latency_ms=50.0,
            baseline_p99_latency_ms=45.0,
            cpu_utilization=0.5,
            memory_growth_rate=0.01,
        )
        result = detect_anomaly(snapshot, RevertThresholds())
        assert not result.anomaly_detected
        assert result.decision == RevertDecision.MONITOR
        assert result.severity_score == 0.0

    def test_error_rate_triggers_revert(self) -> None:
        snapshot = MetricsSnapshot(error_rate=0.05)
        result = detect_anomaly(snapshot, RevertThresholds(error_rate=0.01))
        assert result.anomaly_detected
        assert result.anomaly_type == AnomalyType.ERROR_RATE
        assert result.decision == RevertDecision.REVERT
        assert result.severity_score == 5.0

    def test_error_rate_exactly_at_threshold(self) -> None:
        snapshot = MetricsSnapshot(error_rate=0.01)
        result = detect_anomaly(snapshot, RevertThresholds(error_rate=0.01))
        assert result.anomaly_detected
        assert result.anomaly_type == AnomalyType.ERROR_RATE
        assert result.requires_revert

    def test_latency_spike_triggers_revert(self) -> None:
        snapshot = MetricsSnapshot(
            error_rate=0.001,
            p99_latency_ms=200.0,
            baseline_p99_latency_ms=50.0,
        )
        result = detect_anomaly(snapshot, RevertThresholds(p99_latency_increase=2.0))
        assert result.anomaly_detected
        assert result.anomaly_type == AnomalyType.LATENCY_SPIKE
        assert result.requires_revert
        assert result.severity_score == 4.0

    def test_latency_no_baseline_skips_check(self) -> None:
        snapshot = MetricsSnapshot(
            error_rate=0.001,
            p99_latency_ms=200.0,
            baseline_p99_latency_ms=0.0,
        )
        result = detect_anomaly(snapshot, RevertThresholds())
        assert not result.anomaly_detected

    def test_cpu_sustained_triggers_revert(self) -> None:
        snapshot = MetricsSnapshot(
            error_rate=0.001,
            p99_latency_ms=50.0,
            baseline_p99_latency_ms=45.0,
            cpu_utilization=0.95,
        )
        result = detect_anomaly(snapshot, RevertThresholds(cpu_sustained=0.90))
        assert result.anomaly_detected
        assert result.anomaly_type == AnomalyType.CPU_SUSTAINED
        assert result.requires_revert

    def test_memory_leak_triggers_revert(self) -> None:
        snapshot = MetricsSnapshot(
            error_rate=0.001,
            p99_latency_ms=50.0,
            baseline_p99_latency_ms=45.0,
            cpu_utilization=0.5,
            memory_growth_rate=0.10,
        )
        result = detect_anomaly(snapshot, RevertThresholds(memory_leak_rate=0.05))
        assert result.anomaly_detected
        assert result.anomaly_type == AnomalyType.MEMORY_LEAK
        assert result.requires_revert
        assert result.severity_score == 2.0

    def test_priority_error_rate_over_latency(self) -> None:
        """Error rate takes priority over latency spike."""
        snapshot = MetricsSnapshot(
            error_rate=0.05,
            p99_latency_ms=200.0,
            baseline_p99_latency_ms=50.0,
        )
        result = detect_anomaly(snapshot, RevertThresholds())
        assert result.anomaly_type == AnomalyType.ERROR_RATE

    def test_priority_latency_over_cpu(self) -> None:
        """Latency spike takes priority over CPU."""
        snapshot = MetricsSnapshot(
            error_rate=0.001,
            p99_latency_ms=200.0,
            baseline_p99_latency_ms=50.0,
            cpu_utilization=0.95,
        )
        result = detect_anomaly(snapshot, RevertThresholds())
        assert result.anomaly_type == AnomalyType.LATENCY_SPIKE

    def test_severity_capped_at_10(self) -> None:
        snapshot = MetricsSnapshot(error_rate=0.50)
        result = detect_anomaly(snapshot, RevertThresholds(error_rate=0.01))
        assert result.severity_score == 10.0


class TestAnomalyDetectionResult:
    def test_requires_revert(self) -> None:
        result = AnomalyDetectionResult(decision=RevertDecision.REVERT)
        assert result.requires_revert
        assert not result.requires_escalation

    def test_requires_escalation(self) -> None:
        result = AnomalyDetectionResult(decision=RevertDecision.ESCALATE)
        assert not result.requires_revert
        assert result.requires_escalation

    def test_monitor_no_action(self) -> None:
        result = AnomalyDetectionResult(decision=RevertDecision.MONITOR)
        assert not result.requires_revert
        assert not result.requires_escalation
