"""Unit tests for pipeline/state.py — 0% coverage prior."""

from datetime import datetime

import pytest

from pipeline.state import (
    COMPLEXITY_BUCKETS,
    COST_LIMITS,
    AuditResult,
    BudgetExceeded,
    FeatureCostLedger,
    FeatureRequest,
    FireDrillResult,
    IncidentReport,
    LoadTestResult,
    SpecificationBlueprint,
    VerificationResult,
)


class TestComplexityBuckets:
    def test_all_buckets_defined(self) -> None:
        expected = {"nano", "micro", "standard", "complex", "critical"}
        assert set(COMPLEXITY_BUCKETS.keys()) == expected

    def test_each_bucket_has_required_keys(self) -> None:
        for name, bucket in COMPLEXITY_BUCKETS.items():
            assert "description" in bucket, f"{name} missing description"
            assert "target_hours" in bucket, f"{name} missing target_hours"
            assert "activity_timeout_minutes" in bucket, f"{name} missing timeout"

    def test_target_hours_increase_with_complexity(self) -> None:
        order = ["nano", "micro", "standard", "complex", "critical"]
        hours = [COMPLEXITY_BUCKETS[b]["target_hours"] for b in order]
        assert hours == sorted(hours)

    def test_timeout_increases_with_complexity(self) -> None:
        order = ["nano", "micro", "standard", "complex", "critical"]
        timeouts = [COMPLEXITY_BUCKETS[b]["activity_timeout_minutes"] for b in order]
        assert timeouts == sorted(timeouts)


class TestCostLimits:
    def test_limits_defined(self) -> None:
        assert COST_LIMITS["max_inference_calls_per_feature"] == 50
        assert COST_LIMITS["max_gpu_minutes_per_feature"] == 120
        assert COST_LIMITS["max_retries_global"] == 3


class TestSpecificationBlueprint:
    def _make_blueprint(self) -> SpecificationBlueprint:
        return SpecificationBlueprint(
            project_name="Test Project",
            one_line_description="A test project",
            core_entities=[{"name": "User", "fields": ["id", "email"]}],
            business_rules=[{"rule": "Users must have valid email"}],
            hidden_complexities=["Email validation edge cases"],
            tech_stack={"language": "python", "framework": "fastapi"},
            deployment_target="kubernetes",
            constraints={"max_latency_ms": "100"},
            integrations=[{"name": "stripe", "type": "payment"}],
            data_retention="90 days",
            expected_users=1000,
            availability_target="99.9%",
            offline_support=False,
        )

    def test_lock_assigns_hash(self) -> None:
        bp = self._make_blueprint()
        assert bp.spec_hash == ""
        assert not bp.is_locked
        bp.lock()
        assert bp.is_locked
        assert len(bp.spec_hash) == 12
        assert all(c in "0123456789abcdef" for c in bp.spec_hash)

    def test_lock_is_deterministic(self) -> None:
        bp1 = self._make_blueprint()
        bp2 = self._make_blueprint()
        bp1.lock()
        bp2.lock()
        assert bp1.spec_hash == bp2.spec_hash

    def test_lock_twice_raises(self) -> None:
        bp = self._make_blueprint()
        bp.lock()
        with pytest.raises(ValueError, match="already locked"):
            bp.lock()

    def test_different_content_different_hash(self) -> None:
        bp1 = self._make_blueprint()
        bp2 = self._make_blueprint()
        bp2.core_entities = [{"name": "Order", "fields": ["id", "total"]}]
        bp1.lock()
        bp2.lock()
        assert bp1.spec_hash != bp2.spec_hash

    def test_formal_specs_optional(self) -> None:
        bp = self._make_blueprint()
        assert bp.formal_specs is None
        bp.formal_specs = {"invariant": "balance >= 0"}
        assert bp.formal_specs is not None


class TestAuditResult:
    def test_creation(self) -> None:
        result = AuditResult(
            issues=[{"desc": "Missing auth check", "severity": "HIGH"}],
            severity="BLOCK",
            model_used="deepseek-r1",
            tokens_used=5000,
        )
        assert result.severity == "BLOCK"
        assert len(result.issues) == 1
        assert result.reasoning_trace is None

    def test_with_reasoning_trace(self) -> None:
        result = AuditResult(
            issues=[],
            severity="PASS",
            model_used="deepseek-r1",
            tokens_used=3000,
            reasoning_trace="No issues found after careful review.",
        )
        assert result.reasoning_trace is not None


class TestVerificationResult:
    def test_passing(self) -> None:
        result = VerificationResult(
            invariants_checked=10,
            invariants_proven=10,
            counterexamples=[],
            pass_rate=1.0,
            passed=True,
        )
        assert result.passed
        assert result.pass_rate == 1.0

    def test_failing_with_counterexamples(self) -> None:
        result = VerificationResult(
            invariants_checked=5,
            invariants_proven=3,
            counterexamples=[{"invariant": "balance >= 0", "input": "withdraw(100)"}],
            pass_rate=0.6,
            passed=False,
        )
        assert not result.passed
        assert len(result.counterexamples) == 1


class TestLoadTestResult:
    def test_passing(self) -> None:
        result = LoadTestResult(
            p99_latency_ms=45.0,
            error_rate=0.001,
            timeout_count=0,
            deadlock_count=0,
            peak_rps=1500.0,
            passed=True,
        )
        assert result.passed
        assert result.failure_reason is None

    def test_failing(self) -> None:
        result = LoadTestResult(
            p99_latency_ms=500.0,
            error_rate=0.05,
            timeout_count=10,
            deadlock_count=2,
            peak_rps=500.0,
            passed=False,
            failure_reason="Error rate exceeded threshold",
        )
        assert not result.passed
        assert result.failure_reason is not None


class TestFireDrillResult:
    def test_passing(self) -> None:
        result = FireDrillResult(
            fault_injected="kill_pod",
            detected=True,
            reverted=True,
            detection_time_seconds=30.0,
            revert_time_seconds=90.0,
            passed=True,
        )
        assert result.passed
        assert result.detected
        assert result.reverted

    def test_failing(self) -> None:
        result = FireDrillResult(
            fault_injected="block_database_port",
            detected=False,
            reverted=False,
            detection_time_seconds=400.0,
            revert_time_seconds=0.0,
            passed=False,
        )
        assert not result.passed


class TestIncidentReport:
    def test_creation(self) -> None:
        report = IncidentReport(
            incident_id="inc_001",
            timestamp=datetime(2026, 6, 20, 2, 0, 0),
            trigger="error_rate_spike",
            error_rate_at_trigger=0.05,
            revert_target="deploy_v1.2.3",
            revert_succeeded=True,
            downtime_seconds=45.0,
            forensic_path="/forensics/inc_001",
        )
        assert report.revert_succeeded
        assert report.human_notified_at is None

    def test_with_human_notification(self) -> None:
        report = IncidentReport(
            incident_id="inc_002",
            timestamp=datetime(2026, 6, 20, 2, 0, 0),
            trigger="revert_failed",
            error_rate_at_trigger=0.10,
            revert_target="deploy_v1.2.2",
            revert_succeeded=False,
            downtime_seconds=300.0,
            forensic_path="/forensics/inc_002",
            human_notified_at=datetime(2026, 6, 20, 2, 5, 0),
        )
        assert not report.revert_succeeded
        assert report.human_notified_at is not None


class TestFeatureCostLedger:
    def test_add_inference_call(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.add_inference_call(tokens_in=1000, tokens_out=500, gpu_minutes=2.0)
        assert ledger.inference_calls == 1
        assert ledger.gpu_minutes == 2.0
        assert ledger.estimated_usd == pytest.approx(0.0012)

    def test_multiple_calls_accumulate(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.add_inference_call(tokens_in=1000, tokens_out=1000, gpu_minutes=1.0)
        ledger.add_inference_call(tokens_in=500, tokens_out=500, gpu_minutes=0.5)
        assert ledger.inference_calls == 2
        assert ledger.gpu_minutes == 1.5

    def test_check_budget_within_limits(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.add_inference_call(tokens_in=100, tokens_out=100, gpu_minutes=1.0)
        ledger.check_budget()  # Should not raise

    def test_check_budget_inference_exceeded(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.inference_calls = 51
        with pytest.raises(BudgetExceeded, match="inference call limit"):
            ledger.check_budget()

    def test_check_budget_gpu_exceeded(self) -> None:
        ledger = FeatureCostLedger(feature_id="feat_001")
        ledger.gpu_minutes = 121.0
        with pytest.raises(BudgetExceeded, match="GPU minute limit"):
            ledger.check_budget()


class TestBudgetExceeded:
    def test_exception_message(self) -> None:
        exc = BudgetExceeded("Test budget error")
        assert str(exc) == "Test budget error"


class TestFeatureRequest:
    def _make_feature(self) -> FeatureRequest:
        return FeatureRequest(
            id="feat_2026_0620_001",
            created_at=datetime(2026, 6, 20, 10, 0, 0),
        )

    def test_default_values(self) -> None:
        fr = self._make_feature()
        assert fr.id == "feat_2026_0620_001"
        assert fr.spec_hash == ""
        assert fr.complexity_bucket == ""
        assert fr.code_retry_count == 0
        assert fr.max_code_retries == 3
        assert fr.blueprint is None
        assert fr.interface_files == []
        assert fr.implementation_files == []
        assert not fr.awaiting_human_approval
        assert not fr.human_approval_received
        assert fr.escalation_reason is None

    def test_validate_spec_hash_no_blueprint(self) -> None:
        fr = self._make_feature()
        fr.validate_spec_hash()  # Should not raise when blueprint is None

    def test_validate_spec_hash_matching(self) -> None:
        fr = self._make_feature()
        bp = SpecificationBlueprint(
            project_name="Test",
            one_line_description="Test",
            core_entities=[],
            business_rules=[],
            hidden_complexities=[],
            tech_stack={},
            deployment_target="k8s",
            constraints={},
            integrations=[],
            data_retention="30d",
            expected_users=100,
            availability_target="99.9%",
            offline_support=False,
        )
        bp.lock()
        fr.blueprint = bp
        fr.spec_hash = bp.spec_hash
        fr.validate_spec_hash()  # Should not raise

    def test_validate_spec_hash_mismatch_raises(self) -> None:
        fr = self._make_feature()
        bp = SpecificationBlueprint(
            project_name="Test",
            one_line_description="Test",
            core_entities=[],
            business_rules=[],
            hidden_complexities=[],
            tech_stack={},
            deployment_target="k8s",
            constraints={},
            integrations=[],
            data_retention="30d",
            expected_users=100,
            availability_target="99.9%",
            offline_support=False,
        )
        bp.lock()
        fr.blueprint = bp
        fr.spec_hash = "wrong_hash_!"
        with pytest.raises(ValueError, match="Spec hash mismatch"):
            fr.validate_spec_hash()

    def test_with_full_state(self) -> None:
        fr = self._make_feature()
        fr.complexity_bucket = "complex"
        fr.interface_files = ["models.py", "routes.py"]
        fr.implementation_files = ["models.py"]
        fr.diff = "diff content"
        fr.code_retry_count = 1
        fr.semantic_diff_similarity = 0.85
        assert fr.code_retry_count == 1
        assert len(fr.interface_files) == 2

    def test_with_cost_ledger(self) -> None:
        fr = self._make_feature()
        fr.cost_ledger = FeatureCostLedger(feature_id=fr.id)
        fr.cost_ledger.add_inference_call(
            tokens_in=500, tokens_out=500, gpu_minutes=1.0
        )
        assert fr.cost_ledger.inference_calls == 1

    def test_with_incident_history(self) -> None:
        fr = self._make_feature()
        report = IncidentReport(
            incident_id="inc_001",
            timestamp=datetime(2026, 6, 20, 2, 0, 0),
            trigger="latency_spike",
            error_rate_at_trigger=0.02,
            revert_target="v1.0.0",
            revert_succeeded=True,
            downtime_seconds=30.0,
            forensic_path="/forensics/inc_001",
        )
        fr.incident_history.append(report)
        assert len(fr.incident_history) == 1
