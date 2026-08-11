"""Mapping validation and derived-feature table/graph-summary loading,
normalization, and grouping. Synthetic miniature fixtures only.
"""
from __future__ import annotations

import json

from adapters.fmri_derivatives_features import (
    AdapterDataError,
    cross_validate_rows,
    expand_graph_summary,
    group_rows,
    load_feature_table,
    load_graph_summary,
    load_mapping,
    normalize_wide_rows,
    peek_json_format,
)
from adapters.fmri_derivatives_validation import AdapterMappingError, validate_mapping

_LONG_MAPPING = {
    "format": "long",
    "dataset_id": "ds_test",
    "modality": "fMRI",
    "preprocessing_provenance": {"pipeline": "fmriprep", "source_tool_version": "fmriprep==23.x"},
    "confound_policy": "24-param",
}

_WIDE_MAPPING = {
    "format": "wide",
    "dataset_id": "ds_test",
    "modality": "fMRI",
    "source_state": "placebo",
    "target_state": "drug",
    "atlas_or_parcellation": "Schaefer100",
    "feature_definitions": {"connectivity.global_efficiency": "graph global efficiency"},
    "features": [{"canonical_name": "connectivity.global_efficiency", "source_column": "placebo_ge", "target_column": "drug_ge"}],
    "preprocessing_provenance": {"pipeline": "fmriprep"},
    "confound_policy": "24-param",
}

_GRAPH_SUMMARY = {
    "format": "graph_summary",
    "dataset_id": "ds_test",
    "modality": "fMRI",
    "atlas_or_parcellation": "Schaefer100",
    "source_state": "placebo",
    "target_state": "drug",
    "preprocessing_provenance": {"pipeline": "fmriprep"},
    "confound_policy": "24-param",
    "feature_definitions": {"connectivity.global_efficiency": "graph global efficiency"},
    "subjects": [{"subject_id": "sub-01", "metrics": {"connectivity.global_efficiency": {"source_value": 0.3, "target_value": 0.2}}}],
}


# ── mapping validation ───────────────────────────────────────────────────


def test_valid_long_mapping_passes():
    assert validate_mapping(dict(_LONG_MAPPING)) == []


def test_valid_wide_mapping_passes():
    assert validate_mapping(dict(_WIDE_MAPPING)) == []


def test_valid_graph_summary_passes():
    assert validate_mapping(dict(_GRAPH_SUMMARY)) == []


def test_mapping_requires_format():
    m = dict(_LONG_MAPPING)
    del m["format"]
    assert any("format" in e for e in validate_mapping(m))


def test_mapping_requires_modality_fmri_exactly():
    m = dict(_LONG_MAPPING)
    m["modality"] = "EEG"
    errors = validate_mapping(m)
    assert any("modality" in e for e in errors)


def test_mapping_requires_preprocessing_provenance():
    m = dict(_LONG_MAPPING)
    del m["preprocessing_provenance"]
    errors = validate_mapping(m)
    assert any("preprocessing_provenance" in e for e in errors)


def test_mapping_requires_confound_policy():
    m = dict(_LONG_MAPPING)
    del m["confound_policy"]
    errors = validate_mapping(m)
    assert any("confound_policy" in e for e in errors)


def test_wide_mapping_requires_source_state():
    m = dict(_WIDE_MAPPING)
    del m["source_state"]
    assert any("source_state" in e for e in validate_mapping(m))


def test_wide_mapping_requires_target_state():
    m = dict(_WIDE_MAPPING)
    del m["target_state"]
    assert any("target_state" in e for e in validate_mapping(m))


def test_wide_mapping_requires_atlas_for_graph_feature():
    m = dict(_WIDE_MAPPING)
    del m["atlas_or_parcellation"]
    errors = validate_mapping(m)
    assert any("atlas_or_parcellation" in e for e in errors)


def test_wide_mapping_allows_missing_atlas_for_non_graph_feature():
    m = dict(_WIDE_MAPPING)
    del m["atlas_or_parcellation"]
    m["feature_definitions"] = {"complexity.entropy": "sample entropy"}
    m["features"] = [{"canonical_name": "complexity.entropy", "source_column": "placebo_ge", "target_column": "drug_ge"}]
    errors = validate_mapping(m)
    assert not any("atlas_or_parcellation" in e for e in errors)


def test_mapping_rejects_unsupported_feature_namespace():
    m = dict(_WIDE_MAPPING)
    m["feature_definitions"] = {"consciousness.detected": "bad namespace"}
    m["features"] = [{"canonical_name": "consciousness.detected", "source_column": "a", "target_column": "b"}]
    errors = validate_mapping(m)
    assert any("namespace" in e for e in errors)


def test_mapping_rejects_banned_phrase():
    m = dict(_LONG_MAPPING)
    m["preprocessing_provenance"] = {"note": "this proves consciousness beyond doubt"}
    errors = validate_mapping(m)
    assert any("banned phrase" in e for e in errors)


def test_graph_summary_requires_subjects_or_cohort():
    m = dict(_GRAPH_SUMMARY)
    del m["subjects"]
    errors = validate_mapping(m)
    assert any("subjects" in e or "cohort" in e for e in errors)


def test_graph_summary_cohort_requires_subject_count():
    m = dict(_GRAPH_SUMMARY)
    m["cohort"] = {"metrics": {"connectivity.global_efficiency": {"source_value": 0.3, "target_value": 0.2}}}
    errors = validate_mapping(m)
    assert any("subject_count" in e for e in errors)


def test_graph_summary_cohort_requires_subject_count_at_least_two():
    m = dict(_GRAPH_SUMMARY)
    m["cohort"] = {"subject_count": 1, "metrics": {"connectivity.global_efficiency": {"source_value": 0.3, "target_value": 0.2}}}
    errors = validate_mapping(m)
    assert any("subject_count" in e for e in errors)


def test_load_mapping_fails_closed_on_missing_file(tmp_path):
    try:
        load_mapping(tmp_path / "missing.json")
        assert False, "expected AdapterMappingError"
    except AdapterMappingError:
        pass


def test_load_mapping_fails_closed_on_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid", encoding="utf-8")
    try:
        load_mapping(path)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError:
        pass


# ── feature table / graph-summary loading ────────────────────────────────


def test_load_feature_table_csv(tmp_path):
    path = tmp_path / "features.csv"
    path.write_text("subject_id,feature_name\nsub-01,connectivity.global_efficiency\n", encoding="utf-8")
    rows = load_feature_table(path)
    assert rows == [{"subject_id": "sub-01", "feature_name": "connectivity.global_efficiency"}]


def test_peek_json_format_detects_graph_summary(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(_GRAPH_SUMMARY), encoding="utf-8")
    assert peek_json_format(path) == "graph_summary"


def test_peek_json_format_returns_none_for_csv(tmp_path):
    path = tmp_path / "features.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert peek_json_format(path) is None


def test_load_graph_summary_fails_closed_on_invalid_structure(tmp_path):
    path = tmp_path / "bad_summary.json"
    path.write_text(json.dumps({"format": "graph_summary"}), encoding="utf-8")
    try:
        load_graph_summary(path)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError:
        pass


# ── wide-to-long normalization: never infers state from column names ────


def test_normalize_wide_rows_uses_explicit_mapping_not_column_names():
    rows = [{"subject_id": "sub-01", "placebo_ge": "0.34", "drug_ge": "0.29"}]
    long_rows = normalize_wide_rows(rows, _WIDE_MAPPING)
    assert len(long_rows) == 1
    assert long_rows[0]["source_state"] == "placebo"
    assert long_rows[0]["target_state"] == "drug"
    assert long_rows[0]["atlas_or_parcellation"] == "Schaefer100"


def test_normalize_wide_rows_fails_closed_on_missing_column():
    rows = [{"subject_id": "sub-01", "placebo_ge": "0.34"}]
    try:
        normalize_wide_rows(rows, _WIDE_MAPPING)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


# ── graph_summary expansion ───────────────────────────────────────────────


def test_expand_graph_summary_subject_rows_only():
    subject_rows, cohort_entry = expand_graph_summary(_GRAPH_SUMMARY)
    assert len(subject_rows) == 1
    assert subject_rows[0]["atlas_or_parcellation"] == "Schaefer100"
    assert cohort_entry is None


def test_expand_graph_summary_cohort_entry():
    summary = dict(_GRAPH_SUMMARY)
    summary["cohort"] = {
        "subject_count": 20,
        "metrics": {"connectivity.global_efficiency": {"source_value": 0.33, "target_value": 0.30, "p_value": 0.01}},
    }
    subject_rows, cohort_entry = expand_graph_summary(summary)
    assert cohort_entry is not None
    assert cohort_entry["subject_count"] == 20
    assert cohort_entry["atlas_or_parcellation"] == "Schaefer100"


def test_expand_graph_summary_rejects_subject_missing_id():
    summary = dict(_GRAPH_SUMMARY)
    summary["subjects"] = [{"metrics": {"connectivity.global_efficiency": {"source_value": 0.3, "target_value": 0.2}}}]
    try:
        expand_graph_summary(summary)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


# ── row cross-validation ─────────────────────────────────────────────────


def _long_row(**overrides):
    row = {
        "subject_id": "sub-01", "source_state": "placebo", "target_state": "drug",
        "feature_name": "connectivity.global_efficiency", "source_value": "0.34", "target_value": "0.29",
        "feature_definition": "graph global efficiency", "atlas_or_parcellation": "Schaefer100",
    }
    row.update(overrides)
    return row


def test_cross_validate_accepts_valid_row():
    valid, errors = cross_validate_rows([_long_row()], _LONG_MAPPING)
    assert len(valid) == 1
    assert errors == []


def test_cross_validate_rejects_missing_source_state():
    valid, errors = cross_validate_rows([_long_row(source_state="")], _LONG_MAPPING)
    assert valid == []
    assert any("source_state" in e and "never inferred" in e for e in errors)


def test_cross_validate_rejects_graph_feature_without_atlas():
    valid, errors = cross_validate_rows([_long_row(atlas_or_parcellation="")], _LONG_MAPPING)
    assert valid == []
    assert any("atlas_or_parcellation" in e for e in errors)


def test_cross_validate_allows_non_graph_feature_without_atlas():
    row = _long_row(feature_name="complexity.entropy", feature_definition="sample entropy", atlas_or_parcellation="")
    valid, errors = cross_validate_rows([row], _LONG_MAPPING)
    assert len(valid) == 1
    assert errors == []


def test_cross_validate_rejects_unsupported_feature_namespace():
    valid, errors = cross_validate_rows([_long_row(feature_name="consciousness.detected", feature_definition="bad")], _LONG_MAPPING)
    assert valid == []
    assert any("namespace" in e for e in errors)


def test_cross_validate_rejects_missing_feature_definition():
    valid, errors = cross_validate_rows([_long_row(feature_definition="")], _LONG_MAPPING)
    assert valid == []
    assert any("missing feature_definition" in e for e in errors)


def test_cross_validate_rejects_non_numeric_value():
    valid, errors = cross_validate_rows([_long_row(source_value="not_a_number")], _LONG_MAPPING)
    assert valid == []
    assert any("not numeric" in e for e in errors)


def test_cross_validate_missing_null_control_becomes_not_provided():
    valid, errors = cross_validate_rows([_long_row()], _LONG_MAPPING)
    assert errors == []
    assert valid[0]["null_control_status"] == "not_provided"


def test_cross_validate_preserves_confound_policy():
    valid, errors = cross_validate_rows([_long_row()], _LONG_MAPPING)
    assert valid[0]["confound_policy"] == "24-param"


# ── row grouping ──────────────────────────────────────────────────────────


def _validated_row(**overrides):
    row = {
        "dataset_id": "d", "subject_id": "sub-01", "session_id": None, "source_state": "placebo",
        "target_state": "drug", "modality": "fMRI", "atlas_or_parcellation": "Schaefer100",
        "feature_name": "connectivity.global_efficiency", "source_value": 0.34, "target_value": 0.29,
        "feature_definition": "x", "preprocessing_provenance": {}, "confound_policy": "24-param",
        "null_control_status": "not_provided", "artifact_path": None,
    }
    row.update(overrides)
    return row


def test_group_rows_groups_by_full_key_including_atlas():
    rows = [
        _validated_row(subject_id="sub-01", feature_name="connectivity.global_efficiency"),
        _validated_row(subject_id="sub-01", feature_name="connectivity.modularity"),
        _validated_row(subject_id="sub-02", feature_name="connectivity.global_efficiency"),
    ]
    groups, errors = group_rows(rows)
    assert errors == []
    assert len(groups) == 2
    sub01_group = next(g for g in groups if g.subject_id == "sub-01")
    assert len(sub01_group.rows) == 2
    assert sub01_group.atlas_or_parcellation == "Schaefer100"


def test_group_rows_different_atlas_creates_separate_groups():
    rows = [
        _validated_row(atlas_or_parcellation="Schaefer100"),
        _validated_row(atlas_or_parcellation="AAL"),
    ]
    groups, errors = group_rows(rows)
    assert errors == []
    assert len(groups) == 2


def test_group_rows_rejects_duplicate_feature_in_group():
    rows = [
        _validated_row(feature_name="connectivity.global_efficiency", source_value=0.34),
        _validated_row(feature_name="connectivity.global_efficiency", source_value=0.40),
    ]
    groups, errors = group_rows(rows)
    assert groups == []
    assert any("duplicate feature_name" in e for e in errors)
