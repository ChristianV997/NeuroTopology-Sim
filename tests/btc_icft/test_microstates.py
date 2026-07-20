"""Tests for microstates.py -- real modified K-means microstate segmentation
via pycrostates, operating on full recordings (not windows -- see that
module's docstring for why).
"""
from __future__ import annotations

import numpy as np
import pytest

from sciencer_d.btc_icft.level_t.microstates import (
    build_microstate_report,
    compute_microstates_for_recording,
    fit_microstates,
)
from sciencer_d.btc_icft.level_t.spatial_topology import resolve_montage_positions

_NAMES = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "C3", "Cz", "C4"]


# ---------------------------------------------------------------------------
# fit_microstates
# ---------------------------------------------------------------------------

def test_fit_microstates_returns_expected_structure():
    positions, _ = resolve_montage_positions(_NAMES)
    sfreq = 100.0
    signal = np.random.default_rng(0).standard_normal((len(_NAMES), int(sfreq * 15))) * 1e-5

    result = fit_microstates(_NAMES, positions, signal, sfreq, n_clusters=4, n_init=10)
    assert result["n_clusters"] == 4
    assert 0.0 <= result["global_explained_variance"] <= 1.0
    for i in range(4):
        for suffix in ("mean_corr", "gev", "occurrences", "timecov", "meandurs"):
            assert f"{i}_{suffix}" in result["parameters"]
    assert "unlabeled" in result["parameters"]


def test_fit_microstates_timecov_sums_to_approximately_one():
    """Every sample must be assigned to (approximately) one of the
    n_clusters states or "unlabeled" -- their time coverage fractions must
    sum to ~1. Loose tolerance: pycrostates computes occurrences/timecov
    from labeled-segment boundaries (post GFP-peak-based smoothing), not a
    raw per-sample count, so a small (~0.1%) rounding slack versus a naive
    sum is expected and not itself a bug in this wrapper."""
    positions, _ = resolve_montage_positions(_NAMES)
    sfreq = 100.0
    signal = np.random.default_rng(1).standard_normal((len(_NAMES), int(sfreq * 15))) * 1e-5

    result = fit_microstates(_NAMES, positions, signal, sfreq, n_clusters=4, n_init=10)
    params = result["parameters"]
    total = sum(params[f"{i}_timecov"] for i in range(4)) + params["unlabeled"]
    assert total == pytest.approx(1.0, abs=0.01)


def test_fit_microstates_deterministic_with_fixed_random_state():
    """Same random_state must give the same clustering result up to
    floating-point tolerance -- exact bit-for-bit equality isn't expected
    across repeated sklearn/pycrostates fits (non-associative floating-point
    summation inside threaded BLAS calls can differ in the last few
    significant digits even with a fixed seed)."""
    positions, _ = resolve_montage_positions(_NAMES)
    sfreq = 100.0
    signal = np.random.default_rng(2).standard_normal((len(_NAMES), int(sfreq * 15))) * 1e-5

    r1 = fit_microstates(_NAMES, positions, signal, sfreq, n_clusters=4, n_init=10, random_state=7)
    r2 = fit_microstates(_NAMES, positions, signal, sfreq, n_clusters=4, n_init=10, random_state=7)
    assert r1["global_explained_variance"] == pytest.approx(r2["global_explained_variance"], abs=1e-6)
    for key in r1["parameters"]:
        assert r1["parameters"][key] == pytest.approx(r2["parameters"][key], abs=1e-6)


# ---------------------------------------------------------------------------
# compute_microstates_for_recording
# ---------------------------------------------------------------------------

def test_skips_missing_source_file():
    result = compute_microstates_for_recording("/does/not/exist.edf")
    assert result["status"] == "skipped"
    assert "not found" in result["reason"]


def test_skips_unmatched_channel_names(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: 100.0)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: ["Weird1", "Weird2", "Weird3", "Weird4"])
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: 30.0)

    result = compute_microstates_for_recording(str(f))
    assert result["status"] == "skipped"
    assert "no standard montage matched" in result["reason"]


def test_skips_too_few_channels(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: 100.0)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: _NAMES[:3])
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: 30.0)

    result = compute_microstates_for_recording(str(f))
    assert result["status"] == "skipped"
    assert ">=4 channels" in result["reason"]


def test_computes_real_microstates_from_signal(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 100.0
    duration = 20.0
    signal = np.random.default_rng(3).standard_normal((len(_NAMES), int(sfreq * duration))) * 1e-5

    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: _NAMES)
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: duration)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    result = compute_microstates_for_recording(str(f), n_clusters=4, n_init=10, max_duration_s=None)
    assert result["status"] == "computed"
    assert result["montage"] == "standard_1020"
    assert result["n_channels"] == len(_NAMES)
    assert result["duration_used_s"] == duration
    assert 0.0 <= result["global_explained_variance"] <= 1.0


def test_max_duration_s_truncates_recording(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 100.0
    full_duration = 60.0
    captured = {}

    def fake_read_window_signal(path, start, end, pick="mean", max_channels=None):
        captured["start"] = start
        captured["end"] = end
        return np.random.default_rng(4).standard_normal((len(_NAMES), int(sfreq * (end - start)))) * 1e-5

    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: _NAMES)
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: full_duration)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", fake_read_window_signal)

    result = compute_microstates_for_recording(str(f), n_clusters=4, n_init=10, max_duration_s=10.0)
    assert result["status"] == "computed"
    assert captured["end"] == 10.0
    assert result["duration_used_s"] == 10.0


# ---------------------------------------------------------------------------
# build_microstate_report
# ---------------------------------------------------------------------------

def test_build_report_dedupes_by_source_file_not_by_row(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 100.0
    duration = 15.0
    signal = np.random.default_rng(5).standard_normal((len(_NAMES), int(sfreq * duration))) * 1e-5

    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: _NAMES)
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: duration)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    # 10 window rows, but all sharing the SAME single recording (source_file)
    m_rows = [{"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "4"} for i in range(10)]

    report = build_microstate_report(m_rows, sample_size=5, n_clusters=4, max_duration_s=None)
    assert report["status"] == "microstates_computed"
    assert report["n_recordings_total_candidates"] == 1  # one unique recording, not 10 window rows
    assert report["n_recordings_computed"] == 1


def test_build_report_bounds_sample_size(tmp_path, monkeypatch):
    sfreq = 100.0
    duration = 12.0
    signal = np.random.default_rng(6).standard_normal((len(_NAMES), int(sfreq * duration))) * 1e-5

    files = []
    for i in range(8):
        f = tmp_path / f"fake{i}.edf"
        f.write_bytes(b"x")
        files.append(str(f))

    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: _NAMES)
    monkeypatch.setattr("data.bids_ingest.get_recording_duration", lambda path: duration)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [{"row_id": f"r{i}", "source_file": files[i], "window_start_s": "0", "window_end_s": "4"} for i in range(8)]
    report = build_microstate_report(m_rows, sample_size=3, n_clusters=4, max_duration_s=None)
    assert report["n_recordings_total_candidates"] == 8
    assert report["n_recordings_computed"] == 3
