"""Specification blueprint management and spec hash locking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from autonomous_software_factory.pipeline.models import SpecificationBlueprint


class BlueprintPhase(str, Enum):
    """Phases of the specification factory process."""

    DOMAIN_RESEARCH = "domain_research"
    ARCHITECTURAL_OPTIONS = "architectural_options"
    CONSTRAINT_QUESTIONNAIRE = "constraint_questionnaire"
    BLUEPRINT_LOCK = "blueprint_lock"


class SpecValidationError(Exception):
    """Raised when a specification blueprint fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Blueprint validation failed: {'; '.join(errors)}")


@dataclass
class FormalSpec:
    """A single formal specification for a critical domain property."""

    natural_language: str
    formal_expression: str
    precondition: str = ""
    postcondition: str = ""

    def is_complete(self) -> bool:
        return bool(self.natural_language and self.formal_expression)


@dataclass
class ArchitecturalOption:
    """A proposed architectural approach with tradeoffs."""

    name: str
    description: str
    tradeoffs: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    estimated_hours: float = 0.0
    selected: bool = False


@dataclass
class SpecificationFactory:
    """Manages the specification creation lifecycle through four phases."""

    current_phase: BlueprintPhase = BlueprintPhase.DOMAIN_RESEARCH
    blueprint: SpecificationBlueprint = field(
        default_factory=lambda: SpecificationBlueprint(title="", description="")
    )
    architectural_options: list[ArchitecturalOption] = field(default_factory=list)
    formal_specs: list[FormalSpec] = field(default_factory=list)
    constraints_answered: dict[str, str] = field(default_factory=dict)
    _phase_history: list[tuple[BlueprintPhase, datetime]] = field(default_factory=list)

    def advance_phase(self) -> BlueprintPhase:
        """Advance to the next phase. Raises ValueError if at final phase."""
        phases = list(BlueprintPhase)
        current_idx = phases.index(self.current_phase)
        if current_idx >= len(phases) - 1:
            raise ValueError("Already at final phase (blueprint_lock)")
        self._phase_history.append((self.current_phase, datetime.now(UTC)))
        self.current_phase = phases[current_idx + 1]
        return self.current_phase

    def select_architecture(self, option_index: int) -> ArchitecturalOption:
        """Select an architectural option by index."""
        if not self.architectural_options:
            raise ValueError("No architectural options available")
        if option_index < 0 or option_index >= len(self.architectural_options):
            raise IndexError(
                f"Option index {option_index} out of range "
                f"[0, {len(self.architectural_options) - 1}]"
            )
        for opt in self.architectural_options:
            opt.selected = False
        self.architectural_options[option_index].selected = True
        return self.architectural_options[option_index]

    @property
    def selected_architecture(self) -> ArchitecturalOption | None:
        for opt in self.architectural_options:
            if opt.selected:
                return opt
        return None

    def validate_for_lock(self) -> list[str]:
        """Validate that the blueprint is ready to be locked."""
        errors: list[str] = []
        if not self.blueprint.title:
            errors.append("Blueprint title is required")
        if not self.blueprint.description:
            errors.append("Blueprint description is required")
        if not self.blueprint.entities:
            errors.append("At least one entity must be defined")
        if not self.blueprint.business_rules:
            errors.append("At least one business rule must be defined")
        if self.selected_architecture is None:
            errors.append("An architectural option must be selected")
        if self.current_phase != BlueprintPhase.BLUEPRINT_LOCK:
            errors.append(
                f"Must be in BLUEPRINT_LOCK phase, currently in {self.current_phase.value}"
            )
        return errors

    def lock_blueprint(self) -> str:
        """Validate and lock the blueprint. Returns spec_hash."""
        errors = self.validate_for_lock()
        if errors:
            raise SpecValidationError(errors)
        return self.blueprint.lock()

    @property
    def phase_count(self) -> int:
        return len(self._phase_history)

    @property
    def is_locked(self) -> bool:
        return self.blueprint.is_locked


def compute_spec_hash(content: str) -> str:
    """Compute SHA-256[:12] hash for specification content."""
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def verify_artifact_hash(artifact_hash: str, blueprint: SpecificationBlueprint) -> bool:
    """Verify that an artifact's embedded spec_hash matches the blueprint."""
    if not blueprint.is_locked:
        return False
    return artifact_hash == blueprint.spec_hash
