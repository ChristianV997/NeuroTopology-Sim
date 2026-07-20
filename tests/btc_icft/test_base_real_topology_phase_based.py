"""Tests for base_real_topology.py's Phase 0 (beyond-topology) addition: real
band-specific Hilbert-phase topology, replacing nothing but adding a genuinely
phase-based instrument alongside the existing channel-mean/correlation
heuristic (compute_real_topology_for_window).
"""
from __future__ import annotations

import numpy as np

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyRow,
    build_phase_based_topology_report,
    compute_phase_based_topology_for_window,
)


def _make_t_row(row_id, subject_id="sub-001"):
    return LevelTRealTopologyRow(
        row_id=row_id, subject_id=subject_id, session_id=None, run_id=None,
        window_id="win-0", task_label="x", q_net=0.1, q_abs=0.2, f_dress=0.05,
        defect_density=0.01, n_triangles=10, n_valid_triangles=10, topology_quality=1.0,
        null_method="real_none", null_seed=0, source_file="a", window_start_s=0.0,
        window_end_s=1.0, warnings=[],
    )


def test_skips_missing_source_file():
    m_row = {"row_id": "r1", "source_file": "/does/not/exist.edf", "window_start_s": "0", "window_end_s": "1"}
    result = compute_phase_based_topology_for_window(m_row)
    assert result["status"] == "skipped"
    assert "not found" in result["reason"]


def test_rejects_unknown_band():
    m_row = {"row_id": "r1", "source_file": "/does/not/exist.edf", "window_start_s": "0", "window_end_s": "1"}
    try:
        compute_phase_based_topology_for_window(m_row, band="not_a_real_band")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not_a_real_band" in str(e)


def test_computes_real_phase_based_metrics(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 250.0
    t = np.arange(0, 4, 1 / sfreq)
    # 4 channels sharing a common 10 Hz (alpha-band) oscillation with small
    # per-channel phase offsets -- genuine, nonzero cross-channel phase
    # structure in the alpha band specifically.
    signal = np.array([
        np.sin(2 * np.pi * 10 * t + i * 0.3) + 0.05 * np.random.default_rng(i).standard_normal(t.size)
        for i in range(4)
    ])
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "4"}
    result = compute_phase_based_topology_for_window(m_row, band="alpha")
    assert result["status"] == "computed"
    assert result["band"] == "alpha"
    assert result["metric_kind"] == "analytic_phase_proxy"
    for key in ("Q", "Qabs", "phase_grad", "f_dress"):
        assert key in result
        assert np.isfinite(result[key])


def test_skips_band_above_nyquist(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    low_sfreq = 50.0  # Nyquist 25 Hz, below gamma_low's 45 Hz upper edge
    signal = np.random.default_rng(0).standard_normal((4, 200))
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: low_sfreq)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "4"}
    result = compute_phase_based_topology_for_window(m_row, band="gamma_low")
    assert result["status"] == "skipped"
    assert "Nyquist" in result["reason"]


def test_skips_single_channel(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.random.default_rng(0).standard_normal((1, 500))
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: 250.0)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    result = compute_phase_based_topology_for_window(m_row, band="alpha")
    assert result["status"] == "skipped"
    assert ">=2 channels" in result["reason"]


def test_skips_window_too_short_for_filter(tmp_path, monkeypatch):
    """ds001787's probe_locked windows can be as short as ~1s -- too few samples
    for sosfiltfilt's padding requirement at this filter order. Must be a
    graceful skip (matching this module's existing skip-and-report
    convention), not an unhandled exception propagating out of the report
    builder."""
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.random.default_rng(0).standard_normal((3, 10))  # far too few samples
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: 250.0)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "0.04"}
    result = compute_phase_based_topology_for_window(m_row, band="alpha")
    assert result["status"] == "skipped"
    assert "phase extraction failed" in result["reason"]


def test_deterministic(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 250.0
    t = np.arange(0, 2, 1 / sfreq)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.2) for i in range(3)])
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    r1 = compute_phase_based_topology_for_window(m_row, band="alpha")
    r2 = compute_phase_based_topology_for_window(m_row, band="alpha")
    assert r1 == r2


def test_build_report_aggregates_and_bounds_sample_size(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 250.0
    t = np.arange(0, 2, 1 / sfreq)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.2) for i in range(4)])
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [
        {"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
        for i in range(10)
    ]
    t_rows = [_make_t_row(f"r{i}") for i in range(10)]

    report = build_phase_based_topology_report(t_rows, m_rows, band="alpha", sample_size=3)
    assert report["status"] == "phase_based_topology_computed"
    assert report["n_windows_computed"] == 3  # bounded by sample_size
    assert report["n_windows_total_candidates"] == 10
    assert np.isfinite(report["mean_Qabs"])


def test_build_report_no_sampling_by_default(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    sfreq = 250.0
    t = np.arange(0, 2, 1 / sfreq)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.2) for i in range(4)])
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [
        {"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
        for i in range(5)
    ]
    t_rows = [_make_t_row(f"r{i}") for i in range(5)]
    report = build_phase_based_topology_report(t_rows, m_rows, band="alpha")
    assert report["n_windows_computed"] == 5
