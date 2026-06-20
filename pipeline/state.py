"""
Autonomous Software Factory — Pipeline State

The FeatureRequest dataclass is the sole shared state object passed between
every Temporal activity in the pipeline. Temporal serializes it between steps.

Rules:
- No activity reads fields it does not own
- Every field mutation must be logged to the audit trail
- spec_hash must match blueprint hash at every stage or pipeline resets
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# COMPLEXITY BUCKETS
# ─────────────────────────────────────────────────────────────────────────────

COMPLEXITY_BUCKETS = {
    "nano":     {"description": "CRUD API, single entity",            "target_hours": 4,  "activity_timeout_minutes": 30},
    "micro":    {"description": "Multi-entity app, no auth",          "target_hours": 8,  "activity_timeout_minutes": 60},
    "standard": {"description": "Auth + multi-user + DB",             "target_hours": 16, "activity_timeout_minutes": 120},
    "complex":  {"description": "Real-time, WebSockets, queues",      "target_hours": 24, "activity_timeout_minutes": 180},
    "critical": {"description": "Payments, medical, compliance",      "target_hours": 48, "activity_timeout_minutes": 240},
}

# ─────────────────────────────────────────────────────────────────────────────
# COST LIMITS
# ─────────────────────────────────────────────────────────────────────────────

COST_LIMITS = {
    "max_inference_calls_per_feature": 50,
    "max_gpu_minutes_per_feature": 120,
    "max_retries_global": 3,
}

# ─────────────────────────────────────────────────────────────────────────────
# SUB-OBJECTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SpecificationBlueprint:
    project_name: str
    one_line_description: str
    core_entities: List[Dict]
    business_rules: List[Dict]
    hidden_complexities: List[str]
    tech_stack: Dict
    deployment_target: str
    constraints: Dict
    integrations: List[Dict]
    data_retention: str
    expected_users: int
    availability_target: str
    offline_support: bool
    formal_specs: Optional[Dict] = None
    is_locked: bool = False
    spec_hash: str = field(init=False, default="")

    def lock(self) -> None:
        """Lock the blueprint and assign its hash. Call once — immutable after."""
        if self.is_locked:
            raise ValueError("Blueprint already locked. Cannot modify after lock.")
        content = json.dumps({
            "core_entities": self.core_entities,
            "business_rules": self.business_rules,
            "tech_stack": self.tech_stack,
            "constraints": self.constraints,
        }, sort_keys=True)
        self.spec_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        self.is_locked = True


@dataclass
class AuditResult:
    issues: List[Dict]
    severity: str  # PASS | WARN | BLOCK
    model_used: str
    tokens_used: int
    reasoning_trace: Optional[str] = None


@dataclass
class VerificationResult:
    invariants_checked: int
    invariants_proven: int
    counterexamples: List[Dict]
    pass_rate: float  # invariants_proven / invariants_checked
    passed: bool


@dataclass
class LoadTestResult:
    p99_latency_ms: float
    error_rate: float
    timeout_count: int
    deadlock_count: int
    peak_rps: float
    passed: bool
    failure_reason: Optional[str] = None


@dataclass
class FireDrillResult:
    fault_injected: str
    detected: bool
    reverted: bool
    detection_time_seconds: float
    revert_time_seconds: float
    passed: bool


@dataclass
class IncidentReport:
    incident_id: str
    timestamp: datetime
    trigger: str
    error_rate_at_trigger: float
    revert_target: str
    revert_succeeded: bool
    downtime_seconds: float
    forensic_path: str
    human_notified_at: Optional[datetime] = None


@dataclass
class FeatureCostLedger:
    feature_id: str
    inference_calls: int = 0
    gpu_minutes: float = 0.0
    estimated_usd: float = 0.0

    def add_inference_call(self, tokens_in: int, tokens_out: int, gpu_minutes: float = 0.0) -> None:
        self.inference_calls += 1
        self.gpu_minutes += gpu_minutes
        # Approximate cost at $0.0008/1K tokens
        self.estimated_usd += (tokens_in + tokens_out) / 1000 * 0.0008

    def check_budget(self) -> None:
        if self.inference_calls > COST_LIMITS["max_inference_calls_per_feature"]:
            raise BudgetExceeded(
                f"Feature {self.feature_id} exceeded inference call limit "
                f"({self.inference_calls} > {COST_LIMITS['max_inference_calls_per_feature']})"
            )
        if self.gpu_minutes > COST_LIMITS["max_gpu_minutes_per_feature"]:
            raise BudgetExceeded(
                f"Feature {self.feature_id} exceeded GPU minute limit "
                f"({self.gpu_minutes:.1f} > {COST_LIMITS['max_gpu_minutes_per_feature']})"
            )


class BudgetExceeded(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY STATE OBJECT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FeatureRequest:
    """
    The sole shared state object for the entire pipeline.
    Passed between every Temporal activity. Serialized by Temporal between steps.

    Ownership rules (no agent touches fields outside its scope):
      Intake Agent:       blueprint, spec_hash, complexity_bucket
      Coder Agent:        interface_files, implementation_files, diff, code_retry_count
      QA Agent:           unit_test_results, hostile_audit_result, formal_verification_result
      Migration Pipeline: migration_scripts, clone_validation_passed
      Shadow/Load:        shadow_deployment_id, load_test_result
      Fire Drill:         fire_drill_result
      SRE Agent:          production_deployment_id, incident_history
      Archivist:          (reads all, writes nothing to FeatureRequest)
      Orchestrator:       awaiting_human_approval, human_approval_received, escalation_reason
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    id: str                          # feat_2026_0427_001
    created_at: datetime

    # ── Blueprint (owned by Intake Agent) ─────────────────────────────────────
    blueprint: Optional[SpecificationBlueprint] = None
    spec_hash: str = ""              # Must match blueprint.spec_hash at all times
    complexity_bucket: str = ""      # nano | micro | standard | complex | critical

    # ── Code Generation (owned by Coder Agent) ────────────────────────────────
    interface_files: List[str] = field(default_factory=list)
    implementation_files: List[str] = field(default_factory=list)
    diff: str = ""
    code_retry_count: int = 0
    max_code_retries: int = 3
    file_test_results: Dict = field(default_factory=dict)  # {filename: {passed, output}}

    # ── QA (owned by QA Agent) ────────────────────────────────────────────────
    unit_test_results: Dict = field(default_factory=dict)
    hostile_audit_result: Optional[AuditResult] = None
    formal_verification_result: Optional[VerificationResult] = None
    semantic_diff_similarity: float = 0.0

    # ── Migration (owned by Migration Pipeline) ───────────────────────────────
    migration_scripts: List[str] = field(default_factory=list)
    clone_validation_passed: bool = False

    # ── Deployment (owned by Shadow/SRE) ──────────────────────────────────────
    shadow_deployment_id: str = ""
    load_test_result: Optional[LoadTestResult] = None
    fire_drill_result: Optional[FireDrillResult] = None
    production_deployment_id: str = ""
    promoted_at: Optional[datetime] = None

    # ── Incidents (owned by SRE Agent) ────────────────────────────────────────
    incident_history: List[IncidentReport] = field(default_factory=list)

    # ── Cost (owned by all agents, checked by Orchestrator) ───────────────────
    cost_ledger: Optional[FeatureCostLedger] = None

    # ── Human Loop (owned by Orchestrator) ────────────────────────────────────
    awaiting_human_approval: bool = False
    human_approval_received: bool = False
    escalation_reason: Optional[str] = None

    def validate_spec_hash(self) -> None:
        """Hard check: pipeline resets if spec hash drifts."""
        if self.blueprint and self.spec_hash != self.blueprint.spec_hash:
            raise ValueError(
                f"Spec hash mismatch for {self.id}. "
                f"Expected {self.blueprint.spec_hash}, got {self.spec_hash}. "
                f"Blueprint was modified after lock. Pipeline reset required."
            )
