"""Tests for the ds006644/ds005917 fMRI streaming scripts' real-data logic
(participants.tsv parsing, S3 key construction, disk-bounded download+delete).

The underlying pipeline (parcellate_bold/connectivity_matrix/persistent_homology/
graph_metrics) is already covered by tests/test_fmri_tda_pipeline.py; these tests
cover only the new per-dataset orchestration logic, with S3 access mocked.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import tools.stream_process_ds006644 as ds006644_mod
import tools.stream_process_ds005917 as ds005917_mod


_DS006644_PARTICIPANTS_TSV = (
    "participant_id\tspecies\tage\tsex\thandedness\tdrug_allocation\tcondition\tretreat\tcohort\tmeditation_hours\n"
    "sub-01\thomo sapiens\t32\tf\tright\t2\tplacebo\t1\tB\t800\n"
    "sub-02\thomo sapiens\t35\tm\tright\t1\tverum\t2\tD\t1200\n"
    "sub-03\thomo sapiens\t40\tf\tright\t2\tplacebo\t1\tA\t500\n"
)

_DS005917_PARTICIPANTS_TSV = (
    "participant_id\tage\tsex\tBMI\tgroup\tinfusion_1\tinfusion_2\n"
    "sub-MOA101\t29\tM\t27.84\tMDD\td\tp\n"
    "sub-MOA102\t35\tF\t33.17\tMDD\tp\td\n"
    "sub-MOA103\t29\tM\t30.15\tMDD\tp\tn/a\n"  # incomplete crossover -- must be excluded
    "sub-MOA301\t26\tM\t34.7\tHC\td\tp\n"       # not MDD -- must be excluded
)


def _fake_s3_client(tsv_text: str):
    mock_body = MagicMock()
    mock_body.read.return_value = tsv_text.encode("utf-8")
    mock_client = MagicMock()
    mock_client.get_object.return_value = {"Body": mock_body}
    return mock_client


def test_ds006644_group_labels_parsed_from_real_condition_column():
    with patch("boto3.client", return_value=_fake_s3_client(_DS006644_PARTICIPANTS_TSV)):
        labels = ds006644_mod.load_group_labels()
    assert labels == {"sub-01": "placebo", "sub-02": "verum", "sub-03": "placebo"}


def test_ds006644_bold_key_uses_session_and_atlas_matched_space():
    key = ds006644_mod._BOLD_KEY_TMPL.format(sub="sub-05")
    assert key == (
        "ds006644/derivatives/fmriprep/sub-05/ses-02/func/"
        "sub-05_ses-02_task-rest_space-MNI152NLin6Asym_desc-smoothAROMAnonaggr_bold.nii.gz"
    )


def test_ds005917_only_mdd_with_complete_crossover_included():
    with patch("boto3.client", return_value=_fake_s3_client(_DS005917_PARTICIPANTS_TSV)):
        subs = ds005917_mod.load_mdd_complete_subjects()
    assert subs == ["sub-MOA101", "sub-MOA102"]  # MOA103 incomplete, MOA301 not MDD


def test_ds005917_condition_sessions_map_to_real_bids_labels():
    assert ds005917_mod._CONDITIONS == {"drug": "ses-d2", "placebo": "ses-p2"}


def test_ds006644_download_then_delete_disk_bounded(tmp_path, monkeypatch):
    """process_subject must delete the downloaded BOLD file even on success,
    keeping disk usage bounded regardless of cohort size (same pattern as the
    EEG streamers' base_runner.py)."""
    downloaded_marker = tmp_path / "sub-09_ses-02_bold.nii.gz"

    def fake_download(subject, dest_dir):
        downloaded_marker.write_bytes(b"fake-nifti-bytes")
        return downloaded_marker

    fake_result = MagicMock()
    fake_result.error = ""
    monkeypatch.setattr(ds006644_mod, "download_subject_bold", fake_download)
    monkeypatch.setattr(ds006644_mod, "run_subject", lambda **kw: fake_result)

    assert not downloaded_marker.exists()
    ds006644_mod.process_subject("sub-09", "verum", tmp_path)
    assert not downloaded_marker.exists()  # deleted after processing


def test_ds006644_download_deleted_even_on_processing_error(tmp_path, monkeypatch):
    """Disk-bounding must hold even when run_subject raises -- the download
    should never be left behind on failure."""
    downloaded_marker = tmp_path / "sub-10_ses-02_bold.nii.gz"

    def fake_download(subject, dest_dir):
        downloaded_marker.write_bytes(b"fake-nifti-bytes")
        return downloaded_marker

    def fake_run_subject(**kwargs):
        raise RuntimeError("simulated parcellation failure")

    monkeypatch.setattr(ds006644_mod, "download_subject_bold", fake_download)
    monkeypatch.setattr(ds006644_mod, "run_subject", fake_run_subject)

    try:
        ds006644_mod.process_subject("sub-10", "placebo", tmp_path)
    except RuntimeError:
        pass
    assert not downloaded_marker.exists()
