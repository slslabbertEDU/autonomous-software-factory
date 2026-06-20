"""SRE Agent — self-healing operations with proper error escalation.

Primary directive: REVERT, NEVER REPAIR IN PRODUCTION.

Critical error handling improvement: when a revert FAILS, the original
ARCHITECTURE.md pseudocode simply "notifies human." This implementation
raises RevertFailedError (severity=CRITICAL) which triggers immediate
escalation through the entire call chain — the human is notified with
full forensic context, not just a message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pipeline.errors import (
    FireDrillFailedError,
    RevertFailedError,
)
from pipeline.shared.config import get_config
from workers.base import BaseAgent

if TYPE_CHECKING:
    from pipeline.shared.models import FeatureRequest, FireDrillResult, IncidentReport

logger = logging.getLogger(__name__)


FIRE_DRILL_DETECTION_TIMEOUT_S = get_config().fire_drill.detection_timeout_seconds
FIRE_DRILL_REVERT_TIMEOUT_S = get_config().fire_drill.revert_timeout_seconds


@dataclass
class AnomalySignal:
    """A detected production anomaly."""

    metric: str
    current_value: float
    threshold: float
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ForensicCapture:
    """Forensic state captured before revert."""

    logs: str = ""
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
    active_transactions: list[str] = field(default_factory=list)
    memory_dump_path: str = ""
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SREAgent(BaseAgent):
    """SRE Agent: monitors production and reverts on anomaly.

    Error handling guarantees:
    - Anomaly detection ALWAYS logs the specific metric and threshold
    - Forensic capture happens BEFORE revert (never lost on failure)
    - Revert failure raises CriticalError with full forensic context
    - Human notification includes actionable information, not just "something failed"
    """

    agent_name = "sre_agent"

    async def execute(self, feature: FeatureRequest) -> FeatureRequest:
        """Monitor production deployment for anomalies."""
        logger.info(
            "SRE Agent monitoring deployment %s for feature %s",
            feature.production_deployment_id,
            feature.id,
        )
        return feature

    async def detect_anomaly(
        self, feature: FeatureRequest, metrics: dict[str, float]
    ) -> AnomalySignal | None:
        """Check current metrics against revert thresholds.

        Returns the anomaly signal if a threshold is breached.
        Never silently ignores a threshold breach.
        """
        revert_thresholds = get_config().revert_thresholds
        threshold_map = {
            "error_rate": revert_thresholds.error_rate,
            "p99_latency_increase": revert_thresholds.p99_latency_increase,
            "cpu_sustained": revert_thresholds.cpu_sustained,
            "memory_leak_rate": revert_thresholds.memory_leak_rate,
        }

        for metric, threshold in threshold_map.items():
            current = metrics.get(metric)
            if current is None:
                logger.warning(
                    "Metric '%s' missing from monitoring data for feature %s. "
                    "This should not happen — investigate metric collection.",
                    metric,
                    feature.id,
                )
                continue

            if current > threshold:
                signal = AnomalySignal(
                    metric=metric,
                    current_value=current,
                    threshold=threshold,
                )
                logger.error(
                    "ANOMALY DETECTED for feature %s: %s=%.4f > threshold=%.4f",
                    feature.id,
                    metric,
                    current,
                    threshold,
                )
                return signal

        return None

    async def execute_revert_protocol(
        self,
        feature: FeatureRequest,
        anomaly: AnomalySignal,
    ) -> IncidentReport:
        """Execute the full revert protocol.

        Steps (per ARCHITECTURE.md "2 AM protocol"):
        1. Capture forensic state (BEFORE revert — never lost)
        2. Revert to last known good deployment
        3. Verify revert succeeded
        4. Generate incident report

        If revert FAILS: raises RevertFailedError (CRITICAL) with full
        forensic context. This is the most severe error in the system —
        it triggers immediate human escalation regardless of time.
        """
        context = self._make_context(feature, "revert_protocol")

        # Step 1: Capture forensic state BEFORE any revert action
        logger.info(
            "Capturing forensic state for feature %s before revert",
            feature.id,
        )
        forensics = await self._capture_forensic_state(feature)

        # Step 2: Execute revert
        revert_target = self._determine_revert_target(feature)
        logger.info(
            "Reverting deployment %s to target %s for feature %s",
            feature.production_deployment_id,
            revert_target,
            feature.id,
        )

        revert_success = await self._execute_revert(feature, revert_target)

        if not revert_success:
            # CRITICAL: Revert failed — immediate human intervention required
            logger.critical(
                "REVERT FAILED for deployment %s (feature %s). "
                "Human intervention REQUIRED.",
                feature.production_deployment_id,
                feature.id,
            )
            raise RevertFailedError(
                context=context,
                deployment_id=feature.production_deployment_id,
                revert_target=revert_target,
                reason=(
                    f"Automatic revert failed. Anomaly: {anomaly.metric}="
                    f"{anomaly.current_value:.4f} (threshold={anomaly.threshold}). "
                    f"Forensic data captured at {forensics.captured_at.isoformat()}."
                ),
            )

        # Step 3: Verify revert succeeded
        verified = await self._verify_revert(feature, revert_target)
        if not verified:
            logger.critical(
                "Revert executed but VERIFICATION FAILED for feature %s",
                feature.id,
            )
            raise RevertFailedError(
                context=context,
                deployment_id=feature.production_deployment_id,
                revert_target=revert_target,
                reason=(
                    "Revert command succeeded but post-revert verification failed. "
                    "System may be in inconsistent state."
                ),
            )

        # Step 4: Generate incident report
        from pipeline.shared.models import IncidentReport as IncidentReportModel

        report = IncidentReportModel(
            incident_id=f"inc_{feature.id}_{anomaly.detected_at.strftime('%Y%m%d%H%M%S')}",
            detected_at=anomaly.detected_at,
            reverted_at=datetime.now(UTC),
            trigger=anomaly.metric,
            forensic_state={
                "logs": forensics.logs[:10000],
                "active_transactions": ",".join(forensics.active_transactions),
            },
            revert_successful=True,
        )

        feature.incident_history.append(report)
        logger.info(
            "Revert protocol completed for feature %s. "
            "Incident report: %s. Human will be notified at next check-in.",
            feature.id,
            report.incident_id,
        )
        return report

    async def run_fire_drill(
        self,
        feature: FeatureRequest,
        fault_type: str,
    ) -> FireDrillResult:
        """Run a fire drill to validate SRE readiness.

        The fire drill must PASS before any production promotion.
        Failure raises FireDrillFailedError — the feature is NEVER
        promoted after a failed drill (this is non-negotiable).
        """
        context = self._make_context(feature, "fire_drill")
        logger.info(
            "Starting fire drill (fault=%s) for feature %s",
            fault_type,
            feature.id,
        )

        # Inject fault
        await self._inject_fault(feature, fault_type)

        # Measure detection time
        detection_time = await self._measure_detection_time(feature)
        if detection_time is None or detection_time > FIRE_DRILL_DETECTION_TIMEOUT_S:
            from pipeline.shared.models import FireDrillResult as FireDrillResultModel

            result = FireDrillResultModel(
                fault_type=fault_type,
                detection_time_seconds=detection_time or -1,
                revert_time_seconds=0,
                revert_successful=False,
                passed=False,
            )
            feature.fire_drill_result = result
            raise FireDrillFailedError(
                context=context,
                fault_type=fault_type,
                detection_time_s=detection_time,
            )

        # Measure revert time
        revert_time = await self._measure_revert_time(feature)
        if revert_time is None or revert_time > FIRE_DRILL_REVERT_TIMEOUT_S:
            from pipeline.shared.models import FireDrillResult as FireDrillResultModel

            result = FireDrillResultModel(
                fault_type=fault_type,
                detection_time_seconds=detection_time,
                revert_time_seconds=revert_time or -1,
                revert_successful=False,
                passed=False,
            )
            feature.fire_drill_result = result
            raise FireDrillFailedError(
                context=context,
                fault_type=fault_type,
                detection_time_s=detection_time,
                revert_time_s=revert_time,
            )

        from pipeline.shared.models import FireDrillResult as FireDrillResultModel

        result = FireDrillResultModel(
            fault_type=fault_type,
            detection_time_seconds=detection_time,
            revert_time_seconds=revert_time,
            revert_successful=True,
            passed=True,
        )
        feature.fire_drill_result = result
        logger.info(
            "Fire drill PASSED for feature %s: detection=%.1fs, revert=%.1fs",
            feature.id,
            detection_time,
            revert_time,
        )
        return result

    # ------------------------------------------------------------------
    # Private methods (placeholders for actual infrastructure calls)
    # ------------------------------------------------------------------

    async def _capture_forensic_state(
        self, feature: FeatureRequest
    ) -> ForensicCapture:
        """Capture full forensic state before revert."""
        logger.debug(
            "Capturing forensics for deployment %s",
            feature.production_deployment_id,
        )
        return ForensicCapture()

    def _determine_revert_target(self, feature: FeatureRequest) -> str:
        """Determine the last known good deployment to revert to."""
        return f"pre_{feature.production_deployment_id}"

    async def _execute_revert(
        self, feature: FeatureRequest, target: str
    ) -> bool:
        """Execute the actual revert operation. Returns success status."""
        logger.info("Executing revert to %s", target)
        return True

    async def _verify_revert(
        self, feature: FeatureRequest, target: str
    ) -> bool:
        """Verify the revert completed successfully."""
        logger.info("Verifying revert to %s", target)
        return True

    async def _inject_fault(
        self, feature: FeatureRequest, fault_type: str
    ) -> None:
        """Inject a fault for fire drill testing."""
        logger.info("Injecting fault: %s", fault_type)

    async def _measure_detection_time(
        self, feature: FeatureRequest
    ) -> float | None:
        """Measure how long it takes to detect the injected fault."""
        return 30.0  # Placeholder

    async def _measure_revert_time(
        self, feature: FeatureRequest
    ) -> float | None:
        """Measure how long it takes to revert after detection."""
        return 60.0  # Placeholder
