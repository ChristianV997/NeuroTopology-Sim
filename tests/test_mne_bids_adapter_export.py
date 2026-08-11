"""Derived-feature -> TransitionRecordV1 export, registry gating, and
optional phase-space integration. Synthetic miniature fixtures only.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from adapters.mne_bids import (
    AdapterExportError,
    AdapterRegistryError,
    export_mne_bids_derived_transitions,
)
from adapters.mne_bids_features import AdapterDataError
from adapters.validation import AdapterMappingError
from benchmarks.export_registry import BenchmarkRegistry
from transitions.store import TransitionStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _write_long_features(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition"])
        w.writerow(["sub-01", "awake", "sedated", "spectral.alpha_power", "1.5", "0.8", "Welch PSD alpha 8-12Hz mean power"])
        w.writerow(["sub-01", "awake", "sedated", "connectivity.mean_plv", "0.6", "0.3", "Mean pairwise PLV, 19-channel montage"])
        w.writerow(["sub-02", "awake", "sedated", "spectral.alpha_power", "1.2", "0.9", "Welch PSD alpha 8-12Hz mean power"])
        w.writerow(["sub-02", "awake", "sedated", "connectivity.mean_plv", "0.55", "0.35", "Mean pairwise PLV, 19-channel montage"])
    return path


def _write_long_mapping(path: Path, *, dataset_id: str = "smoke_test_lab_001") -> Path:
    mapping = {
        "format": "long",
        "dataset_id": dataset_id,
        "modality": "EEG",
        "preprocessing_provenance": {"pipeline": "mne bandpass+notch+CAR", "source_tool_version": "mne==1.x"},
    }
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _write_wide_features(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "awake_alpha", "sedated_alpha"])
        w.writerow(["sub-01", "1.5", "0.8"])
        w.writerow(["sub-02", "1.2", "0.9"])
    return path


def _write_wide_mapping(path: Path, *, dataset_id: str = "smoke_test_wide_001") -> Path:
    mapping = {
        "format": "wide", "dataset_id": dataset_id, "modality": "EEG",
        "source_state": "awake", "target_state": "sedated",
        "feature_definitions": {"spectral.alpha_power": "Welch PSD alpha 8-12Hz mean power"},
        "features": [{"canonical_name": "spectral.alpha_power", "source_column": "awake_alpha", "target_column": "sedated_alpha"}],
        "preprocessing_provenance": {"pipeline": "mne"},
    }
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


# ── long-format export ───────────────────────────────────────────────────


def test_long_export_writes_valid_transition_records(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
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
    result_a = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out_a", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out_a" / "reg.json",
    )
    result_b = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out_b", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out_b" / "reg.json",
    )
    ids_a = sorted(r.transition_id for r in result_a["records"])
    ids_b = sorted(r.transition_id for r in result_b["records"])
    assert ids_a == ids_b


def test_long_export_preserves_preprocessing_provenance(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.preprocessing_provenance == {"pipeline": "mne bandpass+notch+CAR", "source_tool_version": "mne==1.x"}


def test_long_export_preserves_source_artifact_paths(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.artifact_paths["mapping"] == str(mapping)
        assert record.artifact_paths["features_table"] == str(features)


def test_long_export_null_controls_not_fabricated(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert record.null_control_summary["status"] == "not_provided"


def test_long_export_records_feature_set_id_in_metadata(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    for record in result["records"]:
        assert "feature_set_id" in record.metadata
        assert record.metadata["feature_set_id"].startswith("mne_bids_derived::")


def test_long_export_uses_transition_store_layout(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    store = TransitionStore(out / "transitions")
    assert len(store.list_records()) == 2


def test_long_export_claim_scope_and_evidence_level_defaults(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
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
    result = export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert result["n_written"] == 2
    for record in result["records"]:
        assert record.validate() == []
        assert record.feature_names == ["spectral.alpha_power"]


def test_wide_export_never_infers_state_from_column_names(tmp_path):
    """A wide table with column names implying awake/sedated must still
    fail closed if the mapping omits source_state/target_state -- proving
    the adapter never parses column-name substrings for state labels."""
    features = _write_wide_features(tmp_path / "features_wide.csv")
    mapping_path = tmp_path / "mapping_wide_no_states.json"
    bad_mapping = {
        "format": "wide", "dataset_id": "d", "modality": "EEG",
        "feature_definitions": {"spectral.alpha_power": "alpha power"},
        "features": [{"canonical_name": "spectral.alpha_power", "source_column": "awake_alpha", "target_column": "sedated_alpha"}],
        "preprocessing_provenance": {"pipeline": "mne"},
    }
    mapping_path.write_text(json.dumps(bad_mapping), encoding="utf-8")
    try:
        export_mne_bids_derived_transitions(features, mapping_path, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError as exc:
        assert "source_state" in str(exc) or "target_state" in str(exc)


# ── failure modes ─────────────────────────────────────────────────────────


def test_missing_mapping_file_fails_closed(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    try:
        export_mne_bids_derived_transitions(features, tmp_path / "no_mapping.json", tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError:
        pass


def test_missing_features_file_fails_closed(tmp_path):
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    try:
        export_mne_bids_derived_transitions(tmp_path / "no_features.csv", mapping, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


def test_all_rows_invalid_raises_export_error(tmp_path):
    features_path = tmp_path / "features_bad.csv"
    with features_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition"])
        w.writerow(["", "awake", "sedated", "spectral.alpha_power", "1.5", "0.8", "alpha power"])
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    try:
        export_mne_bids_derived_transitions(features_path, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterExportError"
    except AdapterExportError:
        pass


def test_ambiguous_pairing_wide_missing_features_key_fails_closed(tmp_path):
    features = _write_wide_features(tmp_path / "features_wide.csv")
    mapping_path = tmp_path / "mapping_no_features.json"
    bad_mapping = {
        "format": "wide", "dataset_id": "d", "modality": "EEG",
        "source_state": "awake", "target_state": "sedated",
        "feature_definitions": {"spectral.alpha_power": "alpha power"},
        "preprocessing_provenance": {"pipeline": "mne"},
    }
    mapping_path.write_text(json.dumps(bad_mapping), encoding="utf-8")
    try:
        export_mne_bids_derived_transitions(features, mapping_path, tmp_path / "out", registry_path=_SEED_REGISTRY)
        assert False, "expected AdapterMappingError"
    except AdapterMappingError as exc:
        assert "features" in str(exc)


# ── registry behavior ──────────────────────────────────────────────────────


def test_allowed_transition_export_succeeds(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(
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
        export_mne_bids_derived_transitions(
            features, mapping, out, registry_path=_SEED_REGISTRY, requested_use="final_claim_confirmation",
        )
        assert False, "expected AdapterRegistryError"
    except AdapterRegistryError:
        pass
    assert not (out / "transitions").exists()


def test_candidate_dataset_cannot_get_confirmatory_use(tmp_path):
    """A brand-new candidate dataset (auto-registered because no prior
    entry existed) must never be usable for a confirmatory claim, even
    though a valid mapping was supplied."""
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json", dataset_id="never_seen_before_dataset")
    try:
        export_mne_bids_derived_transitions(
            features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
            requested_use="cross_dataset_replication_claim",
        )
        assert False, "expected AdapterRegistryError"
    except AdapterRegistryError:
        pass


def test_seed_registry_not_mutated_in_place(tmp_path):
    original_bytes = _SEED_REGISTRY.read_bytes()
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json", dataset_id="never_seen_before_dataset_2")
    export_mne_bids_derived_transitions(
        features, mapping, tmp_path / "out", registry_path=_SEED_REGISTRY,
        updated_registry_out=tmp_path / "out" / "reg.json",
    )
    assert _SEED_REGISTRY.read_bytes() == original_bytes


def test_new_dataset_gets_auto_registered_candidate(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json", dataset_id="never_seen_before_dataset_3")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    assert result["dataset_record_created"] is True
    updated = BenchmarkRegistry.load(out / "reg.json")
    assert "never_seen_before_dataset_3" in updated.datasets
    assert updated.datasets["never_seen_before_dataset_3"].current_role == "exploration"


def test_no_registry_explicit_mode_succeeds(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    result = export_mne_bids_derived_transitions(features, mapping, tmp_path / "out", no_registry=True)
    assert result["n_written"] == 2
    assert result["registry_decisions"] == []


def test_missing_registry_context_fails_closed(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    try:
        export_mne_bids_derived_transitions(features, mapping, tmp_path / "out")
        assert False, "expected AdapterRegistryError"
    except AdapterRegistryError:
        pass


# ── phase-space optional integration ────────────────────────────────────


def test_include_phase_space_writes_valid_coordinates(tmp_path):
    features = _write_long_features(tmp_path / "features.csv")
    mapping = _write_long_mapping(tmp_path / "mapping.json")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
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
    export_mne_bids_derived_transitions(
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
    export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, updated_registry_out=out / "reg.json",
    )
    from phase_space.store import PhaseSpaceStore

    ps_store = PhaseSpaceStore(out / "phase_space")
    all_coords = [c for tid in ps_store.list_records() for c in ps_store.read(tid)]
    for c in all_coords:
        assert c.output_claim_scope in ("computational_artifact", "exploratory_metric")
