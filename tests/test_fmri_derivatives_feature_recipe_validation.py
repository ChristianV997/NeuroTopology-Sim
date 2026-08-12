"""FmriFeatureRecipeSpecV1 structural validation rules. Synthetic fixtures
only.
"""
from __future__ import annotations

from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1
from adapters.fmri_derivatives_feature_recipe_validation import FmriFeatureRecipeValidationError


def _minimal_spec(**overrides) -> FmriFeatureRecipeSpecV1:
    kwargs = dict(
        dataset_id="demo_fmri",
        feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo",
        target_state="drug",
        atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.mean_connectivity"],
        max_subjects=5,
        max_runs=5,
        max_timepoints_per_state=100,
        max_total_timepoints=1000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={"connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation."},
        confound_policy={"description": "No confounds regression applied."},
        limitations=["test"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return FmriFeatureRecipeSpecV1.make(**kwargs)


def test_valid_spec_has_no_errors():
    assert _minimal_spec().validate() == []


def test_validate_or_raise_raises():
    spec = _minimal_spec(limitations=[])
    try:
        spec.validate_or_raise()
        assert False, "expected FmriFeatureRecipeValidationError"
    except FmriFeatureRecipeValidationError:
        pass


def test_validation_fails_on_empty_limitations():
    spec = _minimal_spec(limitations=[])
    assert any("limitations" in e for e in spec.validate())


def test_validation_fails_without_state_mapping():
    spec = _minimal_spec(state_mapping={})
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


def test_validation_fails_without_atlas_or_parcellation():
    spec = _minimal_spec(atlas_or_parcellation="")
    errors = spec.validate()
    assert any("rule 8" in e for e in errors)


def test_validation_fails_without_confound_policy():
    spec = _minimal_spec(confound_policy={})
    errors = spec.validate()
    assert any("rule 9" in e for e in errors)


def test_validation_fails_when_confound_policy_missing_description():
    spec = _minimal_spec(confound_policy={"source": "none"})
    errors = spec.validate()
    assert any("confound_policy.description" in e for e in errors)


def test_validation_fails_on_unsupported_feature_namespace():
    spec = _minimal_spec(
        requested_features=["topology.persistent_homology_h2"],
        feature_definitions={"topology.persistent_homology_h2": "not supported"},
    )
    errors = spec.validate()
    assert any("not in this recipe's supported feature set" in e for e in errors)


def test_validation_fails_without_resource_bounds():
    for field_name in ("max_subjects", "max_runs", "max_timepoints_per_state", "max_total_timepoints"):
        spec = _minimal_spec(**{field_name: None})
        errors = spec.validate()
        assert any("rule 11" in e for e in errors), f"{field_name}=None should fail rule 11"


def test_validation_fails_on_non_positive_bounds():
    spec = _minimal_spec(max_subjects=0)
    assert any("rule 11" in e for e in spec.validate())


def test_validation_fails_on_non_fmri_modality():
    spec = _minimal_spec(modality="EEG")
    errors = spec.validate()
    assert any("rule 7" in e for e in errors)


def test_validation_fails_on_invalid_input_kind():
    spec = _minimal_spec(input_kind="not_a_real_kind")
    errors = spec.validate()
    assert any("input_kind" in e for e in errors)


def test_validation_fails_on_missing_graph_threshold_policy():
    spec = _minimal_spec(
        requested_features=["connectivity.global_efficiency"],
        feature_definitions={"connectivity.global_efficiency": "Global efficiency."},
        graph_policy={},
    )
    errors = spec.validate()
    assert any("graph_policy.threshold" in e for e in errors)


def test_graph_threshold_policy_not_required_for_graph_summary_mode():
    spec = _minimal_spec(
        input_kind="graph_summary",
        requested_features=["connectivity.global_efficiency"],
        feature_definitions={"connectivity.global_efficiency": "Global efficiency."},
        graph_policy={},
    )
    assert spec.validate() == []


def test_topology_feature_only_allowed_for_graph_summary_input_kind():
    spec = _minimal_spec(
        input_kind="timeseries_table",
        requested_features=["topology.fmri_graph_betti0"],
        feature_definitions={"topology.fmri_graph_betti0": "Betti-0 (already computed upstream)."},
    )
    errors = spec.validate()
    assert any("topology feature" in e for e in errors)

    spec2 = _minimal_spec(
        input_kind="graph_summary",
        requested_features=["topology.fmri_graph_betti0"],
        feature_definitions={"topology.fmri_graph_betti0": "Betti-0 (already computed upstream)."},
    )
    assert spec2.validate() == []


def test_recipe_id_mismatch_is_a_validation_error():
    spec = _minimal_spec()
    spec.recipe_id = "not-the-real-id"
    errors = spec.validate()
    assert any("rule 1" in e for e in errors)


def test_banned_phrase_in_free_text_fails():
    spec = _minimal_spec(provenance="this extraction confirms real signal beyond doubt")
    errors = spec.validate()
    assert any("banned phrase" in e for e in errors)
