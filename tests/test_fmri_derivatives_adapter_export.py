"""Derived-feature -> TransitionRecordV1 export, connectivity/graph-summary
handling, registry gating, and optional phase-space integration. Synthetic
miniature fixtures only.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from adapters.fmri_derivatives import (
    AdapterExportError,
    AdapterRegistryError,
    export_fmri_derivative_transitions,
)
from adapters.fmri_derivatives_features import AdapterDataError
from adapters.fmri_derivatives_validation import AdapterMappingError
from benchmarks.export_registry import BenchmarkRegistry
from transitions.store import TransitionStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _write_long_features(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition", "atlas_or_parcellation"])
        w.writerow(["sub-01", "placebo", "drug", "connectivity.global_efficiency", "0.34", "0.29", "Graph global efficiency over Schaefer100 connectome", "Schaefer100"])
        w.writerow(["sub-01", "placebo", "drug", "connectivity.modularity", "0.31", "0.40", "Louvain modularity Q", "Schaefer100"])
        w.writerow(["sub-02", "placebo", "drug", "connectivity.global_efficiency", "0.30", "0.25", "Graph global efficiency over Schaefer100 connectome", "Schaefer100"])
        w.writerow(["sub-02", "placebo", "drug", "connectivity.modularity", "0.33", "0.42", "Louvain modularity Q", "Schaefer100"])
    return path


def _write_long_mapping(path: Path, *, dataset_id: str = "fmri_smoke_lab_001") -> Path:
    mapping = {
        "format": "long", "dataset_id": dataset_id, "modality": "fMRI",
        "preprocessing_provenance": {"pipeline": "fmriprep 23.x + nilearn ConnectivityMeasure", "source_tool_version": "fmriprep==23.1.0"},
        "confound_policy": "24-param + aCompCor, high-pass 0.01Hz",
    }
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _write_wide_features(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "placebo_ge", "drug_ge"])
        w.writerow(["sub-01", "0.34", "0.29"])
        w.writerow(["sub-02", "0.30", "0.25"])
    return path


def _write_wide_mapping(path: Path, *, dataset_id: str = "fmri_smoke_wide_001") -> Path:
    mapping = {
        "format": "wide", "dataset_id": dataset_id, "modality": "fMRI",
        "source_state": "placebo", "target_state": "drug", "atlas_or_parcellation": "Schaefer100",
        "feature_definitions": {"connectivity.global_efficiency": "Graph global efficiency"},
        "features": [{"canonical_name": "connectivity.global_efficiency", "source_column": "placebo_ge", "target_column": "drug_ge"}],
        "preprocessing_provenance": {"pipeline": "fmriprep"},
        "confound_policy": "24-param",
    }
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _write_graph_summary(path: Path, *, dataset_id: str = "fmri_smoke_graph_001", with_cohort: bool = False) -> Path:
    summary = {
        "format": "graph_summary", "dataset_id": dataset_id, "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100", "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"pipeline": "fmriprep+nilearn", "source_tool_version": "fmriprep==23.1.0"},
        "confound_policy": "24-param + aCompCor",
        "feature_definitions": {
            "connectivity.global_efficiency": "Graph global efficiency",
            "connectivity.modularity": "Louvain modularity Q",
        },
        "null_control_status": "not_provided",
        "subjects": [
            {"subject_id": "sub-01", "metrics": {
                "connectivity.global_efficiency": {"source_value": 0.34, "target_value": 0.29},
                "connectivity.modularity": {"source_value": 0.31, "target_value": 0.40},
            }},
            {"subject_id": "sub-02", "metrics": {
                "connectivity.global_efficiency": {"source_value": 0.30, "target_value": 0.25},
                "connectivity.modularity": {"source_value": 0.33, "target_value": 0.42},
            }},
        ],
    }
    if with_cohort:
        summary["cohort"] = {
            "subject_count": 20,
            "metrics": {"connectivity.global_efficiency": {"source_value": 0.33, "target_value": 0.30, "statistic": "paired_t", "p_value": 0.01}},
        }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


# ── long-format export ───────────────────────────────────────────────────


def test_long_export_writes_valid_transition_records(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out",
        registry_path=_SEED_REGISTRY, updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert result["n_written"] == 2
    assert result["errors"] == []
    for record in result["records"]:
        assert record.validate() == []


def test_long_export_transition_ids_deterministic(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result_a = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out_a", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out_a" / "reg.json",
    )
    result_b = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out_b", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out_b" / "reg.json",
    )
    ids_a = sorted(r.transition_id for r in result_a["records"])
    ids_b = sorted(r.transition_id for r in result_b["records"])
    assert ids_a == ids_b


def test_long_export_preserves_preprocessing_provenance_and_confound_policy(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.preprocessing_provenance["pipeline"] == "fmriprep 23.x + nilearn ConnectivityMeasure"
        assert record.preprocessing_provenance["confound_policy"] == "24-param + aCompCor, high-pass 0.01Hz"


def test_long_export_preserves_atlas_or_parcellation(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.metadata["atlas_or_parcellation"] == "Schaefer100"


def test_long_export_preserves_source_artifact_paths(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.artifact_paths["mapping"] == str(mapping)
        assert record.artifact_paths["features_table"] == str(features)


def test_long_export_null_controls_not_fabricated(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.null_control_summary["status"] == "not_provided"


def test_long_export_records_feature_set_id_in_metadata(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.metadata["feature_set_id"].startswith("fmri_derivatives::")


def test_long_export_uses_transition_store_layout(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    store = TransitionStore(out / "transitions")
    assert len(store.list_records()) == 2


def test_long_export_claim_scope_and_evidence_level_defaults(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.claim_scope == "exploratory_metric"
        assert record.evidence_level == "L2_single_subject_real_signal"
        assert record.record_level == "subject"


# ── wide-format export ────────────────────────────────────────────────────


def test_wide_export_writes_valid_transition_records(tmp_path):
    features = _write_wide_features(tmp_path / "features_wide.csv")
    mapping = _write_wide_mapping(tmp_path / "mapping_wide.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert result["n_written"] == 2
    for record in result["records"]:
        assert record.validate() == []
        assert record.feature_names == ["connectivity.global_efficiency"]


def test_wide_export_never_infers_state_from_column_names(tmp_path):
    features = _write_wide_features(tmp_path / "features_wide.csv")
    mapping_path = tmp_path / "mapping_wide_no_states.json"
    bad_mapping = {
        "format": "wide", "dataset_id": "d", "modality": "fMRI", "atlas_or_parcellation": "Schaefer100",
        "feature_definitions": {"connectivity.global_efficiency": "graph global efficiency"},
        "features": [{"canonical_name": "connectivity.global_efficiency", "source_column": "placebo_ge", "target_column": "drug_ge"}],
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
    }
    mapping_path.write_text(json.dumps(bad_mapping), encoding="utf-8")
    try:
        export_fmri_derivative_transitions(features, mapping_path, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError as exc:
        assert "source_state" in str(exc) or "target_state" in str(exc)


def test_wide_export_without_atlas_fails_closed(tmp_path):
    features = _write_wide_features(tmp_path / "features_wide.csv")
    mapping_path = tmp_path / "mapping_wide_no_atlas.json"
    bad_mapping = {
        "format": "wide", "dataset_id": "d", "modality": "fMRI",
        "source_state": "placebo", "target_state": "drug",
        "feature_definitions": {"connectivity.global_efficiency": "graph global efficiency"},
        "features": [{"canonical_name": "connectivity.global_efficiency", "source_column": "placebo_ge", "target_column": "drug_ge"}],
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
    }
    mapping_path.write_text(json.dumps(bad_mapping), encoding="utf-8")
    try:
        export_fmri_derivative_transitions(features, mapping_path, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError as exc:
        assert "atlas_or_parcellation" in str(exc)


# ── connectivity/graph-summary JSON export ────────────────────────────────


def test_graph_summary_export_subject_level(tmp_path):
    summary = _write_graph_summary(tmp_path / "graph_summary.json")
    result = export_fmri_derivative_transitions(
        summary, None, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert result["n_written"] == 2
    assert result["n_cohort_written"] == 0
    for record in result["records"]:
        assert record.validate() == []
        assert record.record_level == "subject"


def test_graph_summary_export_cohort_level_requires_explicit_stats(tmp_path):
    summary = _write_graph_summary(tmp_path / "graph_summary.json", with_cohort=True)
    result = export_fmri_derivative_transitions(
        summary, None, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert result["n_cohort_written"] == 1
    cohort_records = [r for r in result["records"] if r.record_level == "cohort"]
    assert len(cohort_records) == 1
    assert cohort_records[0].subject_id is None
    assert cohort_records[0].metadata["subject_count"] == 20
    assert cohort_records[0].evidence_level == "L4_cross_subject_dataset_specific"


def test_graph_summary_rejects_cohort_without_subject_count(tmp_path):
    path = tmp_path / "bad_summary.json"
    summary = {
        "format": "graph_summary", "dataset_id": "d", "modality": "fMRI", "atlas_or_parcellation": "Schaefer100",
        "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
        "feature_definitions": {"connectivity.global_efficiency": "ge"},
        "cohort": {"metrics": {"connectivity.global_efficiency": {"source_value": 0.3, "target_value": 0.2}}},
    }
    path.write_text(json.dumps(summary), encoding="utf-8")
    try:
        export_fmri_derivative_transitions(path, None, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError as exc:
        assert "subject_count" in str(exc)


def test_graph_summary_parametric_p_value_alone_is_not_null_control_pass(tmp_path):
    summary = _write_graph_summary(tmp_path / "graph_summary.json", with_cohort=True)
    result = export_fmri_derivative_transitions(
        summary, None, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    cohort_records = [r for r in result["records"] if r.record_level == "cohort"]
    assert cohort_records[0].null_control_summary["status"] == "not_provided"


def test_graph_summary_requires_no_separate_mapping_file(tmp_path):
    summary = _write_graph_summary(tmp_path / "graph_summary.json")
    # mapping_path=None is explicitly allowed for a self-contained graph_summary
    result = export_fmri_derivative_transitions(summary, None, tmp_path / "out", no_registry=True)
    assert result["n_written"] == 2


# ── failure modes ─────────────────────────────────────────────────────────


def test_missing_mapping_file_fails_closed(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    try:
        export_fmri_derivative_transitions(features, tmp_path / "no_mapping.json", tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError:
        pass


def test_missing_mapping_for_non_graph_summary_features_fails_closed(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    try:
        export_fmri_derivative_transitions(features, None, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError as exc:
        assert "mapping_path is required" in str(exc)


def test_missing_features_file_fails_closed(tmp_path):
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    try:
        export_fmri_derivative_transitions(tmp_path / "no_features.csv", mapping, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


def test_all_rows_invalid_raises_export_error(tmp_path):
    features_path = tmp_path / "features_bad.csv"
    with features_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition", "atlas_or_parcellation"])
        w.writerow(["", "placebo", "drug", "connectivity.global_efficiency", "0.34", "0.29", "ge", "Schaefer100"])
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    try:
        export_fmri_derivative_transitions(features_path, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterExportError"
    except AdapterExportError:
        pass


# ── registry behavior ──────────────────────────────────────────────────────


def test_allowed_transition_export_succeeds(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        requested_use="transition_export", updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert result["n_written"] == 2
    assert all(d["allowed"] for d in result["registry_decisions"])


def test_forbidden_requested_use_fails_before_writing_output(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    try:
        export_fmri_derivative_transitions(
            features, mapping, out, registry_path=_SEED_REGISTRY, requested_use="final_claim_confirmation",
        )
        assert False, "expected AdapterRegistryError"
    except AdapterRegistryError:
        pass
    assert not (out / "transitions").exists()


def test_seed_registry_not_mutated_in_place(tmp_path):
    original_bytes = _SEED_REGISTRY.read_bytes()
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json", dataset_id="never_seen_fmri_dataset_2")
    export_fmri_derivative_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert _SEED_REGISTRY.read_bytes() == original_bytes


def test_new_dataset_gets_auto_registered_candidate(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json", dataset_id="never_seen_fmri_dataset_3")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    assert result["dataset_record_created"] is True
    updated = BenchmarkRegistry.load(out / "reg.json")
    assert "never_seen_fmri_dataset_3" in updated.datasets
    assert updated.datasets["never_seen_fmri_dataset_3"].current_role == "exploration"


def test_no_registry_explicit_mode_succeeds(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_fmri_derivative_transitions(features, mapping, tmp_path / "out", no_registry=True)
    assert result["n_written"] == 2
    assert result["registry_decisions"] == []


def test_missing_registry_context_fails_closed(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    try:
        export_fmri_derivative_transitions(features, mapping, tmp_path / "out")
        assert False, "expected AdapterRegistryError"
    except AdapterRegistryError:
        pass


# ── phase-space optional integration ────────────────────────────────────


def test_include_phase_space_writes_valid_coordinates(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, updated_registry_out=out / "reg.json",
    )
    assert result["phase_space"] is not None
    assert result["phase_space"]["n_coordinates"] > 0
    from phase_space.store import PhaseSpaceStore

    ps_store = PhaseSpaceStore(out / "phase_space")
    for tid in ps_store.list_records():
        for coord in ps_store.read(tid):
            assert coord.validate() == []


def test_include_phase_space_unsupported_axes_become_insufficient_data(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, updated_registry_out=out / "reg.json",
    )
    from phase_space.store import PhaseSpaceStore

    ps_store = PhaseSpaceStore(out / "phase_space")
    all_coords = [c for tid in ps_store.list_records() for c in ps_store.read(tid)]
    statuses = {c.status for c in all_coords}
    assert "insufficient_data" in statuses
    for c in all_coords:
        if c.status == "insufficient_data":
            assert c.value is None
            assert c.missing_features


def test_include_phase_space_does_not_promote_claim_scope(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, updated_registry_out=out / "reg.json",
    )
    from phase_space.store import PhaseSpaceStore

    ps_store = PhaseSpaceStore(out / "phase_space")
    all_coords = [c for tid in ps_store.list_records() for c in ps_store.read(tid)]
    for c in all_coords:
        assert c.output_claim_scope in ("computational_artifact", "exploratory_metric")
