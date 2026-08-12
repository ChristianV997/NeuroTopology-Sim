"""ReportPipelineSpecV1: dict roundtrip, deterministic ID, and structural
validation rules. Synthetic fixtures only.
"""
from __future__ import annotations

from workflows.report_pipeline import (
    ReportPipelineSpecV1,
    ReportPipelineValidationError,
    compute_pipeline_id,
)


def _minimal_spec(**overrides) -> ReportPipelineSpecV1:
    kwargs = dict(
        input_mode="mne_bids_derived_features",
        dataset_id="demo_ds",
        modality="EEG",
        output_root="outputs/report_packs/demo",
        feature_table_path="features.csv",
        mapping_path="mapping.json",
        limitations=["test"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return ReportPipelineSpecV1.make(**kwargs)


def test_spec_dict_roundtrip():
    spec = _minimal_spec()
    d = spec.to_dict()
    spec2 = ReportPipelineSpecV1.from_dict(d)
    assert spec2.to_dict() == d


def test_spec_json_roundtrip():
    spec = _minimal_spec()
    text = spec.to_json()
    spec2 = ReportPipelineSpecV1.from_json(text)
    assert spec2.to_dict() == spec.to_dict()


def test_spec_write_json_roundtrip(tmp_path):
    spec = _minimal_spec()
    path = spec.write_json(tmp_path / "spec.json")
    spec2 = ReportPipelineSpecV1.from_json(path.read_text(encoding="utf-8"))
    assert spec2.pipeline_id == spec.pipeline_id


def test_pipeline_id_deterministic():
    spec_a = _minimal_spec()
    spec_b = _minimal_spec(pipeline_name="a totally different display name")
    assert spec_a.pipeline_id == spec_b.pipeline_id
    assert spec_a.pipeline_id == compute_pipeline_id(
        input_mode="mne_bids_derived_features", dataset_id="demo_ds", source_paths=[],
        recipe_spec_path=None, feature_table_path="features.csv", mapping_path="mapping.json",
        output_root="outputs/report_packs/demo",
    )


def test_pipeline_id_differs_across_identity_fields():
    base = _minimal_spec()
    other_dataset = _minimal_spec(dataset_id="other_ds")
    other_output = _minimal_spec(output_root="outputs/report_packs/other")
    assert base.pipeline_id != other_dataset.pipeline_id
    assert base.pipeline_id != other_output.pipeline_id


def test_created_at_excluded_from_pipeline_id():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=365)
    spec_now = _minimal_spec(_now=now)
    spec_later = _minimal_spec(_now=later)
    assert spec_now.created_at != spec_later.created_at
    assert spec_now.pipeline_id == spec_later.pipeline_id


def test_validate_or_raise_raises():
    spec = _minimal_spec(limitations=[])
    try:
        spec.validate_or_raise()
        assert False, "expected ReportPipelineValidationError"
    except ReportPipelineValidationError:
        pass


def test_validation_fails_on_empty_limitations():
    spec = _minimal_spec(limitations=[])
    assert any("rule 1" in e for e in spec.validate())


def test_validation_fails_on_empty_provenance():
    spec = _minimal_spec(provenance="")
    assert any("rule 2" in e for e in spec.validate())


def test_validation_fails_on_missing_input_mode():
    spec = _minimal_spec(input_mode="")
    assert any("rule 3" in e for e in spec.validate())


def test_validation_fails_on_unsupported_input_mode():
    spec = _minimal_spec(input_mode="not_a_real_mode")
    assert any("rule 4" in e for e in spec.validate())


def test_validation_fails_on_known_but_unsupported_input_mode():
    spec = _minimal_spec(input_mode="mne_bids_bids_raw_recipe", feature_table_path=None, mapping_path=None)
    errors = spec.validate()
    assert any("unsupported in v1" in e for e in errors)


def test_validation_fails_on_invalid_output_root():
    spec = _minimal_spec(output_root="/etc/evil")
    assert any("rule 6" in e for e in spec.validate())


def test_validation_fails_on_output_root_traversal():
    spec = _minimal_spec(output_root="outputs/../secrets")
    assert any("rule 6" in e for e in spec.validate())


def test_validation_fails_on_missing_required_paths_mne_bids_derived_features():
    spec = _minimal_spec(feature_table_path=None)
    assert any("rule 7" in e for e in spec.validate())
    spec2 = _minimal_spec(mapping_path=None)
    assert any("rule 7" in e for e in spec2.validate())


def test_validation_fails_on_missing_required_paths_existing_evidence_bundle():
    spec = _minimal_spec(
        input_mode="existing_evidence_bundle", feature_table_path=None, mapping_path=None,
    )
    assert any("rule 7" in e for e in spec.validate())


def test_validation_fails_on_missing_required_paths_recipe_mode():
    spec = _minimal_spec(
        input_mode="mne_bids_epoch_table_recipe", feature_table_path=None, mapping_path=None,
    )
    errors = spec.validate()
    assert any("recipe_spec_path" in e for e in errors)
    assert any("source_paths" in e for e in errors)


def test_validation_fails_on_missing_graph_summary_path_for_fmri_graph_summary_recipe():
    spec = _minimal_spec(
        input_mode="fmri_graph_summary_recipe", feature_table_path=None, mapping_path=None,
        recipe_spec_path="spec.json",
    )
    errors = spec.validate()
    assert any("graph_summary_path" in e for e in errors)


def test_validation_fails_on_invalid_modality():
    spec = _minimal_spec(modality="MEG")
    assert any("modality" in e for e in spec.validate())


def test_pipeline_id_mismatch_is_a_validation_error():
    spec = _minimal_spec()
    spec.pipeline_id = "not-the-real-id"
    errors = spec.validate()
    assert any("rule 1" in e for e in errors)


def test_banned_phrase_in_free_text_fails():
    spec = _minimal_spec(provenance="this run confirms diagnosis beyond doubt")
    errors = spec.validate()
    assert any("banned phrase" in e for e in errors)


def test_valid_spec_for_every_supported_mode_has_no_errors():
    from workflows.validation import SUPPORTED_INPUT_MODES

    per_mode_extra = {
        "existing_evidence_bundle": dict(feature_table_path=None, mapping_path=None, evidence_bundle_path="bundle.json"),
        "mne_bids_epoch_table_recipe": dict(feature_table_path=None, mapping_path=None, recipe_spec_path="spec.json", source_paths=["epochs.json"]),
        "mne_bids_derived_features": {},
        "fmri_timeseries_recipe": dict(feature_table_path=None, mapping_path=None, recipe_spec_path="spec.json", source_paths=["ts.json"]),
        "fmri_connectivity_matrix_recipe": dict(feature_table_path=None, mapping_path=None, recipe_spec_path="spec.json", source_paths=["conn.json"]),
        "fmri_graph_summary_recipe": dict(feature_table_path=None, mapping_path=None, recipe_spec_path="spec.json", graph_summary_path="gs.json"),
        "fmri_derived_features": {},
        "builtin_ds005620_cohort_summary": dict(feature_table_path=None, mapping_path=None, source_paths=["contracts/x"]),
        "builtin_ds005620_spatial_defect_map": dict(feature_table_path=None, mapping_path=None, source_paths=["contracts/x"]),
        "builtin_ds000245_schaefer100_motcorr": dict(feature_table_path=None, mapping_path=None, source_paths=["contracts/x"]),
        "builtin_ds000245_kmeans100": dict(feature_table_path=None, mapping_path=None, source_paths=["contracts/x"]),
    }
    assert set(per_mode_extra) == SUPPORTED_INPUT_MODES
    for mode, extra in per_mode_extra.items():
        spec = _minimal_spec(input_mode=mode, **extra)
        assert spec.validate() == [], f"{mode}: {spec.validate()}"
