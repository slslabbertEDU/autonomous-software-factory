"""Extended tests for pipeline/shared/models.py — covers lines 279, 284."""

import pytest

from pipeline.shared.models import FeatureRequest


class TestFeatureRequestFieldOwnership:
    def test_unknown_field_raises(self) -> None:
        fr = FeatureRequest(id="feat_001")
        with pytest.raises(ValueError, match="Unknown field"):
            fr.get_field_owner("nonexistent_field")

    def test_field_without_dict_extra_returns_unknown(self) -> None:
        """Fields whose json_schema_extra is not a dict return 'unknown'."""
        fr = FeatureRequest(id="feat_001")
        # Temporarily patch a field's json_schema_extra to be non-dict
        original = fr.model_fields["id"].json_schema_extra
        fr.model_fields["id"].json_schema_extra = None  # type: ignore[assignment]
        try:
            owner = fr.get_field_owner("id")
            assert owner == "unknown"
        finally:
            fr.model_fields["id"].json_schema_extra = original

    def test_field_with_dict_extra_returns_owner(self) -> None:
        fr = FeatureRequest(id="feat_001")
        owner = fr.get_field_owner("id")
        assert owner == "orchestrator"
