"""Offline tests for the empirical readiness evaluator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.empirical_readiness.evaluator import (
    SCHEMA,
    ReadinessError,
    evaluate_readiness,
    serialize_report,
)


def _recording(path: Path, **overrides):
    path.write_bytes(b"local-fixture")
    record = {
        "subject_id": "sub-01",
        "session_id": "ses-01",
        "condition_label": "meditation",
        "local_path": str(path),
        "file_checksum_sha256": "abc123",
        "origin": "empirical_local",
        "sampling_rate_hz": 250.0,
        "channel_count": 32,
        "units": {"time": "s", "sampling_frequency": "Hz", "amplitude": "V"},
        "montage_state": "10-20",
        "preprocessing_steps": ["bandpass 0.5-40 Hz"],
        "container_capability": "ok",
        "format": "edf",
    }
    record.update(overrides)
    return record


def _packet(recordings, *, min_pairs=2, extra=None):
    packet = {
        "min_pairs_required": min_pairs,
        "min_channels": 8,
        "requested_band_hz": {"low_hz": 0.5, "high_hz": 40.0},
        "recordings": recordings,
        "topology": {"engine": "ripser", "maxdim": 1, "recorded": True},
        "statistics": {
            "null_controls": ["phase_shuffle", "label_permutation"],
            "multiple_comparison_policy": "holm",
        },
    }
    if extra:
        packet.update(extra)
    return packet


def _paired(tmp_path: Path, n_subjects: int, **rec_overrides):
    recordings = []
    pairs = []
    for index in range(1, n_subjects + 1):
        subject = f"sub-{index:02d}"
        med = tmp_path / f"{subject}_med.edf"
        ctl = tmp_path / f"{subject}_ctl.edf"
        recordings.append(_recording(med, subject_id=subject, condition_label="meditation", **rec_overrides))
        recordings.append(_recording(ctl, subject_id=subject, condition_label="control", **rec_overrides))
        pairs.append({"subject_id": subject, "conditions": ["meditation", "control"]})
    return recordings, pairs


def test_valid_local_empirical_metadata(tmp_path):
    recordings, pairs = _paired(tmp_path, 8)
    report = evaluate_readiness(_packet(recordings, min_pairs=8, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "READY_FOR_FORMAL_EVIDENCE_REVIEW"
    assert report.descriptive_ready is True
    assert report.paired_ready is True
    assert report.formal_evidence_eligible is True
    assert report.to_dict()["scientific_support"] == "not_claimed"


def test_synthetic_only_input(tmp_path):
    recordings, pairs = _paired(tmp_path, 8, origin="synthetic_demo")
    report = evaluate_readiness(_packet(recordings, min_pairs=8, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "SYNTHETIC_DEMO_ONLY"
    assert report.formal_evidence_eligible is False
    assert report.descriptive_ready is False


def test_insufficient_pairs(tmp_path):
    recordings, pairs = _paired(tmp_path, 2)
    report = evaluate_readiness(_packet(recordings, min_pairs=8, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "INSUFFICIENT_PAIRED_SUBJECTS"
    assert report.n_paired_subjects == 2
    assert report.formal_evidence_eligible is False


def test_incomplete_montage(tmp_path):
    recordings, pairs = _paired(tmp_path, 2, montage_state="unavailable")
    report = evaluate_readiness(_packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "INCOMPLETE_PROVENANCE"
    assert any("montage" in reason for reason in report.reasons)


def test_invalid_sample_rate(tmp_path):
    recordings, pairs = _paired(tmp_path, 2, sampling_rate_hz=50.0)
    report = evaluate_readiness(_packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "UNSUPPORTED_SAMPLING_RATE"


def test_missing_units(tmp_path):
    recordings, pairs = _paired(tmp_path, 2, units={"time": "s"})
    report = evaluate_readiness(_packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "INCOMPLETE_PROVENANCE"
    assert any("units" in reason for reason in report.reasons)


def test_missing_preprocessing(tmp_path):
    recordings, pairs = _paired(tmp_path, 2, preprocessing_steps=[])
    report = evaluate_readiness(_packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "INCOMPLETE_PROVENANCE"
    assert any("preprocessing" in reason for reason in report.reasons)


def test_missing_null_controls(tmp_path):
    recordings, pairs = _paired(tmp_path, 2)
    packet = _packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}})
    packet["statistics"] = {"null_controls": [], "multiple_comparison_policy": "holm"}
    report = evaluate_readiness(packet)
    assert report.formal_evidence_eligible is False
    assert report.status != "READY_FOR_FORMAL_EVIDENCE_REVIEW"
    assert any("null-control" in reason for reason in report.reasons)


def test_missing_optional_mne(tmp_path):
    recordings, pairs = _paired(
        tmp_path,
        2,
        container_capability="missing_optional_dependency",
        optional_dependency="mne",
        format="fif",
    )
    report = evaluate_readiness(_packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}}))
    assert report.status == "MISSING_OPTIONAL_DEPENDENCY"
    assert report.missing_optional_dependency == "mne"


def test_deterministic_repeat(tmp_path):
    recordings, pairs = _paired(tmp_path, 8)
    packet = _packet(recordings, min_pairs=8, extra={"cohort": {"pairs": pairs}})
    first = serialize_report(evaluate_readiness(packet))
    second = serialize_report(evaluate_readiness(packet))
    assert first == second
    loaded = json.loads(first)
    assert loaded["schema"] == SCHEMA
    assert loaded["signals_loaded"] is False
    assert loaded["bayes_factor_computed"] is False


def test_finite_json(tmp_path):
    recordings, _pairs = _paired(tmp_path, 1)
    recordings[0]["sampling_rate_hz"] = float("nan")
    with pytest.raises(ReadinessError, match="finite"):
        evaluate_readiness(_packet(recordings, min_pairs=1))


def test_descriptive_vs_formal_evidence(tmp_path):
    recordings, pairs = _paired(tmp_path, 3)
    packet = _packet(recordings, min_pairs=2, extra={"cohort": {"pairs": pairs}})
    packet["statistics"] = {"null_controls": [], "multiple_comparison_policy": None}
    report = evaluate_readiness(packet)
    assert report.status == "READY_FOR_PAIRED_STATISTICS"
    assert report.descriptive_ready is True
    assert report.paired_ready is True
    assert report.formal_evidence_eligible is False
