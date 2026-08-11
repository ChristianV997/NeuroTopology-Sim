"""BIDS metadata scan: dataset_description.json/participants.tsv/
*_events.tsv file presence and content, conservative DatasetRecordV1/
ArtifactRecordV1 generation. Synthetic miniature fixtures only -- no real
BIDS dataset, no raw signal files, no network access.
"""
from __future__ import annotations

import json

from adapters.mne_bids import make_artifact_records_from_bids, make_dataset_record_from_bids, scan_bids_metadata
from adapters.mne_bids_features import AdapterDataError


def _make_bids_root(tmp_path, *, with_description=True, with_participants=True, with_events=True):
    root = tmp_path / "bids_root"
    (root / "sub-01" / "eeg").mkdir(parents=True, exist_ok=True)
    if with_description:
        (root / "dataset_description.json").write_text(
            json.dumps({"Name": "Tiny Test EEG Dataset", "BIDSVersion": "1.8.0"}), encoding="utf-8",
        )
    if with_participants:
        (root / "participants.tsv").write_text("participant_id\tage\tsex\nsub-01\t30\tF\nsub-02\t45\tM\n", encoding="utf-8")
    if with_events:
        (root / "sub-01" / "eeg" / "sub-01_task-rest_events.tsv").write_text(
            "onset\tduration\ttrial_type\n0\t60\trest\n60\t60\tsedation\n", encoding="utf-8",
        )
    return root


def test_scan_reads_dataset_description(tmp_path):
    root = _make_bids_root(tmp_path)
    summary = scan_bids_metadata(root)
    assert summary.dataset_description is not None
    assert summary.dataset_description["Name"] == "Tiny Test EEG Dataset"
    assert summary.dataset_id == "tiny-test-eeg-dataset"


def test_scan_reads_participants_tsv(tmp_path):
    root = _make_bids_root(tmp_path)
    summary = scan_bids_metadata(root)
    assert summary.n_subjects == 2
    assert summary.participants[0]["participant_id"] == "sub-01"


def test_scan_reads_events_tsv_when_present(tmp_path):
    root = _make_bids_root(tmp_path)
    summary = scan_bids_metadata(root)
    assert len(summary.events_files) == 1
    assert summary.events_files[0].endswith("sub-01_task-rest_events.tsv")


def test_scan_handles_missing_events_gracefully(tmp_path):
    root = _make_bids_root(tmp_path, with_events=False)
    summary = scan_bids_metadata(root)
    assert summary.events_files == []


def test_scan_detects_eeg_modality_directory(tmp_path):
    root = _make_bids_root(tmp_path)
    summary = scan_bids_metadata(root)
    assert summary.modalities_declared == ["EEG"]


def test_scan_falls_back_to_unknown_modality_with_no_modality_dirs(tmp_path):
    root = tmp_path / "bids_root_flat"
    root.mkdir()
    (root / "dataset_description.json").write_text(json.dumps({"Name": "No Modality Dirs"}), encoding="utf-8")
    summary = scan_bids_metadata(root)
    assert summary.modalities_declared == ["unknown"]


def test_scan_falls_back_to_dir_name_dataset_id_without_description(tmp_path):
    root = _make_bids_root(tmp_path, with_description=False)
    summary = scan_bids_metadata(root)
    assert summary.dataset_id == "bids-root"


def test_scan_fails_closed_on_nonexistent_root(tmp_path):
    try:
        scan_bids_metadata(tmp_path / "does_not_exist")
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


def test_scan_fails_closed_on_malformed_dataset_description(tmp_path):
    root = tmp_path / "bids_root_bad_json"
    root.mkdir()
    (root / "dataset_description.json").write_text("{not valid json", encoding="utf-8")
    try:
        scan_bids_metadata(root)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


# ── conservative DatasetRecordV1 generation ──────────────────────────────


def test_dataset_record_defaults_to_exploration_role(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    record = make_dataset_record_from_bids(summary)
    assert record.current_role == "exploration"
    assert record.contamination_status == "unseen"


def test_dataset_record_excludes_transition_export_without_mapping(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    record = make_dataset_record_from_bids(summary, mapping_provided=False)
    assert "transition_export" not in record.allowed_uses
    assert "documentation" in record.allowed_uses
    assert "feature_design" in record.allowed_uses


def test_dataset_record_includes_transition_export_with_mapping(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    record = make_dataset_record_from_bids(summary, mapping_provided=True)
    assert "transition_export" in record.allowed_uses


def test_dataset_record_never_marks_validation_ready(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    record = make_dataset_record_from_bids(summary)
    assert record.current_role not in ("locked_internal_validation", "locked_external_validation")
    assert record.validation_lock is None


def test_dataset_record_is_structurally_valid(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    record = make_dataset_record_from_bids(summary)
    assert record.validate() == []


def test_dataset_record_has_forbidden_claim_uses(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    record = make_dataset_record_from_bids(summary)
    for use in ("clinical_claim", "diagnostic_claim", "treatment_claim", "mechanistic_causal_claim"):
        assert use in record.forbidden_uses


# ── conservative ArtifactRecordV1 generation ─────────────────────────────


def test_artifact_records_one_per_metadata_file(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    records = make_artifact_records_from_bids(summary)
    kinds = {r.artifact_kind for r in records}
    assert kinds == {"bids_dataset_description", "bids_participants_tsv", "bids_events_tsv"}


def test_artifact_records_are_external(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    records = make_artifact_records_from_bids(summary)
    assert all(r.external for r in records)


def test_artifact_records_are_structurally_valid(tmp_path):
    summary = scan_bids_metadata(_make_bids_root(tmp_path))
    records = make_artifact_records_from_bids(summary)
    assert records
    for r in records:
        assert r.validate() == []


def test_artifact_records_skip_absent_files(tmp_path):
    root = _make_bids_root(tmp_path, with_participants=False, with_events=False)
    summary = scan_bids_metadata(root)
    records = make_artifact_records_from_bids(summary)
    kinds = {r.artifact_kind for r in records}
    assert "bids_participants_tsv" not in kinds
    assert "bids_events_tsv" not in kinds
