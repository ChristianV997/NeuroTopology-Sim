"""Mapping validation and derived-feature table loading/normalization/
grouping. Synthetic miniature fixtures only.
"""
from __future__ import annotations

import json

from adapters.mne_bids_features import (
    AdapterDataError,
    cross_validate_rows,
    group_rows,
    load_feature_table,
    load_mapping,
    normalize_wide_rows,
)
from adapters.validation import AdapterMappingError, validate_mapping

_LONG_MAPPING = {
    "format": "long",
    "dataset_id": "ds_test",
    "modality": "EEG",
    "preprocessing_provenance": {"pipeline": "mne", "source_tool_version": "mne==1.x"},
}

_WIDE_MAPPING = {
    "format": "wide",
    "dataset_id": "ds_test",
    "modality": "EEG",
    "source_state": "awake",
    "target_state": "sedated",
    "feature_definitions": {"spectral.alpha_power": "alpha band power"},
    "features": [{"canonical_name": "spectral.alpha_power", "source_column": "awake_alpha", "target_column": "sedated_alpha"}],
    "preprocessing_provenance": {"pipeline": "mne"},
}


# ── mapping validation ───────────────────────────────────────────────────


def test_valid_long_mapping_passes():
    assert validate_mapping(dict(_LONG_MAPPING)) == []


def test_valid_wide_mapping_passes():
    assert validate_mapping(dict(_WIDE_MAPPING)) == []


def test_mapping_requires_format():
    m = dict(_LONG_MAPPING)
    del m["format"]
    errors = validate_mapping(m)
    assert any("format" in e for e in errors)


def test_mapping_requires_modality():
    m = dict(_LONG_MAPPING)
    del m["modality"]
    errors = validate_mapping(m)
    assert any("modality" in e for e in errors)


def test_mapping_rejects_unsupported_modality():
    m = dict(_LONG_MAPPING)
    m["modality"] = "PET"
    errors = validate_mapping(m)
    assert any("modality" in e for e in errors)


def test_wide_mapping_requires_source_state():
    m = dict(_WIDE_MAPPING)
    del m["source_state"]
    errors = validate_mapping(m)
    assert any("source_state" in e for e in errors)


def test_wide_mapping_requires_target_state():
    m = dict(_WIDE_MAPPING)
    del m["target_state"]
    errors = validate_mapping(m)
    assert any("target_state" in e for e in errors)


def test_wide_mapping_requires_matching_canonical_feature_names():
    m = dict(_WIDE_MAPPING)
    m["features"] = [{"canonical_name": "spectral.beta_power", "source_column": "a", "target_column": "b"}]
    errors = validate_mapping(m)
    assert any("canonical_name" in e for e in errors)


def test_wide_mapping_requires_feature_definitions():
    m = dict(_WIDE_MAPPING)
    del m["feature_definitions"]
    errors = validate_mapping(m)
    assert any("feature_definitions" in e for e in errors)


def test_mapping_rejects_unsupported_feature_namespace():
    m = dict(_WIDE_MAPPING)
    m["feature_definitions"] = {"consciousness.detected": "bad namespace"}
    m["features"] = [{"canonical_name": "consciousness.detected", "source_column": "a", "target_column": "b"}]
    errors = validate_mapping(m)
    assert any("namespace" in e for e in errors)


def test_mapping_requires_preprocessing_provenance():
    m = dict(_LONG_MAPPING)
    del m["preprocessing_provenance"]
    errors = validate_mapping(m)
    assert any("preprocessing_provenance" in e for e in errors)


def test_mapping_rejects_banned_phrase():
    m = dict(_LONG_MAPPING)
    m["preprocessing_provenance"] = {"note": "this proves consciousness beyond doubt"}
    errors = validate_mapping(m)
    assert any("banned phrase" in e for e in errors)


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


def test_load_mapping_fails_closed_on_invalid_structure(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({"format": "long"}), encoding="utf-8")
    try:
        load_mapping(path)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError:
        pass


# ── feature table loading ────────────────────────────────────────────────


def test_load_feature_table_csv(tmp_path):
    path = tmp_path / "features.csv"
    path.write_text("subject_id,feature_name\nsub-01,spectral.alpha_power\n", encoding="utf-8")
    rows = load_feature_table(path)
    assert rows == [{"subject_id": "sub-01", "feature_name": "spectral.alpha_power"}]


def test_load_feature_table_json_list(tmp_path):
    path = tmp_path / "features.json"
    path.write_text(json.dumps([{"subject_id": "sub-01"}]), encoding="utf-8")
    rows = load_feature_table(path)
    assert rows == [{"subject_id": "sub-01"}]


def test_load_feature_table_json_rows_key(tmp_path):
    path = tmp_path / "features.json"
    path.write_text(json.dumps({"rows": [{"subject_id": "sub-01"}]}), encoding="utf-8")
    rows = load_feature_table(path)
    assert rows == [{"subject_id": "sub-01"}]


def test_load_feature_table_fails_closed_on_missing_file(tmp_path):
    try:
        load_feature_table(tmp_path / "missing.csv")
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


# ── wide-to-long normalization: never infers state from column names ────


def test_normalize_wide_rows_uses_explicit_mapping_not_column_names():
    rows = [{"subject_id": "sub-01", "awake_alpha": "1.5", "sedated_alpha": "0.8"}]
    long_rows = normalize_wide_rows(rows, _WIDE_MAPPING)
    assert len(long_rows) == 1
    assert long_rows[0]["source_state"] == "awake"
    assert long_rows[0]["target_state"] == "sedated"
    assert long_rows[0]["feature_name"] == "spectral.alpha_power"
    assert long_rows[0]["source_value"] == "1.5"
    assert long_rows[0]["target_value"] == "0.8"


def test_normalize_wide_rows_fails_closed_on_missing_column():
    rows = [{"subject_id": "sub-01", "awake_alpha": "1.5"}]  # missing sedated_alpha
    try:
        normalize_wide_rows(rows, _WIDE_MAPPING)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


def test_normalize_wide_rows_fails_closed_on_missing_subject_id():
    rows = [{"awake_alpha": "1.5", "sedated_alpha": "0.8"}]
    try:
        normalize_wide_rows(rows, _WIDE_MAPPING)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


# ── row cross-validation ─────────────────────────────────────────────────


def _long_row(**overrides):
    row = {
        "subject_id": "sub-01", "source_state": "awake", "target_state": "sedated",
        "feature_name": "spectral.alpha_power", "source_value": "1.5", "target_value": "0.8",
        "feature_definition": "alpha band power",
    }
    row.update(overrides)
    return row


def test_cross_validate_accepts_valid_row():
    valid, errors = cross_validate_rows([_long_row()], _LONG_MAPPING)
    assert len(valid) == 1
    assert errors == []


def test_cross_validate_rejects_missing_subject_id():
    valid, errors = cross_validate_rows([_long_row(subject_id="")], _LONG_MAPPING)
    assert valid == []
    assert any("subject_id" in e for e in errors)


def test_cross_validate_rejects_missing_source_state():
    valid, errors = cross_validate_rows([_long_row(source_state="")], _LONG_MAPPING)
    assert valid == []
    assert any("source_state" in e and "never inferred" in e for e in errors)


def test_cross_validate_rejects_missing_target_state():
    valid, errors = cross_validate_rows([_long_row(target_state="")], _LONG_MAPPING)
    assert valid == []
    assert any("target_state" in e and "never inferred" in e for e in errors)


def test_cross_validate_rejects_identical_source_and_target_state():
    valid, errors = cross_validate_rows([_long_row(target_state="awake")], _LONG_MAPPING)
    assert valid == []
    assert any("must differ" in e for e in errors)


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


def test_cross_validate_rejects_invalid_null_control_status():
    valid, errors = cross_validate_rows([_long_row(null_control_status="definitely_passed")], _LONG_MAPPING)
    assert valid == []
    assert any("null_control_status" in e for e in errors)


def test_cross_validate_accepts_valid_null_control_status():
    valid, errors = cross_validate_rows([_long_row(null_control_status="passed")], _LONG_MAPPING)
    assert errors == []
    assert valid[0]["null_control_status"] == "passed"


def test_cross_validate_one_bad_row_does_not_block_good_rows():
    rows = [_long_row(subject_id="sub-01"), _long_row(subject_id="")]
    valid, errors = cross_validate_rows(rows, _LONG_MAPPING)
    assert len(valid) == 1
    assert len(errors) == 1


def test_cross_validate_rejects_dataset_id_mismatch():
    valid, errors = cross_validate_rows([_long_row(dataset_id="some_other_dataset")], _LONG_MAPPING)
    assert valid == []
    assert any("dataset_id" in e and "does not match" in e for e in errors)


# ── row grouping ──────────────────────────────────────────────────────────


def test_group_rows_groups_by_full_key():
    rows = [
        {"dataset_id": "d", "subject_id": "sub-01", "session_id": None, "source_state": "awake",
         "target_state": "sedated", "modality": "EEG", "feature_name": "spectral.alpha_power",
         "source_value": 1.5, "target_value": 0.8, "feature_definition": "x",
         "preprocessing_provenance": {}, "null_control_status": "not_provided", "artifact_path": None},
        {"dataset_id": "d", "subject_id": "sub-01", "session_id": None, "source_state": "awake",
         "target_state": "sedated", "modality": "EEG", "feature_name": "connectivity.mean_plv",
         "source_value": 0.6, "target_value": 0.3, "feature_definition": "y",
         "preprocessing_provenance": {}, "null_control_status": "not_provided", "artifact_path": None},
        {"dataset_id": "d", "subject_id": "sub-02", "session_id": None, "source_state": "awake",
         "target_state": "sedated", "modality": "EEG", "feature_name": "spectral.alpha_power",
         "source_value": 1.2, "target_value": 0.9, "feature_definition": "x",
         "preprocessing_provenance": {}, "null_control_status": "not_provided", "artifact_path": None},
    ]
    groups, errors = group_rows(rows)
    assert errors == []
    assert len(groups) == 2
    sub01_group = next(g for g in groups if g.subject_id == "sub-01")
    assert len(sub01_group.rows) == 2


def test_group_rows_rejects_duplicate_feature_in_group():
    rows = [
        {"dataset_id": "d", "subject_id": "sub-01", "session_id": None, "source_state": "awake",
         "target_state": "sedated", "modality": "EEG", "feature_name": "spectral.alpha_power",
         "source_value": 1.5, "target_value": 0.8, "feature_definition": "x",
         "preprocessing_provenance": {}, "null_control_status": "not_provided", "artifact_path": None},
        {"dataset_id": "d", "subject_id": "sub-01", "session_id": None, "source_state": "awake",
         "target_state": "sedated", "modality": "EEG", "feature_name": "spectral.alpha_power",
         "source_value": 1.6, "target_value": 0.9, "feature_definition": "x",
         "preprocessing_provenance": {}, "null_control_status": "not_provided", "artifact_path": None},
    ]
    groups, errors = group_rows(rows)
    assert groups == []
    assert any("duplicate feature_name" in e for e in errors)
