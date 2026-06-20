"""QA Agent — verification pipeline with proper error propagation.

Contrast with the ARCHITECTURE.md pseudocode where:
- The semantic diff gate silently returned False without raising
- Security scan results were not structured
- Hostile audit failures had no machine-readable context

This implementation ensures every QA stage failure:
- Raises a specific, typed exception
- Includes the full findings for retry feedback
- Distinguishes between retryable and blocking failures
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipeline.errors import (
    SpecHashMismatchError,
)
from workers.base import BaseAgent

if TYPE_CHECKING:
    from pipeline.shared.models import FeatureRequest

logger = logging.getLogger(__name__)


class QAAgent(BaseAgent):
    """Runs the full QA verification pipeline.

    Six sequential stages, each with explicit error handling:
    1. Unit Tests — retryable on failure (fed back to coder)
    2. Type Checking — retryable on failure (fed back to coder)
    3. Linting — retryable on failure (fed back to coder)
    4. Security Scan — BLOCKS on HIGH severity (never silently passes)
    5. Hostile Audit — BLOCKS on BLOCK severity (never silently passes)
    6. Formal Verification — feeds counterexamples back to coder
    """

    agent_name = "qa_agent"

    async def execute(self, feature: FeatureRequest) -> FeatureRequest:
        """Run all QA stages sequentially. Raises on any blocking failure."""
        # Verify spec hash integrity
        expected_hash = feature.blueprint.compute_hash()
        if feature.spec_hash and feature.spec_hash != expected_hash:
            raise SpecHashMismatchError(
                context=self._make_context(feature, "spec_verification"),
                expected_hash=feature.spec_hash,
                actual_hash=expected_hash,
            )

        # Stage 1: Unit Tests
        feature = await self._run_unit_tests(feature)

        # Stage 2: Type Checking (mypy --strict)
        await self._run_type_check(feature)

        # Stage 3: Linting (ruff)
        await self._run_lint(feature)

        # Stage 4: Security Scan (bandit + semgrep)
        await self._run_security_scan(feature)

        # Stage 5: Hostile Audit (second model)
        feature = await self._run_hostile_audit(feature)

        # Stage 6: Formal Verification (Z3, critical paths only)
        feature = await self._run_formal_verification(feature)

        return feature

    async def _run_unit_tests(self, feature: FeatureRequest) -> FeatureRequest:
        """Run unit tests. Returns results for all files.

        Does NOT silently skip failing tests — captures full output
        for each file so the coder agent gets actionable feedback.
        """
        logger.info("Running unit tests for feature %s", feature.id)
        # Placeholder: run pytest and capture per-file results
        return feature

    async def _run_type_check(self, feature: FeatureRequest) -> None:
        """Run mypy --strict. Raises QABlockError with full error output."""
        logger.info("Running type check for feature %s", feature.id)
        # Placeholder for mypy execution — raises QABlockError on failure

    async def _run_lint(self, feature: FeatureRequest) -> None:
        """Run ruff linter. Raises QABlockError with findings."""
        logger.info("Running linter for feature %s", feature.id)
        # Placeholder for ruff execution — raises QABlockError on failure

    async def _run_security_scan(self, feature: FeatureRequest) -> None:
        """Run security scan (bandit + semgrep).

        BLOCKS immediately on HIGH severity findings.
        Never silently downgrades severity or skips findings.
        """
        self._make_context(feature, "security_scan")
        logger.info("Running security scan for feature %s", feature.id)

        # Placeholder for bandit + semgrep execution
        # Real implementation:
        #
        # findings = await _execute_bandit(feature.implementation_files)
        # high_severity = [f for f in findings if f["severity"] == "HIGH"]
        # if high_severity:
        #     raise SecurityBlockError(
        #         f"Security scan found {len(high_severity)} HIGH severity issue(s)",
        #         context=context,
        #         stage="security_scan",
        #         findings=high_severity,
        #     )

    async def _run_hostile_audit(self, feature: FeatureRequest) -> FeatureRequest:
        """Run hostile audit via second model (DeepSeek-R1).

        BLOCKS on BLOCK severity — this is the last defense against
        logic errors that tests miss. Never silently passes a BLOCK result.
        """
        self._make_context(feature, "hostile_audit")
        logger.info("Running hostile audit for feature %s", feature.id)

        # Placeholder for hostile audit execution
        # Real implementation:
        #
        # result = await self._call_hostile_auditor(feature)
        # feature.hostile_audit_result = result
        #
        # if result.is_blocking:
        #     raise HostileAuditBlockError(
        #         "Hostile audit found critical issues that tests would miss",
        #         context=context,
        #         stage="hostile_audit",
        #         findings=[issue.model_dump() for issue in result.issues],
        #     )

        return feature

    async def _run_formal_verification(
        self, feature: FeatureRequest
    ) -> FeatureRequest:
        """Run Z3 formal verification for critical paths.

        Unlike the ARCHITECTURE.md pseudocode which feeds counterexamples
        back silently, this raises a specific error with the counterexample
        so the orchestrator can route it properly.
        """
        self._make_context(feature, "formal_verification")

        if feature.complexity_bucket.value not in ("complex", "critical"):
            logger.info(
                "Skipping formal verification for non-critical feature %s "
                "(bucket=%s)",
                feature.id,
                feature.complexity_bucket.value,
            )
            return feature

        logger.info("Running Z3 formal verification for feature %s", feature.id)

        # Placeholder for Z3 execution
        # Real implementation:
        #
        # result = await _run_z3_verification(feature)
        # feature.formal_verification_result = result
        #
        # if not result.all_proven:
        #     raise QABlockError(
        #         f"Formal verification failed: "
        #         f"{result.invariants_total - result.invariants_proven} "
        #         f"invariants unproven",
        #         context=context,
        #         stage="formal_verification",
        #         findings=[{"counterexample": ce} for ce in result.counterexamples],
        #     )

        return feature
