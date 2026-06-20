"""Tests for shared data models."""

from pipeline.shared.models import (
    AuditResult,
    AuditSeverity,
    ComplexityBucket,
    FeatureCostLedger,
    FeatureRequest,
    SpecificationBlueprint,
    VerificationResult,
)


def test_complexity_bucket_values() -> None:
    assert ComplexityBucket.NANO == "nano"
    assert ComplexityBucket.CRITICAL == "critical"


def test_verification_result_pass_rate() -> None:
    result = VerificationResult(invariants_total=10, invariants_proven=8)
    assert result.pass_rate == 0.8
    assert not result.all_proven


def test_verification_result_all_proven() -> None:
    result = VerificationResult(invariants_total=5, invariants_proven=5)
    assert result.pass_rate == 1.0
    assert result.all_proven


def test_verification_result_empty() -> None:
    result = VerificationResult()
    assert result.pass_rate == 0.0


def test_audit_result_blocking() -> None:
    audit = AuditResult(severity=AuditSeverity.BLOCK)
    assert audit.is_blocking

    audit_pass = AuditResult(severity=AuditSeverity.PASS)
    assert not audit_pass.is_blocking


def test_feature_cost_ledger() -> None:
    ledger = FeatureCostLedger()
    ledger.record_inference_call(gpu_minutes=2.5, cost_usd=0.01)
    ledger.record_inference_call(gpu_minutes=1.0, cost_usd=0.005)
    ledger.record_retry()

    assert ledger.inference_calls == 2
    assert ledger.gpu_minutes == 3.5
    assert ledger.cost_usd == 0.015
    assert ledger.retries_global == 1


def test_specification_blueprint_lock() -> None:
    bp = SpecificationBlueprint(
        title="Payment Service",
        description="Handles payments",
        entities=["Account", "Transaction"],
    )
    assert not bp.is_locked

    spec_hash = bp.lock()
    assert bp.is_locked
    assert bp.locked_at is not None
    assert len(spec_hash) == 12


def test_specification_blueprint_hash_deterministic() -> None:
    bp = SpecificationBlueprint(title="Test", description="Test", entities=["A"])
    hash1 = bp.compute_hash()
    hash2 = bp.compute_hash()
    assert hash1 == hash2


def test_feature_request_field_ownership() -> None:
    fr = FeatureRequest(id="feat_001")
    assert fr.get_field_owner("spec_hash") == "intake_agent"
    assert fr.get_field_owner("diff") == "coder_agent"
    assert fr.get_field_owner("shadow_deployment_id") == "sre_agent"
    assert fr.get_field_owner("id") == "orchestrator"


def test_feature_request_validate_field_access() -> None:
    fr = FeatureRequest(id="feat_001")
    assert fr.validate_field_access("diff", "coder_agent")
    assert not fr.validate_field_access("diff", "sre_agent")


def test_feature_request_defaults() -> None:
    fr = FeatureRequest(id="feat_001")
    assert fr.complexity_bucket == ComplexityBucket.STANDARD
    assert fr.code_retry_count == 0
    assert fr.max_code_retries == 3
    assert not fr.awaiting_human_approval
    assert fr.cost_ledger.inference_calls == 0
