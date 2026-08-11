"""fMRIPrep-style metadata scan: dataset_description.json/participants.tsv/
confounds TSV/derivative JSON sidecar presence and content, conservative
DatasetRecordV1/ArtifactRecordV1 generation. Synthetic miniature fixtures
only -- no real fMRIPrep output, no raw BOLD, no network access.
"""
from __future__ import annotations

import json

from adapters.fmri_derivatives import (
    make_artifact_records_from_fmri_derivatives,
    make_dataset_record_from_fmri_derivatives,
    scan_fmri_derivatives_metadata,
)
from adapters.fmri_derivatives_features import AdapterDataError


def _make_derivatives_root(tmp_path, *, with_description=True, with_participants=True, with_confounds=True, with_fmriprep_dd=True):
    root = tmp_path / "derivatives_root"
    (root / "sub-01" / "func").mkdir(parents=True, exist_ok=True)
    if with_description:
        (root / "dataset_description.json").write_text(
            json.dumps({"Name": "Tiny Test fMRI Derivatives", "BIDSVersion": "1.8.0"}), encoding="utf-8",
        )
    if with_fmriprep_dd:
        (root / "derivatives" / "fmriprep").mkdir(parents=True, exist_ok=True)
        (root / "derivatives" / "fmriprep" / "dataset_description.json").write_text(
            json.dumps({"Name": "fMRIPrep - fMRIPrep derivatives", "PipelineDescription": {"Name": "fMRIPrep", "Version": "23.1.0"}}),
            encoding="utf-8",
        )
    if with_participants:
        (root / "participants.tsv").write_text("participant_id\tage\tsex\nsub-01\t28\tF\nsub-02\t34\tM\n", encoding="utf-8")
    if with_confounds:
        (root / "sub-01" / "func" / "sub-01_task-rest_desc-confounds_timeseries.tsv").write_text(
            "framewise_displacement\tcsf\twhite_matter\n0.1\t100.2\t50.1\n0.2\t101.3\t50.5\n", encoding="utf-8",
        )
        (root / "sub-01" / "func" / "sub-01_task-rest_desc-confounds_timeseries.json").write_text(
            json.dumps({"framewise_displacement": {"Description": "FD per Power et al."}}), encoding="utf-8",
        )
    return root


def test_scan_reads_dataset_description(tmp_path):
    root = _make_derivatives_root(tmp_path)
    summary = scan_fmri_derivatives_metadata(root)
    assert summary.dataset_description is not None
    assert summary.dataset_description["Name"] == "Tiny Test fMRI Derivatives"
    assert summary.dataset_id == "tiny-test-fmri-derivatives"


def test_scan_reads_fmriprep_derivatives_dataset_description(tmp_path):
    root = _make_derivatives_root(tmp_path)
    summary = scan_fmri_derivatives_metadata(root)
    assert summary.fmriprep_dataset_description is not None
    assert summary.fmriprep_dataset_description["PipelineDescription"]["Name"] == "fMRIPrep"


def test_scan_reads_participants_tsv(tmp_path):
    root = _make_derivatives_root(tmp_path)
    summary = scan_fmri_derivatives_metadata(root)
    assert summary.n_subjects == 2
    assert summary.participants[0]["participant_id"] == "sub-01"


def test_scan_detects_confounds_tsv_when_present(tmp_path):
    root = _make_derivatives_root(tmp_path)
    summary = scan_fmri_derivatives_metadata(root)
    assert len(summary.confounds_files) == 1
    assert summary.confounds_files[0].endswith("sub-01_task-rest_desc-confounds_timeseries.tsv")
    assert summary.confounds_entities[0]["sub"] == "01"
    assert summary.confounds_entities[0]["task"] == "rest"


def test_scan_detects_derivative_metadata_json_sidecar(tmp_path):
    root = _make_derivatives_root(tmp_path)
    summary = scan_fmri_derivatives_metadata(root)
    assert any(f.endswith("confounds_timeseries.json") for f in summary.derivative_metadata_files)


def test_scan_handles_missing_confounds_gracefully(tmp_path):
    root = _make_derivatives_root(tmp_path, with_confounds=False)
    summary = scan_fmri_derivatives_metadata(root)
    assert summary.confounds_files == []


def test_scan_detects_fmri_modality_from_func_dir(tmp_path):
    root = _make_derivatives_root(tmp_path)
    summary = scan_fmri_derivatives_metadata(root)
    assert summary.modalities_declared == ["fMRI"]


def test_scan_falls_back_to_unknown_modality_with_no_func_or_confounds(tmp_path):
    root = tmp_path / "derivatives_flat"
    root.mkdir()
    (root / "dataset_description.json").write_text(json.dumps({"Name": "No Func Dir"}), encoding="utf-8")
    summary = scan_fmri_derivatives_metadata(root)
    assert summary.modalities_declared == ["unknown"]


def test_scan_fails_closed_on_nonexistent_root(tmp_path):
    try:
        scan_fmri_derivatives_metadata(tmp_path / "does_not_exist")
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


def test_scan_fails_closed_on_malformed_dataset_description(tmp_path):
    root = tmp_path / "derivatives_bad_json"
    root.mkdir()
    (root / "dataset_description.json").write_text("{not valid json", encoding="utf-8")
    try:
        scan_fmri_derivatives_metadata(root)
        assert False, "expected AdapterDataError"
    except AdapterDataError:
        pass


# ── conservative DatasetRecordV1 generation ──────────────────────────────


def test_dataset_record_defaults_to_exploration_role(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    record = make_dataset_record_from_fmri_derivatives(summary)
    assert record.current_role == "exploration"
    assert record.contamination_status == "unseen"


def test_dataset_record_excludes_transition_export_without_mapping(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    record = make_dataset_record_from_fmri_derivatives(summary, mapping_provided=False)
    assert "transition_export" not in record.allowed_uses
    assert "documentation" in record.allowed_uses
    assert "feature_design" in record.allowed_uses


def test_dataset_record_includes_transition_export_with_mapping(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    record = make_dataset_record_from_fmri_derivatives(summary, mapping_provided=True)
    assert "transition_export" in record.allowed_uses


def test_dataset_record_never_marks_validation_ready(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    record = make_dataset_record_from_fmri_derivatives(summary)
    assert record.current_role not in ("locked_internal_validation", "locked_external_validation")
    assert record.validation_lock is None


def test_dataset_record_is_structurally_valid(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    record = make_dataset_record_from_fmri_derivatives(summary)
    assert record.validate() == []


def test_dataset_record_has_forbidden_claim_uses(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    record = make_dataset_record_from_fmri_derivatives(summary)
    for use in ("clinical_claim", "diagnostic_claim", "treatment_claim", "mechanistic_causal_claim", "prospective_prediction_claim"):
        assert use in record.forbidden_uses


# ── conservative ArtifactRecordV1 generation ─────────────────────────────


def test_artifact_records_one_per_metadata_file(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    records = make_artifact_records_from_fmri_derivatives(summary)
    kinds = {r.artifact_kind for r in records}
    assert "bids_dataset_description" in kinds
    assert "fmriprep_dataset_description" in kinds
    assert "bids_participants_tsv" in kinds
    assert "fmriprep_confounds_timeseries_tsv" in kinds
    assert "fmriprep_derivative_metadata" in kinds


def test_artifact_records_are_external(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    records = make_artifact_records_from_fmri_derivatives(summary)
    assert all(r.external for r in records)


def test_artifact_records_are_structurally_valid(tmp_path):
    summary = scan_fmri_derivatives_metadata(_make_derivatives_root(tmp_path))
    records = make_artifact_records_from_fmri_derivatives(summary)
    assert records
    for r in records:
        assert r.validate() == []


def test_artifact_records_skip_absent_files(tmp_path):
    root = _make_derivatives_root(tmp_path, with_participants=False, with_confounds=False, with_fmriprep_dd=False)
    summary = scan_fmri_derivatives_metadata(root)
    records = make_artifact_records_from_fmri_derivatives(summary)
    kinds = {r.artifact_kind for r in records}
    assert "bids_participants_tsv" not in kinds
    assert "fmriprep_confounds_timeseries_tsv" not in kinds
    assert "fmriprep_dataset_description" not in kinds
