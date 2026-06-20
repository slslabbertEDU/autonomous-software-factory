# System Architecture

## Overview

The Autonomous Software Factory is a multi-agent pipeline connected by a durable execution orchestrator (Temporal). Each agent is a stateless worker that receives a `FeatureRequest` payload, performs its function, mutates only its own fields, and returns the updated payload. State persists across crashes. No agent shares mutable state with another.

---

## Pipeline State Object

Every agent receives and returns this object. Temporal serializes it between activities.

```python
@dataclass
class FeatureRequest:
    # Identity
    id: str                           # feat_2026_0427_001
    spec_hash: str                    # SHA-256[:12] of locked blueprint
    complexity_bucket: str            # nano/micro/standard/complex/critical

    # Blueprint
    blueprint: SpecificationBlueprint

    # Code generation state
    interface_files: List[str]        # populated after skeleton step
    implementation_files: List[str]   # populated after impl step
    diff: str                         # full git diff of changes
    code_retry_count: int = 0
    max_code_retries: int = 3

    # QA state
    unit_test_results: Dict           # {file: {passed: bool, output: str}}
    hostile_audit_result: AuditResult
    formal_verification_result: Optional[VerificationResult]

    # Migration state
    migration_scripts: List[str]
    clone_validation_passed: bool = False

    # Deployment state
    shadow_deployment_id: str
    load_test_result: LoadTestResult
    fire_drill_result: FireDrillResult
    production_deployment_id: str

    # Cost tracking
    cost_ledger: FeatureCostLedger

    # Human loop
    awaiting_human_approval: bool = False
    human_approval_received: bool = False
    escalation_reason: Optional[str] = None

    # Audit trail
    created_at: datetime
    promoted_at: Optional[datetime]
    incident_history: List[IncidentReport]
```

**Rule:** No agent reads fields it does not own. The QA Agent does not touch `shadow_deployment_id`. The SRE Agent does not touch `blueprint`. Violations are caught in code review.

---

## Complexity Buckets

Every feature is classified at blueprint lock. Temporal activity timeouts are set per bucket.

| Bucket | Description | Target Hours |
|---|---|---|
| nano | CRUD API, single entity | 4 |
| micro | Multi-entity, no auth | 8 |
| standard | Auth + multi-user + DB | 16 |
| complex | Real-time, WebSockets, queues | 24 |
| critical | Payments, medical, compliance | 48 |

---

## Agent Responsibilities

### Intake Agent (Specification Factory)

**Input:** Raw natural language idea  
**Output:** Locked `SpecificationBlueprint` with `spec_hash`

Four phases:
1. **Domain Research** — breaks idea into entities, business rules, hidden complexities, race conditions
2. **Architectural Options** — presents 2-4 approaches with tradeoffs and cost estimates
3. **Constraint Questionnaire** — targeted questions by category (state, integrations, data, access control, ops, edge cases)
4. **Blueprint Lock** — all decisions compiled, `spec_hash` assigned, blueprint marked `is_locked: True`

Formal specifications generated for critical domains:
```
Natural: "Account balances can never be negative"
Formal:  ∀a ∈ Accounts: balance(a) ≥ 0
Pre:     withdraw(account, amount) requires balance(account) ≥ amount
Post:    balance'(account) = balance(account) - amount
```

---

### Coder Agent (Direct vLLM Loop)

**Input:** Locked blueprint + RAG context (15 most relevant files) + dependency manifest  
**Output:** Code diff committed to repository

**Not Aider.** A direct agent loop calling the vLLM endpoint. Full control over retry logic, context injection, and file parsing.

Two Temporal activities (skeleton-first):

**Activity 1: Interface Generation**
```python
# Generates ONLY:
# - Empty class structures
# - Database model definitions
# - Function signatures with docstrings
# - No implementation logic
```

**Activity 2: Implementation (per file)**
```python
# For each interface file:
# - Fill in logic for that file only
# - Run unit tests for that file
# - Retry just this file on failure (not entire codebase)
# - Context: ~8-12K tokens (not 32K)
```

Context budget per call: ~8-12K tokens. Total context: blueprint + single file interface + 3-5 most relevant existing files.

**Dependency constraint injected into every prompt:**
```
DEPENDENCY CONSTRAINTS — NON-NEGOTIABLE:
You may ONLY use dependencies at these exact versions: [manifest]
If you need unlisted dependency: output "DEPENDENCY_REQUEST: {name}"
Do NOT write code using unapproved dependencies.
```

---

### QA Agent (Verification Pipeline)

**Input:** Code diff  
**Output:** Pass/fail per stage + failure details for retry

Six sequential stages:

| Stage | Tool | Failure Action |
|---|---|---|
| Unit Tests | pytest (80% coverage minimum) | Feed failures to Coder Agent |
| Type Checking | mypy --strict | Feed errors to Coder Agent |
| Linting | ruff | Feed errors to Coder Agent |
| Security Scan | bandit + semgrep | BLOCK on HIGH severity |
| Hostile Audit | DeepSeek-R1 (second model) | BLOCK on BLOCK severity |
| Formal Verification | Z3 (critical paths only) | Feed counterexample to Coder Agent |

**Hostile Audit prompt (DeepSeek-R1):**
```
SPEC: {blueprint}
CODE DIFF: {diff}

You are a hostile security auditor. Find:
1. Logic that contradicts the spec
2. Off-by-ones in financial calculations
3. Missing auth checks
4. Race conditions
5. Anything the tests would not catch

Return JSON: {"issues": [...], "severity": "PASS|WARN|BLOCK"}
```

**Semantic diff gate** (before commit):
```python
similarity = cosine_similarity(embed(blueprint), embed(code_summary))
if similarity < 0.75:
    return False  # Code doesn't match spec — retry with gap analysis
```

---

### State Migration Pipeline

**Rule:** The clone is a proof environment only. It is never promoted to production. Production data written during the shadow test window is never lost.

```
1. Clone production database → ephemeral container
2. Apply migration scripts to clone
3. Verify constraints, foreign keys, row counts
4. Mirror 10% of production traffic to clone for 15 minutes
5. Compare clone responses to production responses
6. If passes: DISCARD clone entirely
7. Run the verified migration scripts against LIVE production database
8. Rollback script pre-tested on clone before production run
```

---

### SRE Agent (Self-Healing Operations)

**Primary directive: REVERT, NEVER REPAIR IN PRODUCTION.**

**Revert thresholds:**
```python
REVERT_THRESHOLDS = {
    "error_rate": 0.01,           # 1% error rate
    "p99_latency_increase": 2.0,  # 2x latency increase
    "cpu_sustained": 0.90,        # 90% CPU for 5 minutes
    "memory_leak_rate": 0.05,     # 5% growth per 5 minutes
}
```

**2 AM protocol:**
1. Detect anomaly
2. Capture forensic state (logs, metrics, memory dump, active transactions)
3. Revert to last known good deployment
4. Verify revert succeeded
5. Generate incident report
6. Notify human at 7 AM (not 2 AM, unless revert failed)

**The SRE Agent NEVER:**
- Attempts to fix code in production
- Applies patches to running services
- Modifies database state
- Restarts services hoping it helps
- Wakes the human unless revert fails

---

### Fire Drill (Chaos Engineering Gate)

Runs before every production promotion. The SRE Agent must prove it works before it's needed.

```python
FAULT_TYPES = {
    "nano":     kill_pod,
    "standard": spike_cpu_to_95_percent,
    "complex":  block_database_port,
    "critical": corrupt_single_response_header,
}

# SRE Agent has 5 minutes to detect, 10 minutes to revert
# If fire drill fails: DO NOT PROMOTE TO PRODUCTION
```

---

### Archivist Agent (Knowledge Management)

Runs after every merged PR. Prevents knowledge rot in AI-generated codebases.

Updates:
- **System Overview** — single page, under 2000 words, describes entire system
- **Component Documentation** — updated for affected components
- **Architecture Diagram** — Mermaid diagram regenerated from codebase
- **Changelog** — human-readable summary of every change
- **ADRs** — Architecture Decision Records for every feature

Query interface:
```python
archivist.query("How does payment processing work?")
# Returns: Plain English explanation with ADR references
```

---

## Cost Circuit Breaker

```python
COST_LIMITS = {
    "max_inference_calls_per_feature": 50,
    "max_gpu_minutes_per_feature": 120,
    "max_retries_global": 3,
}
# Hard stop on budget exceeded → escalate to human
```

Per-feature cost tracked in `FeatureCostLedger`. Weekly summary: cost per feature, cost per component.

---

## Temporal Orchestrator Workflow

```python
@workflow.defn
class FeatureDevelopmentWorkflow:
    @workflow.run
    async def run(self, feature: FeatureRequest) -> FeatureRequest:

        # Phase 1: Specification
        feature = await workflow.execute_activity(run_intake_agent, feature)
        feature = await workflow.execute_activity(verify_formal_specs, feature)
        # PAUSE: Human approves blueprint

        # Phase 2: Code Generation (skeleton-first)
        feature = await workflow.execute_activity(run_coder_agent_interfaces, feature)
        feature = await workflow.execute_activity(validate_interfaces_against_blueprint, feature)

        for file in feature.interface_files:
            while feature.code_retry_count < feature.max_code_retries:
                feature = await workflow.execute_activity(run_coder_agent_implement_file, feature, file)
                feature = await workflow.execute_activity(run_unit_tests_for_file, feature, file)
                if feature.file_test_results[file]['passed']:
                    break
                feature.code_retry_count += 1

        # Phase 3: QA
        feature = await workflow.execute_activity(run_hostile_audit, feature)
        feature = await workflow.execute_activity(run_formal_verification, feature)

        # Phase 4: Shadow + Load Test + Fire Drill
        feature = await workflow.execute_activity(run_state_migration_pipeline, feature)
        feature = await workflow.execute_activity(deploy_to_shadow, feature)
        feature = await workflow.execute_activity(run_load_swarm, feature)
        feature = await workflow.execute_activity(run_sre_fire_drill, feature)

        # Phase 5: Production
        # PAUSE: Human approves promotion (or auto-promote if all clean)
        feature = await workflow.execute_activity(deploy_to_production, feature)
        feature = await workflow.execute_activity(monitor_production, feature)

        # Phase 6: Knowledge
        feature = await workflow.execute_activity(run_archivist, feature)

        return feature
```
