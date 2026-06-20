"""Temporal activity helpers and common workflow patterns.

All agents are Temporal activities. This module provides:
- Activity wrappers with cost tracking and metrics
- Timeout calculation based on complexity bucket
- Heartbeat patterns for long-running activities
- Error classification for retry vs. escalation decisions
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, TypeVar

from temporalio import activity

from pipeline.shared.config import get_config
from pipeline.shared.cost import CostTracker
from pipeline.shared.metrics import pipeline_stage_duration, pipeline_stage_status
from pipeline.shared.models import (
    COMPLEXITY_TARGET_HOURS,
    ComplexityBucket,
    FeatureRequest,
)
from pipeline.shared.retry import BudgetExceededError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class EscalationRequiredError(Exception):
    """Raised when human intervention is needed."""

    def __init__(self, reason: str, feature_id: str) -> None:
        self.reason = reason
        self.feature_id = feature_id
        super().__init__(f"Escalation required for {feature_id}: {reason}")


def get_activity_timeout(bucket: ComplexityBucket) -> timedelta:
    """Calculate activity timeout based on complexity bucket.

    Used by the orchestrator when scheduling activities to set
    appropriate start-to-close timeouts per the Architecture spec.
    """
    hours = COMPLEXITY_TARGET_HOURS[bucket]
    return timedelta(hours=hours)


def get_heartbeat_interval(bucket: ComplexityBucket) -> timedelta:
    """Calculate heartbeat interval (1/10 of timeout)."""
    timeout = get_activity_timeout(bucket)
    return timedelta(seconds=timeout.total_seconds() / 10)


def tracked_activity(
    stage_name: str,
) -> Callable[
    [Callable[..., Awaitable[FeatureRequest]]],
    Callable[..., Awaitable[FeatureRequest]],
]:
    """Decorator for Temporal activities with metrics and cost tracking.

    Wraps all agent activities with:
    - Duration measurement (Prometheus histogram)
    - Status tracking (success/failure/escalation)
    - Cost budget checking before execution
    - Automatic heartbeating

    Usage:
        @activity.defn
        @tracked_activity("coder_implement_file")
        async def run_coder_agent_implement_file(
            feature: FeatureRequest, file_path: str
        ) -> FeatureRequest:
            ...
    """

    def decorator(
        func: Callable[..., Awaitable[FeatureRequest]],
    ) -> Callable[..., Awaitable[FeatureRequest]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> FeatureRequest:
            # Extract feature request from args
            feature: FeatureRequest | None = None
            for arg in args:
                if isinstance(arg, FeatureRequest):
                    feature = arg
                    break
            if feature is None:
                for v in kwargs.values():
                    if isinstance(v, FeatureRequest):
                        feature = v
                        break

            bucket_label = feature.complexity_bucket.value if feature else "unknown"
            start = time.monotonic()
            status = "success"

            try:
                # Check cost budget before proceeding
                if feature:
                    cost_tracker = CostTracker(
                        feature_id=feature.id,
                        limits=get_config().cost_limits,
                    )
                    cost_tracker.check_budget()

                result = await func(*args, **kwargs)
                return result

            except BudgetExceededError as exc:
                status = "budget_exceeded"
                logger.error("Budget exceeded in %s: %s", stage_name, exc)
                if feature:
                    feature.awaiting_human_approval = True
                    feature.escalation_reason = str(exc)
                raise EscalationRequiredError(
                    reason=str(exc),
                    feature_id=feature.id if feature else "unknown",
                ) from exc

            except Exception:
                status = "failure"
                raise

            finally:
                elapsed = time.monotonic() - start
                pipeline_stage_duration.labels(
                    stage=stage_name, complexity_bucket=bucket_label
                ).observe(elapsed)
                pipeline_stage_status.labels(stage=stage_name, status=status).inc()

        return wrapper

    return decorator


async def heartbeat_loop(
    interval: timedelta,
    details: str = "",
) -> None:
    """Send periodic heartbeats during long-running activities.

    Called within activity implementations to prevent timeout.
    """
    activity.heartbeat(details)


def classify_error(exc: Exception) -> str:
    """Classify an error for retry vs. escalation decisions.

    Returns:
        "retry" — transient error, safe to retry
        "escalate" — requires human intervention
        "fatal" — unrecoverable, abort pipeline
    """
    if isinstance(exc, BudgetExceededError):
        return "escalate"
    if isinstance(exc, EscalationRequiredError):
        return "escalate"
    if isinstance(exc, ConnectionError | TimeoutError | OSError):
        return "retry"
    return "fatal"
