"""FeatureRecipeSpecV1 structural validation rules. Synthetic fixtures
only.
"""
from __future__ import annotations

from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1
from adapters.mne_bids_feature_recipe_validation import FeatureRecipeValidationError


def _minimal_spec(**overrides) -> FeatureRecipeSpecV1:
    kwargs = dict(
        dataset_id="demo_bids_eeg",
        feature_set_id="mne_bids_spectral_v1",
        source_state="rest",
        target_state="task",
        requested_features=["spectral.alpha_power"],
        max_subjects=5,
        max_runs=5,
        max_epochs_per_state=10,
        max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={"spectral.alpha_power": "Mean relative alpha-band power over valid epochs."},
        limitations=["test"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return FeatureRecipeSpecV1.make(**kwargs)


def test_valid_spec_has_no_errors():
    assert _minimal_spec().validate() == []


def test_validate_or_raise_raises():
    spec = _minimal_spec(limitations=[])
    try:
        spec.validate_or_raise()
        assert False, "expected FeatureRecipeValidationError"
    except FeatureRecipeValidationError:
        pass


def test_validation_fails_on_empty_limitations():
    spec = _minimal_spec(limitations=[])
    assert any("limitations" in e for e in spec.validate())


def test_validation_fails_without_event_state_mapping():
    spec = _minimal_spec(event_state_mapping={})
    errors = spec.validate()
    assert any("rule 5" in e for e in errors)


def test_validation_fails_without_source_state():
    spec = _minimal_spec(source_state="")
    errors = spec.validate()
    assert any("rule 6" in e for e in errors)


def test_validation_fails_without_target_state():
    spec = _minimal_spec(target_state="")
    errors = spec.validate()
    assert any("rule 6" in e for e in errors)


def test_validation_fails_when_source_state_not_in_mapping_values():
    spec = _minimal_spec(source_state="sleep")
    errors = spec.validate()
    assert any("does not appear as a value in event_state_mapping" in e for e in errors)


def test_validation_fails_when_source_and_target_state_identical():
    spec = _minimal_spec(target_state="rest")
    errors = spec.validate()
    assert any("must differ" in e for e in errors)


def test_validation_fails_on_unsupported_feature_namespace():
    spec = _minimal_spec(
        requested_features=["connectivity.plv"],
        feature_definitions={"connectivity.plv": "not supported in v1"},
    )
    errors = spec.validate()
    assert any("not in this recipe's supported feature set" in e for e in errors)


def test_validation_fails_on_feature_missing_definition():
    spec = _minimal_spec(requested_features=["spectral.alpha_power"], feature_definitions={})
    errors = spec.validate()
    assert any("has no entry in feature_definitions" in e for e in errors)


def test_validation_fails_without_resource_bounds():
    for field_name in ("max_subjects", "max_runs", "max_epochs_per_state", "max_total_epochs"):
        spec = _minimal_spec(**{field_name: None})
        errors = spec.validate()
        assert any("rule 9" in e for e in errors), f"{field_name}=None should fail rule 9"


def test_validation_fails_on_non_positive_bounds():
    spec = _minimal_spec(max_subjects=0)
    errors = spec.validate()
    assert any("rule 9" in e for e in errors)

    spec2 = _minimal_spec(max_runs=-1)
    errors2 = spec2.validate()
    assert any("rule 9" in e for e in errors2)


def test_validation_fails_on_non_eeg_modality():
    spec = _minimal_spec(modality="MEG")
    errors = spec.validate()
    assert any("rule 7" in e for e in errors)


def test_validation_fails_on_invalid_input_kind():
    spec = _minimal_spec(input_kind="not_a_real_kind")
    errors = spec.validate()
    assert any("input_kind" in e for e in errors)


def test_validation_fails_when_bids_raw_missing_bids_root():
    spec = _minimal_spec(input_kind="bids_raw", bids_root="")
    errors = spec.validate()
    assert any("bids_root is required" in e for e in errors)


def test_validation_fails_on_invalid_output_format():
    spec = _minimal_spec(output_format="wide")
    errors = spec.validate()
    assert any("output_format" in e for e in errors)


def test_validation_fails_on_invalid_artifact_policy():
    spec = _minimal_spec(artifact_policy="autoreject")
    errors = spec.validate()
    assert any("artifact_policy" in e for e in errors)


def test_validation_fails_on_invalid_reference_policy():
    spec = _minimal_spec(reference_policy="linked_mastoid")
    errors = spec.validate()
    assert any("reference_policy" in e for e in errors)


def test_recipe_id_mismatch_is_a_validation_error():
    spec = _minimal_spec()
    spec.recipe_id = "not-the-real-id"
    errors = spec.validate()
    assert any("rule 1" in e for e in errors)


def test_banned_phrase_in_free_text_fails():
    spec = _minimal_spec(provenance="this extraction confirms real signal beyond doubt")
    errors = spec.validate()
    assert any("banned phrase" in e for e in errors)
