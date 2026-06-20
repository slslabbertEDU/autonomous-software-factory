"""Prometheus metrics shared across all agents.

Centralizes metric definitions to avoid duplicate registrations
and ensure consistent naming/labeling across the pipeline.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- LLM metrics (used by Coder Agent, QA Agent, Intake Agent) ---

llm_call_counter = Counter(
    "asf_llm_calls_total",
    "Total LLM inference calls",
    ["model", "role"],
)

llm_latency_histogram = Histogram(
    "asf_llm_latency_seconds",
    "LLM call latency in seconds",
    ["model", "role"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# --- Cost metrics (used by all agents via CostTracker) ---

inference_calls_gauge = Gauge(
    "asf_inference_calls",
    "Current inference call count per feature",
    ["feature_id"],
)

gpu_minutes_gauge = Gauge(
    "asf_gpu_minutes",
    "GPU minutes consumed per feature",
    ["feature_id"],
)

cost_total_gauge = Gauge(
    "asf_cost_usd",
    "Total cost in USD per feature",
    ["feature_id"],
)

# --- Retry/circuit breaker metrics (used by all agents) ---

retry_counter = Counter(
    "asf_retries_total",
    "Total retry attempts",
    ["operation", "attempt"],
)

circuit_breaker_trips_counter = Counter(
    "asf_circuit_breaker_trips_total",
    "Circuit breaker trip events",
    ["breaker"],
)

# --- Pipeline stage metrics (used by orchestrator) ---

pipeline_stage_duration = Histogram(
    "asf_pipeline_stage_duration_seconds",
    "Duration of each pipeline stage",
    ["stage", "complexity_bucket"],
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400),
)

pipeline_stage_status = Counter(
    "asf_pipeline_stage_completions_total",
    "Pipeline stage completion status",
    ["stage", "status"],
)

# --- SRE metrics (used by SRE Agent) ---

revert_counter = Counter(
    "asf_reverts_total",
    "Total automated reverts",
    ["trigger"],
)

fire_drill_result_counter = Counter(
    "asf_fire_drill_results_total",
    "Fire drill outcomes",
    ["fault_type", "result"],
)

# --- QA metrics (used by QA Agent) ---

verification_pass_rate_gauge = Gauge(
    "asf_verification_pass_rate",
    "Z3 formal verification pass rate",
    ["feature_id"],
)

test_coverage_gauge = Gauge(
    "asf_test_coverage_percent",
    "Test coverage percentage",
    ["feature_id"],
)

hostile_audit_severity_counter = Counter(
    "asf_hostile_audit_results_total",
    "Hostile audit severity outcomes",
    ["severity"],
)
