# Research Question and Methodology

## Principal Investigator

Shane Louis Slabbert  
Independent Researcher  
University of Maryland Global Campus (Student)

---

## Central Hypothesis

> **Do formal verification pass rates in AI-generated code predict production incident rates better than traditional test coverage metrics?**

This is a falsifiable empirical hypothesis. It will be tested through a controlled experiment using the Autonomous Software Factory as the generation and deployment platform.

---

## Background

Current literature benchmarks AI code generation quality using static upstream metrics:
- HumanEval pass@k scores
- Test coverage percentage
- Compilation success rate

No published study connects these upstream quality signals to downstream production reliability outcomes. The field currently operates on assumption: that higher test coverage or better benchmark scores produce more reliable production software.

This research closes that gap with a direct measurement study.

---

## Experimental Design

### Setup

50 software modules generated through the Autonomous Software Factory pipeline, divided into two groups:

| | Group A | Group B |
|---|---|---|
| **N** | 25 modules | 25 modules |
| **Formal Verification** | Z3 theorem prover — ENABLED | DISABLED |
| **Test Coverage Gate** | 80% minimum | 80% minimum |
| **Security Scanning** | bandit + semgrep | bandit + semgrep |
| **Hostile Audit** | DeepSeek-R1 second-model pass | DeepSeek-R1 second-model pass |
| **Shadow Deployment** | 15 minutes minimum | 15 minutes minimum |
| **Load Testing** | Poisson spike distribution | Poisson spike distribution |

All other pipeline stages are identical between groups. Formal verification is the sole independent variable.

### Module Complexity Distribution

Modules distributed across complexity buckets to ensure generalizability:

| Bucket | Group A | Group B |
|---|---|---|
| nano (CRUD API) | 5 | 5 |
| micro (multi-entity) | 5 | 5 |
| standard (auth + DB) | 7 | 7 |
| complex (real-time) | 5 | 5 |
| critical (payments/auth) | 3 | 3 |

---

## Measured Variables

### Upstream Quality Signals (Pre-Deployment)

Measured before production deployment for every module:

| Variable | Measurement Method |
|---|---|
| Formal verification pass rate | % of Z3 invariants proven (Group A) / N/A (Group B) |
| Test coverage percentage | pytest --cov output |
| Static analysis severity score | bandit + semgrep weighted severity |
| Type checking pass/fail | mypy --strict binary outcome |
| Hostile audit severity | DeepSeek-R1 JSON output (PASS/WARN/BLOCK) |
| Coder Agent retry count | Temporal workflow state |
| Semantic diff similarity | cosine similarity of blueprint vs. code embeddings |

### Downstream Reliability Outcomes (Post-Deployment, 30-Day Window)

Measured from production monitoring after deployment:

| Variable | Measurement Method |
|---|---|
| Production incident rate | Incidents per 1,000 requests (Prometheus) |
| Automated revert frequency | SRE Agent revert count |
| P99 latency anomaly rate | % of hours exceeding 2x baseline P99 |
| Error rate | HTTP 5xx rate (Prometheus) |
| Time to first incident | Hours from deployment to first revert trigger |

---

## Statistical Analysis Plan

### Primary Analysis

**Pearson correlation:** formal verification pass rate vs. production incident rate  
**Pearson correlation:** test coverage percentage vs. production incident rate  

If formal verification is a better predictor, its correlation with incident rate should be stronger (higher |r|, lower p-value) than test coverage's correlation.

### Group Comparison

**Mann-Whitney U test:** Group A vs. Group B incident rates  
(Non-parametric — no assumption of normal distribution)

**Effect size:** Cohen's d for practical significance  
**95% confidence intervals** on all correlation estimates

### Multivariate Analysis

**Logistic regression:** which upstream quality signals are significant predictors of whether a module triggers at least one production incident within 30 days.

Predictors: formal verification pass rate, test coverage %, static analysis score, hostile audit severity, retry count, semantic diff similarity  
Outcome: binary (incident / no incident in 30-day window)

---

## Null Hypothesis

H₀: Formal verification pass rate does not predict production incident rate better than test coverage percentage.

The null is retained if:
- The correlation between formal verification pass rate and incident rate is not significantly stronger than the correlation between test coverage and incident rate (overlapping 95% CIs)
- Group A and Group B incident rates are not significantly different (Mann-Whitney p > 0.05)

The null is falsified if both conditions are violated.

---

## Timeline

| Month | Activity |
|---|---|
| 1-2 | Pipeline construction (ARM VM, no GPU required) |
| 3 | Module generation begins (A10 GPU — sustained inference) |
| 4 | Module generation complete, all modules deployed |
| 5 | 30-day production measurement window |
| 6 | Statistical analysis + paper writing |
| 7 | Dataset release + paper submission to MSR 2027 / ICSE 2027 |

---

## Deliverables

1. **Benchmark Dataset** — 50-module dataset with all upstream quality signals and downstream reliability outcomes. Released as open-source CSV + JSON under MIT license on GitHub and submitted to Papers With Code.

2. **Autonomous Software Factory Pipeline** — Complete codebase for the generation, verification, and deployment pipeline. Released open-source under MIT license.

3. **Research Paper** — Full empirical study submitted to MSR 2027 or ICSE 2027. Oracle for Research acknowledged as funding institution.

4. **Reproducibility Package** — Docker images, model configuration files, and experiment scripts enabling full replication by other research groups.

---

## Limitations

- N=50 modules is a moderate sample size. Effect size estimates will carry wider confidence intervals than a larger study. This is acknowledged as a limitation in the paper.
- Modules are generated from the same pipeline, introducing potential correlated errors. This is controlled by varying complexity buckets.
- 30-day measurement window may not capture long-tail reliability failures. Noted as future work.
- Single-operator pipeline introduces potential selection bias in module specification. Mitigated by pre-committing module types and complexity distribution before generation begins.

---

## Connection to Prior Work

This research builds on the Autonomous Software Factory blueprint (Slabbert, 2026) which documents the complete system architecture and design rationale. The blueprint is available in this repository at `docs/ARCHITECTURE.md`.

The formal verification component uses Z3 (de Moura & Bjørner, 2008), the industry-standard SMT solver from Microsoft Research, consistent with its use in production verification systems at Amazon Web Services (Newcombe et al., 2015) and Meta.
