"""Unit tests for pipeline state models."""

from datetime import datetime

import pytest

from autonomous_software_factory.pipeline.models import (
    AuditIssue,
    AuditResult,
    AuditSeverity,
    ComplexityBucket,
    FeatureRequest,
    FireDrillResult,
    FireDrillStatus,
    IncidentReport,
    LoadTestResult,
    SpecificationBlueprint,
    VerificationResult,
)


class TestComplexityBucket:
    def test_all_values_exist(self) -> None:
        assert ComplexityBucket.NANO == "nano"
        assert ComplexityBucket.MICRO == "micro"
        assert ComplexityBucket.STANDARD == "standard"
        assert ComplexityBucket.COMPLEX == "complex"
        assert ComplexityBucket.CRITICAL == "critical"

    def test_bucket_from_string(self) -> None:
        assert ComplexityBucket("nano") == ComplexityBucket.NANO
        assert ComplexityBucket("critical") == ComplexityBucket.CRITICAL


class TestAuditResult:
    def test_empty_audit_passes(self) -> None:
        result = AuditResult()
        assert not result.is_blocking
        assert result.issue_count == 0
        assert result.severity == AuditSeverity.PASS

    def test_blocking_audit(self) -> None:
        result = AuditResult(
            issues=[AuditIssue(description="Missing auth", category="security")],
            severity=AuditSeverity.BLOCK,
        )
        assert result.is_blocking
        assert result.issue_count == 1

    def test_warning_audit_not_blocking(self) -> None:
        result = AuditResult(
            issues=[AuditIssue(description="Minor issue", category="style")],
            severity=AuditSeverity.WARN,
        )
        assert not result.is_blocking
        assert result.issue_count == 1

    def test_audit_issue_optional_fields(self) -> None:
        issue = AuditIssue(description="test", category="logic")
        assert issue.file_path is None
        assert issue.line_number is None

        issue_with_location = AuditIssue(
            description="test", category="logic", file_path="main.py", line_number=42
        )
        assert issue_with_location.file_path == "main.py"
        assert issue_with_location.line_number == 42


class TestVerificationResult:
    def test_default_not_verified(self) -> None:
        result = VerificationResult()
        assert not result.verified
        assert result.pass_rate == 0.0

    def test_full_pass_rate(self) -> None:
        result = VerificationResult(
            verified=True, properties_checked=10, properties_passed=10
        )
        assert result.pass_rate == 1.0

    def test_partial_pass_rate(self) -> None:
        result = VerificationResult(
            verified=False,
            properties_checked=10,
            properties_passed=7,
            counterexamples=["x=0 violates invariant"],
        )
        assert result.pass_rate == 0.7

    def test_zero_properties_checked(self) -> None:
        result = VerificationResult(properties_checked=0, properties_passed=0)
        assert result.pass_rate == 0.0


class TestLoadTestResult:
    def test_default_not_passed(self) -> None:
        result = LoadTestResult()
        assert not result.passed
        assert result.error_rate == 0.0

    def test_error_rate_calculation(self) -> None:
        result = LoadTestResult(
            passed=True, total_requests=1000, failed_requests=5
        )
        assert result.error_rate == 0.005

    def test_zero_requests_error_rate(self) -> None:
        result = LoadTestResult(total_requests=0, failed_requests=0)
        assert result.error_rate == 0.0


class TestFireDrillResult:
    def test_default_not_run(self) -> None:
        result = FireDrillResult()
        assert not result.passed
        assert result.status == FireDrillStatus.NOT_RUN

    def test_passed_drill(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            detection_time_seconds=60.0,
            revert_time_seconds=120.0,
        )
        assert result.passed
        assert result.detection_within_limit
        assert result.revert_within_limit

    def test_detection_exceeds_limit(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            detection_time_seconds=400.0,
            max_detection_seconds=300.0,
        )
        assert not result.detection_within_limit

    def test_revert_exceeds_limit(self) -> None:
        result = FireDrillResult(
            status=FireDrillStatus.PASSED,
            revert_time_seconds=700.0,
            max_revert_seconds=600.0,
        )
        assert not result.revert_within_limit


class TestIncidentReport:
    def test_resolution_time_with_revert(self) -> None:
        detected = datetime(2026, 1, 1, 2, 0, 0)
        reverted = datetime(2026, 1, 1, 2, 5, 0)
        report = IncidentReport(
            incident_id="inc_001",
            detected_at=detected,
            reverted_at=reverted,
            was_auto_reverted=True,
        )
        assert report.resolution_time_seconds == 300.0

    def test_resolution_time_without_revert(self) -> None:
        report = IncidentReport(
            incident_id="inc_002",
            detected_at=datetime(2026, 1, 1, 2, 0, 0),
        )
        assert report.resolution_time_seconds is None


class TestSpecificationBlueprint:
    def test_lock_produces_hash(self) -> None:
        bp = SpecificationBlueprint(
            title="Payment Service",
            description="Handle payments",
            entities=["Account", "Transaction"],
            business_rules=["Balance >= 0"],
        )
        spec_hash = bp.lock()
        assert len(spec_hash) == 12
        assert bp.is_locked
        assert bp.locked_at is not None
        assert bp.spec_hash == spec_hash

    def test_double_lock_raises(self) -> None:
        bp = SpecificationBlueprint(title="Test", description="Test")
        bp.lock()
        with pytest.raises(ValueError, match="already locked"):
            bp.lock()

    def test_integrity_verification_passes(self) -> None:
        bp = SpecificationBlueprint(
            title="Service",
            description="Desc",
            entities=["User"],
            business_rules=["Rule1"],
        )
        bp.lock()
        assert bp.verify_integrity()

    def test_integrity_verification_fails_on_modification(self) -> None:
        bp = SpecificationBlueprint(
            title="Service",
            description="Desc",
            entities=["User"],
            business_rules=["Rule1"],
        )
        bp.lock()
        bp.entities.append("Hacked")
        assert not bp.verify_integrity()

    def test_unlocked_blueprint_fails_verification(self) -> None:
        bp = SpecificationBlueprint(title="Test", description="Test")
        assert not bp.verify_integrity()

    def test_hash_deterministic(self) -> None:
        bp1 = SpecificationBlueprint(
            title="A", description="B", entities=["C"], business_rules=["D"]
        )
        bp2 = SpecificationBlueprint(
            title="A", description="B", entities=["C"], business_rules=["D"]
        )
        bp1.lock()
        bp2.lock()
        assert bp1.spec_hash == bp2.spec_hash


class TestFeatureRequest:
    def test_default_creation(self) -> None:
        fr = FeatureRequest(id="feat_001")
        assert fr.id == "feat_001"
        assert fr.complexity_bucket == ComplexityBucket.STANDARD
        assert fr.code_retry_count == 0
        assert fr.can_retry_code

    def test_retry_exhaustion(self) -> None:
        fr = FeatureRequest(id="feat_001", max_code_retries=3)
        assert fr.increment_retry()  # count=1, can still retry
        assert fr.increment_retry()  # count=2, can still retry
        assert not fr.increment_retry()  # count=3, limit reached
        assert not fr.can_retry_code

    def test_not_ready_for_deployment_blocking_audit(self) -> None:
        fr = FeatureRequest(id="feat_001")
        fr.hostile_audit_result = AuditResult(severity=AuditSeverity.BLOCK)
        assert not fr.is_ready_for_deployment

    def test_not_ready_without_fire_drill(self) -> None:
        fr = FeatureRequest(id="feat_001")
        fr.hostile_audit_result = AuditResult(severity=AuditSeverity.PASS)
        fr.load_test_result = LoadTestResult(passed=True)
        # fire drill not passed
        assert not fr.is_ready_for_deployment

    def test_not_ready_without_load_test(self) -> None:
        fr = FeatureRequest(id="feat_001")
        fr.hostile_audit_result = AuditResult(severity=AuditSeverity.PASS)
        fr.fire_drill_result = FireDrillResult(status=FireDrillStatus.PASSED)
        # load test not passed
        assert not fr.is_ready_for_deployment

    def test_ready_for_deployment(self) -> None:
        fr = FeatureRequest(id="feat_001")
        fr.hostile_audit_result = AuditResult(severity=AuditSeverity.PASS)
        fr.fire_drill_result = FireDrillResult(status=FireDrillStatus.PASSED)
        fr.load_test_result = LoadTestResult(passed=True)
        assert fr.is_ready_for_deployment
