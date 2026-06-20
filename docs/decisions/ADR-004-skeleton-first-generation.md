# ADR-004: Skeleton-First Code Generation

**Date:** 2026-06-20  
**Status:** Accepted  
**Author:** Shane Louis Slabbert

---

## Context

Initial pipeline design passed 25-32K tokens of context to the Coder Agent in a single call: 15 relevant files + blueprint + dependency manifest + coding standards. While Qwen3-Coder handles 32K context for reading, code generation at this context width produces two failure modes:

1. **Context degradation:** The model loses focus on early instructions when generating code at the end of a long context. Blueprint constraints specified at token 1,000 are forgotten by token 28,000.
2. **Lazy generation:** The model outputs `# ... rest of implementation` instead of actual code when context is near capacity.

## Decision

Split code generation into two sequential Temporal activities:

**Activity 1 — Interface Generation:**  
Generate only empty class structures, database model definitions, and function signatures with docstrings. No implementation logic. Context: blueprint + dependency manifest (~8K tokens).

**Activity 2 — Implementation (per file):**  
Fill in logic for one file at a time. Run unit tests after each file. Retry only the failing file, not the entire codebase. Context: blueprint + single file interface + 3-5 most relevant existing files (~8-12K tokens per call).

## Rationale

**Context reduction:** Per-call context drops from 32K to 8-12K. The model operates well within its reliable generation window.

**Validation gate between phases:** Interfaces are validated against the blueprint before any implementation begins. If the skeleton doesn't match the spec, it's cheaper to catch and fix at this stage than after 20 files of implementation are generated.

**Granular retry:** When a file fails tests, only that file is regenerated. The previous design regenerated the entire codebase on any test failure — wasting inference budget and risking regression in files that were already correct.

**Test-after-each-file:** Running tests after each implementation file catches errors before they propagate into dependent files. A bug in `models.py` caught immediately doesn't become a bug in `services.py`, `routes.py`, and `tests.py`.

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| Single-call full generation | Context degradation and lazy generation failure modes |
| Reduce context to 16K | Still suffers lazy generation; RAG quality degrades with fewer context files |
| Generate file-by-file without skeleton phase | No validation gate — implementation diverges from spec before catch |
| Use Aider headless | Less control over retry logic, context injection, file parsing — silent failures in headless mode |

## Consequences

- Two Temporal activities per feature instead of one (minor orchestration overhead)
- Interface validation requires a blueprint-to-skeleton comparison step (added to QA Agent)
- Per-file test runs increase total test execution time (acceptable — parallelizable)
- The Coder Agent is a direct vLLM API loop, not Aider — full control over context construction
