# Autonomous Software Factory

**A complete AI-driven software development lifecycle pipeline operated by a single person.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Research Status](https://img.shields.io/badge/Status-Active%20Research-blue)]()
[![Institution](https://img.shields.io/badge/Institution-UMGC-red)]()

---

## What This Is

The Autonomous Software Factory accepts a natural language description of any software application and produces a deployed, verified, self-healing application — without a development team.

**Input:** A plain English idea.  
**Output:** Deployed, load-tested, formally verified, self-healing production software.  
**Human involvement:** Specification review and occasional escalation response only.

---

## Research Question

> *Do formal verification pass rates in AI-generated code predict production incident rates better than traditional test coverage metrics?*

This is a controlled empirical study. 50 software modules will be generated through the pipeline:

- **Group A (25 modules):** Full pipeline with Z3 formal verification enabled
- **Group B (25 modules):** Pipeline with test coverage only — no formal verification

Upstream quality signals (verification pass rate, coverage %, static analysis score) will be correlated against downstream production outcomes (incident rate, revert frequency, error rate) over a 30-day measurement window.

**Publication target:** MSR 2027 / ICSE 2027

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   FACTORY OPERATOR (HUMAN)                  │
│         Approve specs · Review escalations · Collect money  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  TEMPORAL ORCHESTRATOR                       │
│   Tracks state · Retries failures · Persists across crashes │
└───┬─────────┬─────────┬─────────┬─────────┬────────────────┘
    │         │         │         │         │
┌───▼──┐ ┌───▼───┐ ┌───▼──┐ ┌───▼───┐ ┌───▼──────┐
│INTAKE│ │CODER  │ │QA    │ │SRE    │ │ARCHIVIST │
│AGENT │ │AGENT  │ │AGENT │ │AGENT  │ │AGENT     │
│      │ │       │ │      │ │       │ │          │
│Spec  │ │Direct │ │Z3 +  │ │Revert │ │Wiki +    │
│Factor│ │Agent  │ │CI/CD │ │Only   │ │ADR Store │
│      │ │Loop   │ │      │ │       │ │          │
└──────┘ └───────┘ └──────┘ └───────┘ └──────────┘
```

---

## Pipeline Flow

```
1.  Human submits raw idea
2.  Intake Agent researches domain autonomously
3.  Architectural options presented → Human selects
4.  Constraint questionnaire → Answers locked
5.  Specification blueprint generated + spec_hash assigned
6.  Skeleton-first code generation (interfaces → implementation)
7.  QA: unit tests + type checking + linting + security scan
8.  Hostile audit (second model pass — finds what tests miss)
9.  Formal verification (Z3) for critical paths
10. Shadow deployment + Poisson load test
11. SRE Fire Drill (chaos injection → verify auto-revert)
12. Human approves promotion (or auto-promote if clean)
13. Blue-green production deployment
14. SRE Agent monitors (revert-only on anomaly)
15. Archivist updates Wiki + ADRs
```

---

## Key Design Principles

### REVERT, NEVER REPAIR IN PRODUCTION
The SRE Agent at 2 AM: detects anomaly → captures forensic state → reverts to last known good → generates incident report → notifies human at 7 AM. It never patches running code.

### SPEC HASH LOCKING
Every blueprint is SHA-256 hashed at lock time. The hash is embedded in every artifact, every commit, every deployment record. If the spec changes after lock, the entire pipeline resets.

### SKELETON-FIRST GENERATION
Code generation splits into two Temporal activities:
1. Interface generation (class signatures, models, docstrings only)
2. Implementation (one file at a time, tests run after each file)

This prevents context degradation and eliminates the `// ... rest of implementation` failure mode.

### DEPENDENCY ENFORCER
Every dependency pinned to exact version. AI cannot add unapproved dependencies. Upgrades run in isolated sandboxes with full migration context injected.

### HOSTILE PRINCIPAL AUDIT
After tests pass, a second model (DeepSeek-R1) reviews the diff against the spec specifically looking for logic violations, off-by-ones in financial code, missing auth checks, and race conditions.

---

## Technology Stack

| Component | Technology |
|---|---|
| Orchestrator | Temporal (durable execution) |
| Primary Model | Qwen3-Coder-30B-A3B-AWQ (vLLM on A10 24GB) |
| Reasoning Model | DeepSeek-R1-Distill-Qwen-32B (vLLM on A100 40GB) |
| Formal Verification | Z3 Theorem Prover (Microsoft Research) |
| Property Testing | Hypothesis |
| Vector Database | ChromaDB (RAG context) |
| Load Testing | K6 with Poisson spike distribution |
| Traffic Mirroring | Istio VirtualService |
| Monitoring | Prometheus + Grafana |
| Compute | Oracle Cloud (A10 GPU + ARM always-free) |

---

## Repository Structure

```
autonomous-software-factory/
├── docs/
│   ├── ARCHITECTURE.md          # Full system design
│   ├── RESEARCH_QUESTION.md     # Formal hypothesis and methodology
│   ├── PIPELINE_FLOW.md         # Step-by-step pipeline documentation
│   ├── HARDWARE.md              # Compute requirements and justification
│   └── decisions/
│       ├── ADR-001-orchestrator-choice.md
│       ├── ADR-002-model-selection.md
│       ├── ADR-003-revert-only-sre.md
│       └── ADR-004-skeleton-first-generation.md
├── workers/
│   ├── specification/           # Intake Agent implementation
│   ├── coder/                   # Direct agent loop (vLLM)
│   ├── qa/                      # QA pipeline + hostile audit
│   ├── sre/                     # SRE Agent + fire drill
│   └── archivist/               # Wiki + ADR auto-update
├── orchestrator/                # Temporal workflow definitions
├── pipeline/                    # Shared pipeline state + cost ledger
├── cli/                         # Factory Operator Console
├── dependency_manifest.json     # Pinned dependency versions
├── CONTRIBUTING.md
└── LICENSE
```

---

## Current Status

| Phase | Status |
|---|---|
| Blueprint & Architecture | ✅ Complete |
| GitHub Repository | ✅ Active |
| Oracle Research Grant | 🔄 Application in progress |
| Temporal Orchestrator | 🔲 Pending compute |
| Specification Factory | 🔲 Pending compute |
| Coder Agent Loop | 🔲 Pending compute |
| QA Pipeline | 🔲 Pending compute |
| Experiment (50 modules) | 🔲 Pending grant award |

---

## Author

**Shane Louis Slabbert**  
Independent Researcher  
University of Maryland Global Campus (Student)  
GitHub: [your-github-username]

---

## License

MIT License — see [LICENSE](LICENSE)

All research outputs (benchmark dataset, pipeline code, paper) will be released under MIT license upon completion.
