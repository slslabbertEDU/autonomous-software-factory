"""Cost circuit breaker and per-feature cost tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class CostLimitExceededError(Exception):
    """Raised when a cost limit is breached."""

    def __init__(self, limit_name: str, current: float, maximum: float) -> None:
        self.limit_name = limit_name
        self.current = current
        self.maximum = maximum
        super().__init__(
            f"Cost limit '{limit_name}' exceeded: {current:.2f} / {maximum:.2f}"
        )


class CostCategory(str, Enum):
    """Categories of cost tracked per feature."""

    INFERENCE = "inference"
    GPU_COMPUTE = "gpu_compute"
    STORAGE = "storage"
    NETWORK = "network"
    EXTERNAL_API = "external_api"


@dataclass
class CostEntry:
    """Single cost entry in the ledger."""

    category: CostCategory
    amount_usd: float
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    agent: str = ""


@dataclass
class CostLimits:
    """Hard limits for the cost circuit breaker."""

    max_inference_calls_per_feature: int = 50
    max_gpu_minutes_per_feature: float = 120.0
    max_retries_global: int = 3
    max_total_cost_usd: float = 50.0

    def check_inference_calls(self, current: int) -> bool:
        return current <= self.max_inference_calls_per_feature

    def check_gpu_minutes(self, current: float) -> bool:
        return current <= self.max_gpu_minutes_per_feature

    def check_retries(self, current: int) -> bool:
        return current <= self.max_retries_global

    def check_total_cost(self, current: float) -> bool:
        return current <= self.max_total_cost_usd


@dataclass
class FeatureCostLedger:
    """Per-feature cost tracking with circuit breaker."""

    feature_id: str
    limits: CostLimits = field(default_factory=CostLimits)
    entries: list[CostEntry] = field(default_factory=list)
    inference_call_count: int = 0
    gpu_minutes_used: float = 0.0
    global_retry_count: int = 0
    _tripped: bool = False
    _trip_reason: str | None = None

    @property
    def total_cost_usd(self) -> float:
        return sum(entry.amount_usd for entry in self.entries)

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    @property
    def trip_reason(self) -> str | None:
        return self._trip_reason

    def record_cost(self, category: CostCategory, amount_usd: float,
                    description: str, agent: str = "") -> None:
        """Record a cost entry. Raises CostLimitExceededError if total budget is breached."""
        entry = CostEntry(
            category=category,
            amount_usd=amount_usd,
            description=description,
            agent=agent,
        )
        self.entries.append(entry)
        new_total = self.total_cost_usd
        if not self.limits.check_total_cost(new_total):
            self._trip("total_cost_usd", new_total, self.limits.max_total_cost_usd)

    def record_inference_call(self) -> None:
        """Record an inference call. Raises CostLimitExceededError if limit is breached."""
        self.inference_call_count += 1
        if not self.limits.check_inference_calls(self.inference_call_count):
            self._trip(
                "inference_calls",
                float(self.inference_call_count),
                float(self.limits.max_inference_calls_per_feature),
            )

    def record_gpu_minutes(self, minutes: float) -> None:
        """Record GPU time usage. Raises CostLimitExceededError if limit is breached."""
        self.gpu_minutes_used += minutes
        if not self.limits.check_gpu_minutes(self.gpu_minutes_used):
            self._trip(
                "gpu_minutes",
                self.gpu_minutes_used,
                self.limits.max_gpu_minutes_per_feature,
            )

    def record_retry(self) -> None:
        """Record a global retry. Raises CostLimitExceededError if limit is breached."""
        self.global_retry_count += 1
        if not self.limits.check_retries(self.global_retry_count):
            self._trip(
                "global_retries",
                float(self.global_retry_count),
                float(self.limits.max_retries_global),
            )

    def cost_by_category(self) -> dict[CostCategory, float]:
        """Aggregate costs by category."""
        totals: dict[CostCategory, float] = {}
        for entry in self.entries:
            totals[entry.category] = totals.get(entry.category, 0.0) + entry.amount_usd
        return totals

    def cost_by_agent(self) -> dict[str, float]:
        """Aggregate costs by agent."""
        totals: dict[str, float] = {}
        for entry in self.entries:
            key = entry.agent or "unknown"
            totals[key] = totals.get(key, 0.0) + entry.amount_usd
        return totals

    def _trip(self, limit_name: str, current: float, maximum: float) -> None:
        """Trip the circuit breaker."""
        self._tripped = True
        self._trip_reason = f"{limit_name}: {current:.2f} / {maximum:.2f}"
        raise CostLimitExceededError(limit_name, current, maximum)
