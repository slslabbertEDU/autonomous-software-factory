# Contributing

This is an active research project. The codebase is under construction pending Oracle Cloud GPU allocation.

## Current Status

The architecture and research methodology are fully specified. Implementation begins upon grant award. See `docs/ARCHITECTURE.md` for the complete system design and `docs/RESEARCH_QUESTION.md` for the experimental methodology.

## Repository Structure

```
docs/           System documentation and ADRs
workers/        Agent implementations (in progress)
orchestrator/   Temporal workflow definitions (in progress)
pipeline/       Shared state objects and cost ledger (in progress)
cli/            Factory Operator Console (in progress)
```

## Design Principles

Before contributing, read the four ADRs in `docs/decisions/`. They explain the non-negotiable architectural decisions:

- ADR-001: Why Temporal (not Celery, not Airflow)
- ADR-002: Why these specific models (not GPT-4o, not smaller models)
- ADR-003: Why revert-only SRE (never repair in production)
- ADR-004: Why skeleton-first generation (not single-call)

## Code Standards

- Python 3.11+
- All dependencies pinned to exact versions in `dependency_manifest.json`
- Type annotations required (`mypy --strict` must pass)
- 80% test coverage minimum
- Every new component requires an ADR

## Contact

Shane Louis Slabbert — open an issue for questions.
