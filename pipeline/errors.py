"""Structured exception hierarchy for the Autonomous Software Factory.

Design principles:
- Every exception carries machine-readable context (feature_id, agent, stage).
- No exception is ever silently swallowed — agents must either handle and log,
  or let the exception propagate to the Temporal orchestrator for retry/escalation.
- Severity levels map directly to pipeline actions (retry vs. block vs. escalate).

Integration:
- Complements pipeline.shared.retry.BudgetExceededError (circuit breaker level)
- Provides richer context for agent-level failures that need structured routing
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class Severity(enum.Enum):
    """Maps to pipeline response: retry, block pipeline, or escalate to human."""

    RETRYABLE = "retryable"
    BLOCKING = "blocking"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ErrorContext:
    """Structured metadata attached to every pipeline error."""

    feature_id: str
    agent: str
    stage: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)


class PipelineError(Exception):
    """Base exception for all factory pipeline errors.

    Never catch this without logging or re-raising. Silent swallowing of
    PipelineError subclasses is a policy violation.
    """

    severity: Severity = Severity.BLOCKING

    def __init__(self, message: str, context: ErrorContext) -> None:
        self.context = context
        super().__init__(f"[{context.agent}/{context.stage}] {message}")


# ---------------------------------------------------------------------------
# Retryable errors — Temporal will retry these up to max_retries
# ---------------------------------------------------------------------------


class RetryableError(PipelineError):
    """Transient failure that should be retried by the orchestrator."""

    severity = Severity.RETRYABLE


class CodeGenerationError(RetryableError):
    """Code generation produced invalid output — retry with feedback."""

    def __init__(
        self,
        message: str,
        context: ErrorContext,
        *,
        failing_file: str,
        test_output: str,
        attempt: int,
        max_attempts: int,
    ) -> None:
        self.failing_file = failing_file
        self.test_output = test_output
        self.attempt = attempt
        self.max_attempts = max_attempts
        super().__init__(
            f"{message} (attempt {attempt}/{max_attempts}, file: {failing_file})",
            context,
        )


class InferenceTimeoutError(RetryableError):
    """vLLM inference call timed out — retry with backoff."""

    pass


class TransientInfraError(RetryableError):
    """Temporary infrastructure failure (network, DB connection, etc.)."""

    pass


# ---------------------------------------------------------------------------
# Blocking errors — pipeline halts, no further retries
# ---------------------------------------------------------------------------


class BlockingError(PipelineError):
    """Pipeline must halt — cannot proceed without intervention."""

    severity = Severity.BLOCKING


class QABlockError(BlockingError):
    """QA stage produced a BLOCK verdict — pipeline halts for review."""

    def __init__(
        self,
        message: str,
        context: ErrorContext,
        *,
        stage: str,
        findings: list[dict[str, Any]],
    ) -> None:
        self.qa_stage = stage
        self.findings = findings
        super().__init__(
            f"QA BLOCK at stage '{stage}': {message} ({len(findings)} finding(s))",
            context,
        )


class SecurityBlockError(QABlockError):
    """High-severity security finding — immediate pipeline halt."""

    pass


class HostileAuditBlockError(QABlockError):
    """Hostile audit returned BLOCK severity — code contradicts spec."""

    pass


class SpecHashMismatchError(BlockingError):
    """Spec hash changed after lock — entire pipeline must reset."""

    def __init__(
        self,
        context: ErrorContext,
        *,
        expected_hash: str,
        actual_hash: str,
    ) -> None:
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Spec hash mismatch: expected {expected_hash[:12]}, "
            f"got {actual_hash[:12]}. Pipeline reset required.",
            context,
        )


class SemanticDriftError(BlockingError):
    """Generated code semantically diverges from the specification."""

    def __init__(
        self,
        message: str,
        context: ErrorContext,
        *,
        similarity_score: float,
        threshold: float,
    ) -> None:
        self.similarity_score = similarity_score
        self.threshold = threshold
        super().__init__(
            f"{message} (similarity={similarity_score:.3f}, threshold={threshold})",
            context,
        )


class CostBudgetExceededError(BlockingError):
    """Feature cost exceeded budget — hard stop, escalate to human."""

    def __init__(
        self,
        context: ErrorContext,
        *,
        metric: str,
        current_value: float,
        limit: float,
    ) -> None:
        self.metric = metric
        self.current_value = current_value
        self.limit = limit
        super().__init__(
            f"Cost budget exceeded: {metric}={current_value} > limit={limit}",
            context,
        )


class MaxRetriesExhaustedError(BlockingError):
    """All retry attempts exhausted — escalate to human."""

    def __init__(
        self,
        context: ErrorContext,
        *,
        attempts: int,
        last_error: Exception | None = None,
    ) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Max retries exhausted ({attempts} attempts). "
            f"Last error: {last_error!r}",
            context,
        )


class FireDrillFailedError(BlockingError):
    """Fire drill failed — DO NOT promote to production."""

    def __init__(
        self,
        context: ErrorContext,
        *,
        fault_type: str,
        detection_time_s: float | None = None,
        revert_time_s: float | None = None,
    ) -> None:
        self.fault_type = fault_type
        self.detection_time_s = detection_time_s
        self.revert_time_s = revert_time_s
        parts = [f"Fire drill FAILED for fault '{fault_type}'"]
        if detection_time_s is not None:
            parts.append(f"detection={detection_time_s:.1f}s")
        if revert_time_s is not None:
            parts.append(f"revert={revert_time_s:.1f}s")
        super().__init__(", ".join(parts), context)


# ---------------------------------------------------------------------------
# Critical errors — immediate escalation to human operator
# ---------------------------------------------------------------------------


class CriticalError(PipelineError):
    """Critical failure requiring immediate human intervention."""

    severity = Severity.CRITICAL


class RevertFailedError(CriticalError):
    """Production revert FAILED — human must intervene immediately."""

    def __init__(
        self,
        context: ErrorContext,
        *,
        deployment_id: str,
        revert_target: str,
        reason: str,
    ) -> None:
        self.deployment_id = deployment_id
        self.revert_target = revert_target
        self.reason = reason
        super().__init__(
            f"REVERT FAILED for deployment {deployment_id}. "
            f"Target: {revert_target}. Reason: {reason}. "
            "IMMEDIATE HUMAN INTERVENTION REQUIRED.",
            context,
        )


class DataCorruptionError(CriticalError):
    """Data integrity violation detected — stop all operations."""

    pass


class MigrationRollbackFailedError(CriticalError):
    """Database migration rollback failed — manual recovery needed."""

    pass
