"""Shared data models for the pipeline state object.

All agents receive and return the FeatureRequest. Temporal serializes it between
activities. Each agent only mutates fields it owns (enforced via field ownership
metadata).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field


class ComplexityBucket(str, Enum):
    """Feature complexity classification. Determines Temporal timeouts."""

    NANO = "nano"
    MICRO = "micro"
    STANDARD = "standard"
    COMPLEX = "complex"
    CRITICAL = "critical"


COMPLEXITY_TARGET_HOURS: dict[ComplexityBucket, int] = {
    ComplexityBucket.NANO: 4,
    ComplexityBucket.MICRO: 8,
    ComplexityBucket.STANDARD: 16,
    ComplexityBucket.COMPLEX: 24,
    ComplexityBucket.CRITICAL: 48,
}


class AuditSeverity(str, Enum):
    """Hostile audit severity levels."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


class AuditIssue(BaseModel):
    """A single issue found during hostile audit."""

    description: str
    category: str
    severity: AuditSeverity
    file_path: str | None = None
    line_number: int | None = None


class AuditResult(BaseModel):
    """Result of the hostile principal audit (DeepSeek-R1)."""

    issues: list[AuditIssue] = Field(default_factory=list)
    severity: AuditSeverity = AuditSeverity.PASS
    raw_response: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.severity == AuditSeverity.BLOCK


class VerificationResult(BaseModel):
    """Z3 formal verification result for critical paths."""

    invariants_total: int = 0
    invariants_proven: int = 0
    counterexamples: list[str] = Field(default_factory=list)
    verification_time_seconds: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pass_rate(self) -> float:
        if self.invariants_total == 0:
            return 0.0
        return self.invariants_proven / self.invariants_total

    @property
    def all_proven(self) -> bool:
        return self.invariants_proven == self.invariants_total


class LoadTestResult(BaseModel):
    """K6 Poisson load test results."""

    requests_total: int = 0
    requests_failed: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_rate: float = 0.0
    duration_seconds: float = 0.0
    passed: bool = False


class FireDrillResult(BaseModel):
    """SRE fire drill (chaos engineering) result."""

    fault_type: str
    detection_time_seconds: float = 0.0
    revert_time_seconds: float = 0.0
    revert_successful: bool = False
    passed: bool = False


class IncidentReport(BaseModel):
    """Production incident captured by SRE Agent."""

    incident_id: str
    detected_at: datetime
    reverted_at: datetime | None = None
    trigger: str
    forensic_state: dict[str, str] = Field(default_factory=dict)
    revert_successful: bool = False


class FeatureCostLedger(BaseModel):
    """Per-feature cost tracking. Enforces budget circuit breaker."""

    inference_calls: int = 0
    gpu_minutes: float = 0.0
    retries_global: int = 0
    cost_usd: float = 0.0

    def record_inference_call(self, gpu_minutes: float, cost_usd: float) -> None:
        self.inference_calls += 1
        self.gpu_minutes += gpu_minutes
        self.cost_usd += cost_usd

    def record_retry(self) -> None:
        self.retries_global += 1


class FormalSpecification(BaseModel):
    """A single formal specification for Z3 verification."""

    natural_language: str
    formal_expression: str
    precondition: str | None = None
    postcondition: str | None = None


class SpecificationBlueprint(BaseModel):
    """Locked specification blueprint produced by Intake Agent."""

    title: str = ""
    description: str = ""
    entities: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    formal_specs: list[FormalSpecification] = Field(default_factory=list)
    architecture_choice: str = ""
    constraints: dict[str, str] = Field(default_factory=dict)
    is_locked: bool = False
    locked_at: datetime | None = None

    def lock(self) -> str:
        """Lock the blueprint and return the spec_hash."""
        self.is_locked = True
        self.locked_at = datetime.utcnow()
        return self.compute_hash()

    def compute_hash(self) -> str:
        """SHA-256[:12] of the serialized blueprint."""
        payload = self.model_dump_json(exclude={"is_locked", "locked_at"})
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


class FileTestResult(BaseModel):
    """Unit test result for a single implementation file."""

    passed: bool
    output: str = ""
    coverage_percent: float | None = None


class FeatureRequest(BaseModel):
    """Pipeline state object passed between all agents via Temporal.

    Each agent only mutates fields it owns. Field ownership is documented
    via the 'owner' key in Field json_schema_extra.
    """

    # Identity
    id: str = Field(json_schema_extra={"owner": "orchestrator"})
    spec_hash: str = Field(default="", json_schema_extra={"owner": "intake_agent"})
    complexity_bucket: ComplexityBucket = Field(
        default=ComplexityBucket.STANDARD,
        json_schema_extra={"owner": "intake_agent"},
    )

    # Blueprint
    blueprint: SpecificationBlueprint = Field(
        default_factory=SpecificationBlueprint,
        json_schema_extra={"owner": "intake_agent"},
    )

    # Code generation state
    interface_files: list[str] = Field(
        default_factory=list, json_schema_extra={"owner": "coder_agent"}
    )
    implementation_files: list[str] = Field(
        default_factory=list, json_schema_extra={"owner": "coder_agent"}
    )
    diff: str = Field(default="", json_schema_extra={"owner": "coder_agent"})
    code_retry_count: int = Field(default=0, json_schema_extra={"owner": "coder_agent"})
    max_code_retries: int = Field(
        default=3, json_schema_extra={"owner": "orchestrator"}
    )

    # QA state
    unit_test_results: dict[str, FileTestResult] = Field(
        default_factory=dict, json_schema_extra={"owner": "qa_agent"}
    )
    hostile_audit_result: AuditResult | None = Field(
        default=None, json_schema_extra={"owner": "qa_agent"}
    )
    formal_verification_result: VerificationResult | None = Field(
        default=None, json_schema_extra={"owner": "qa_agent"}
    )

    # Migration state
    migration_scripts: list[str] = Field(
        default_factory=list, json_schema_extra={"owner": "sre_agent"}
    )
    clone_validation_passed: bool = Field(
        default=False, json_schema_extra={"owner": "sre_agent"}
    )

    # Deployment state
    shadow_deployment_id: str = Field(
        default="", json_schema_extra={"owner": "sre_agent"}
    )
    load_test_result: LoadTestResult | None = Field(
        default=None, json_schema_extra={"owner": "sre_agent"}
    )
    fire_drill_result: FireDrillResult | None = Field(
        default=None, json_schema_extra={"owner": "sre_agent"}
    )
    production_deployment_id: str = Field(
        default="", json_schema_extra={"owner": "sre_agent"}
    )

    # Cost tracking
    cost_ledger: FeatureCostLedger = Field(
        default_factory=FeatureCostLedger,
        json_schema_extra={"owner": "orchestrator"},
    )

    # Human loop
    awaiting_human_approval: bool = Field(
        default=False, json_schema_extra={"owner": "orchestrator"}
    )
    human_approval_received: bool = Field(
        default=False, json_schema_extra={"owner": "orchestrator"}
    )
    escalation_reason: str | None = Field(
        default=None, json_schema_extra={"owner": "orchestrator"}
    )

    # Audit trail
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        json_schema_extra={"owner": "orchestrator"},
    )
    promoted_at: datetime | None = Field(
        default=None, json_schema_extra={"owner": "sre_agent"}
    )
    incident_history: list[IncidentReport] = Field(
        default_factory=list, json_schema_extra={"owner": "sre_agent"}
    )

    def get_field_owner(self, field_name: str) -> str:
        """Return the agent that owns a given field."""
        field_info = self.model_fields.get(field_name)
        if field_info is None:
            raise ValueError(f"Unknown field: {field_name}")
        extra = field_info.json_schema_extra
        if isinstance(extra, dict):
            owner = extra.get("owner", "unknown")
            return str(owner)
        return "unknown"

    def validate_field_access(self, field_name: str, agent: str) -> bool:
        """Check if an agent is allowed to write a field."""
        return self.get_field_owner(field_name) == agent
