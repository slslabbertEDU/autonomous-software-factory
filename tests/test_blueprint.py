"""Unit tests for specification blueprint and spec hash locking."""

import pytest

from autonomous_software_factory.pipeline.models import SpecificationBlueprint
from autonomous_software_factory.workers.specification.blueprint import (
    ArchitecturalOption,
    BlueprintPhase,
    FormalSpec,
    SpecificationFactory,
    SpecValidationError,
    compute_spec_hash,
    verify_artifact_hash,
)


class TestComputeSpecHash:
    def test_hash_is_12_chars(self) -> None:
        result = compute_spec_hash("test content")
        assert len(result) == 12

    def test_hash_is_deterministic(self) -> None:
        assert compute_spec_hash("hello") == compute_spec_hash("hello")

    def test_different_content_different_hash(self) -> None:
        assert compute_spec_hash("a") != compute_spec_hash("b")

    def test_hash_is_hex(self) -> None:
        result = compute_spec_hash("content")
        assert all(c in "0123456789abcdef" for c in result)


class TestVerifyArtifactHash:
    def test_matching_hash_passes(self) -> None:
        bp = SpecificationBlueprint(
            title="Test", description="Desc", entities=["A"], business_rules=["R"]
        )
        spec_hash = bp.lock()
        assert verify_artifact_hash(spec_hash, bp)

    def test_wrong_hash_fails(self) -> None:
        bp = SpecificationBlueprint(
            title="Test", description="Desc", entities=["A"], business_rules=["R"]
        )
        bp.lock()
        assert not verify_artifact_hash("wronghash123", bp)

    def test_unlocked_blueprint_fails(self) -> None:
        bp = SpecificationBlueprint(title="Test", description="Desc")
        assert not verify_artifact_hash("anyhash12345", bp)


class TestFormalSpec:
    def test_complete_spec(self) -> None:
        spec = FormalSpec(
            natural_language="Balance >= 0",
            formal_expression="forall a: balance(a) >= 0",
            precondition="withdraw requires balance >= amount",
            postcondition="balance' = balance - amount",
        )
        assert spec.is_complete()

    def test_incomplete_spec_no_expression(self) -> None:
        spec = FormalSpec(natural_language="Balance >= 0", formal_expression="")
        assert not spec.is_complete()

    def test_incomplete_spec_no_natural(self) -> None:
        spec = FormalSpec(natural_language="", formal_expression="forall x: x >= 0")
        assert not spec.is_complete()


class TestArchitecturalOption:
    def test_default_not_selected(self) -> None:
        opt = ArchitecturalOption(name="REST", description="REST API")
        assert not opt.selected

    def test_with_tradeoffs(self) -> None:
        opt = ArchitecturalOption(
            name="GraphQL",
            description="GraphQL API",
            tradeoffs=["Flexible queries", "Complex setup"],
            estimated_cost_usd=100.0,
            estimated_hours=16.0,
        )
        assert len(opt.tradeoffs) == 2
        assert opt.estimated_cost_usd == 100.0


class TestSpecificationFactory:
    def _make_ready_factory(self) -> SpecificationFactory:
        """Create a factory ready for locking."""
        factory = SpecificationFactory()
        factory.blueprint = SpecificationBlueprint(
            title="Test Service",
            description="A test service",
            entities=["User", "Order"],
            business_rules=["Users must be authenticated"],
        )
        factory.architectural_options = [
            ArchitecturalOption(name="REST", description="REST API"),
            ArchitecturalOption(name="GraphQL", description="GraphQL API"),
        ]
        factory.select_architecture(0)
        # Advance to lock phase
        factory.advance_phase()  # -> architectural_options
        factory.advance_phase()  # -> constraint_questionnaire
        factory.advance_phase()  # -> blueprint_lock
        return factory

    def test_initial_phase_is_domain_research(self) -> None:
        factory = SpecificationFactory()
        assert factory.current_phase == BlueprintPhase.DOMAIN_RESEARCH

    def test_advance_phase_sequence(self) -> None:
        factory = SpecificationFactory()
        assert factory.advance_phase() == BlueprintPhase.ARCHITECTURAL_OPTIONS
        assert factory.advance_phase() == BlueprintPhase.CONSTRAINT_QUESTIONNAIRE
        assert factory.advance_phase() == BlueprintPhase.BLUEPRINT_LOCK

    def test_advance_past_final_phase_raises(self) -> None:
        factory = SpecificationFactory()
        factory.advance_phase()
        factory.advance_phase()
        factory.advance_phase()
        with pytest.raises(ValueError, match="final phase"):
            factory.advance_phase()

    def test_phase_history_tracked(self) -> None:
        factory = SpecificationFactory()
        factory.advance_phase()
        factory.advance_phase()
        assert factory.phase_count == 2

    def test_select_architecture(self) -> None:
        factory = SpecificationFactory()
        factory.architectural_options = [
            ArchitecturalOption(name="A", description="Option A"),
            ArchitecturalOption(name="B", description="Option B"),
        ]
        selected = factory.select_architecture(1)
        assert selected.name == "B"
        assert factory.selected_architecture is not None
        assert factory.selected_architecture.name == "B"

    def test_select_architecture_deselects_previous(self) -> None:
        factory = SpecificationFactory()
        factory.architectural_options = [
            ArchitecturalOption(name="A", description="A"),
            ArchitecturalOption(name="B", description="B"),
        ]
        factory.select_architecture(0)
        factory.select_architecture(1)
        assert not factory.architectural_options[0].selected
        assert factory.architectural_options[1].selected

    def test_select_architecture_invalid_index(self) -> None:
        factory = SpecificationFactory()
        factory.architectural_options = [
            ArchitecturalOption(name="A", description="A"),
        ]
        with pytest.raises(IndexError):
            factory.select_architecture(5)

    def test_select_architecture_no_options(self) -> None:
        factory = SpecificationFactory()
        with pytest.raises(ValueError, match="No architectural options"):
            factory.select_architecture(0)

    def test_validate_for_lock_all_errors(self) -> None:
        factory = SpecificationFactory()
        errors = factory.validate_for_lock()
        assert len(errors) >= 4  # title, desc, entities, rules, architecture, phase

    def test_validate_for_lock_passes(self) -> None:
        factory = self._make_ready_factory()
        errors = factory.validate_for_lock()
        assert errors == []

    def test_lock_blueprint_success(self) -> None:
        factory = self._make_ready_factory()
        spec_hash = factory.lock_blueprint()
        assert len(spec_hash) == 12
        assert factory.is_locked

    def test_lock_blueprint_fails_validation(self) -> None:
        factory = SpecificationFactory()
        with pytest.raises(SpecValidationError) as exc_info:
            factory.lock_blueprint()
        assert len(exc_info.value.errors) > 0

    def test_is_locked_property(self) -> None:
        factory = SpecificationFactory()
        assert not factory.is_locked
        factory = self._make_ready_factory()
        factory.lock_blueprint()
        assert factory.is_locked
