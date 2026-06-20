"""Pipeline state objects passed between agents via Temporal."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ComplexityBucket(str, Enum):
    """Feature complexity classification. Determines activity timeouts."""

    NANO = "nano"
    MICRO = "micro"
    STANDARD = "standard"
    COMPLEX = "complex"
    CRITICAL = "critical"


class AuditSeverity(str, Enum):
    """Hostile audit result severity levels."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


class FireDrillStatus(str, Enum):
    """Fire drill outcome status."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


@dataclass
class AuditIssue:
    """A single issue found during hostile audit."""

    description: str
    category: str
    file_path: str | None = None
    line_number: int | None = None


@dataclass
class AuditResult:
    """Result of the hostile principal audit (DeepSeek-R1)."""

    issues: list[AuditIssue] = field(default_factory=list)
    severity: AuditSeverity = AuditSeverity.PASS

    @property
    def is_blocking(self) -> bool:
        return self.severity == AuditSeverity.BLOCK

    @property
    def issue_count(self) -> int:
        return len(self.issues)


@dataclass
class VerificationResult:
    """Result of Z3 formal verification for critical paths."""

    verified: bool = False
    counterexamples: list[str] = field(default_factory=list)
    properties_checked: int = 0
    properties_passed: int = 0

    @property
    def pass_rate(self) -> float:
        if self.properties_checked == 0:
            return 0.0
        return self.properties_passed / self.properties_checked


@dataclass
class LoadTestResult:
    """K6 load test result with Poisson spike distribution."""

    passed: bool = False
    total_requests: int = 0
    failed_requests: int = 0
    p99_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    max_rps: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests


@dataclass
class FireDrillResult:
    """Chaos engineering fire drill result."""

    status: FireDrillStatus = FireDrillStatus.NOT_RUN
    fault_type: str = ""
    detection_time_seconds: float = 0.0
    revert_time_seconds: float = 0.0
    max_detection_seconds: float = 300.0
    max_revert_seconds: float = 600.0

    @property
    def passed(self) -> bool:
        return self.status == FireDrillStatus.PASSED

    @property
    def detection_within_limit(self) -> bool:
        return self.detection_time_seconds <= self.max_detection_seconds

    @property
    def revert_within_limit(self) -> bool:
        return self.revert_time_seconds <= self.max_revert_seconds


@dataclass
class IncidentReport:
    """Production incident record."""

    incident_id: str
    detected_at: datetime
    reverted_at: datetime | None = None
    description: str = ""
    root_cause: str = ""
    was_auto_reverted: bool = False

    @property
    def resolution_time_seconds(self) -> float | None:
        if self.reverted_at is None:
            return None
        return (self.reverted_at - self.detected_at).total_seconds()


@dataclass
class SpecificationBlueprint:
    """Locked specification blueprint with integrity hash."""

    title: str
    description: str
    entities: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    formal_specs: list[str] = field(default_factory=list)
    constraints: dict[str, str] = field(default_factory=dict)
    is_locked: bool = False
    locked_at: datetime | None = None
    _spec_hash: str | None = field(default=None, repr=False)

    def lock(self) -> str:
        """Lock the blueprint and compute spec_hash. Returns the hash."""
        if self.is_locked:
            raise ValueError("Blueprint is already locked")
        self.is_locked = True
        self.locked_at = datetime.now(UTC)
        self._spec_hash = self._compute_hash()
        return self._spec_hash

    @property
    def spec_hash(self) -> str | None:
        return self._spec_hash

    def verify_integrity(self) -> bool:
        """Verify blueprint hasn't been modified since locking."""
        if not self.is_locked or self._spec_hash is None:
            return False
        return self._compute_hash() == self._spec_hash

    def _compute_hash(self) -> str:
        """SHA-256[:12] of blueprint content."""
        content = (
            f"{self.title}|{self.description}|"
            f"{','.join(sorted(self.entities))}|"
            f"{','.join(sorted(self.business_rules))}|"
            f"{','.join(sorted(self.formal_specs))}|"
            f"{str(sorted(self.constraints.items()))}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:12]


@dataclass
class FeatureRequest:
    """Central pipeline state object passed between all agents."""

    # Identity
    id: str
    spec_hash: str = ""
    complexity_bucket: ComplexityBucket = ComplexityBucket.STANDARD

    # Blueprint
    blueprint: SpecificationBlueprint = field(
        default_factory=lambda: SpecificationBlueprint(title="", description="")
    )

    # Code generation state
    interface_files: list[str] = field(default_factory=list)
    implementation_files: list[str] = field(default_factory=list)
    diff: str = ""
    code_retry_count: int = 0
    max_code_retries: int = 3

    # QA state
    unit_test_results: dict[str, dict[str, object]] = field(default_factory=dict)
    hostile_audit_result: AuditResult = field(default_factory=AuditResult)
    formal_verification_result: VerificationResult | None = None

    # Migration state
    migration_scripts: list[str] = field(default_factory=list)
    clone_validation_passed: bool = False

    # Deployment state
    shadow_deployment_id: str = ""
    load_test_result: LoadTestResult = field(default_factory=LoadTestResult)
    fire_drill_result: FireDrillResult = field(default_factory=FireDrillResult)
    production_deployment_id: str = ""

    # Human loop
    awaiting_human_approval: bool = False
    human_approval_received: bool = False
    escalation_reason: str | None = None

    # Audit trail
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    promoted_at: datetime | None = None
    incident_history: list[IncidentReport] = field(default_factory=list)

    @property
    def can_retry_code(self) -> bool:
        return self.code_retry_count < self.max_code_retries

    @property
    def is_ready_for_deployment(self) -> bool:
        """Check if all pre-deployment gates have passed."""
        if self.hostile_audit_result.is_blocking:
            return False
        if not self.fire_drill_result.passed:
            return False
        if not self.load_test_result.passed:
            return False
        return True

    def increment_retry(self) -> bool:
        """Increment retry count. Returns True if retries remain."""
        self.code_retry_count += 1
        return self.can_retry_code
