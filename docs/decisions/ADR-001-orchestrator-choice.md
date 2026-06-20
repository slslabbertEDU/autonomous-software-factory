# ADR-001: Temporal as Orchestration Layer

**Date:** 2026-06-20  
**Status:** Accepted  
**Author:** Shane Louis Slabbert

---

## Context

The Autonomous Software Factory pipeline has 15+ sequential steps, each of which can fail independently. Steps invoke external services (vLLM inference endpoints, GitHub, Kubernetes), take minutes to hours to complete, and must survive server crashes mid-execution. A naive implementation using async Python or a task queue (Celery, RQ) would lose state on crash and require complex manual recovery logic.

## Decision

Use **Temporal** as the orchestration layer.

## Rationale

Temporal provides durable execution: if the orchestrator server crashes during step 9 of a 15-step pipeline, the workflow resumes at step 9 on restart — not from the beginning. This property is non-negotiable for a pipeline where a single module generation run can take 4-48 hours.

Additional properties required and provided by Temporal:
- **Human-in-the-loop signals:** Workflows can pause indefinitely waiting for human approval (spec review, production promotion) and resume on signal receipt
- **Per-activity retry policies:** Each pipeline step has independent retry configuration (max attempts, backoff strategy, timeout)
- **Visibility UI:** Web interface shows every workflow, its current state, input/output at each step, and full execution history
- **SDK:** Python SDK matches the existing codebase language

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| Celery + Redis | No durable execution — state lost on crash |
| Prefect | Heavier operational overhead, less granular retry control |
| Apache Airflow | Designed for scheduled batch jobs, not event-driven workflows |
| Custom async loop | Requires reimplementing durability, retries, and visibility from scratch |

## Consequences

- Temporal server runs on the always-free ARM VM (no GPU required, no cost)
- All pipeline steps are Temporal activities — stateless, idempotent, independently retryable
- The `FeatureRequest` dataclass is the sole shared state object, serialized by Temporal between activities
- Human approval gates are implemented as Temporal signals
