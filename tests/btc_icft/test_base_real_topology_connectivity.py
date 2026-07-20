"""Tests for base_real_topology.py's Phase 3 (beyond-topology) addition: real
PLV/PLI/wPLI connectivity and optional directed Granger causality, wired into
the dataset pipeline for the first time (previously only existed in the
separate analysis/itct/ script) -- additive alongside the existing
channel-mean/correlation q_net/q_abs/f_dress.
"""
from __future__ import annotations

import numpy as np

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyRow,
    build_connectivity_report,
    compute_connectivity_for_window,
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
    result = compute_connectivity_for_window(m_row)
    assert result["status"] == "skipped"
    assert "not found" in result["reason"]


def test_skips_single_channel(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.random.default_rng(0).standard_normal((1, 500))
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    result = compute_connectivity_for_window(m_row)
    assert result["status"] == "skipped"
    assert ">=2 channels" in result["reason"]


def test_computes_real_connectivity_metrics(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 10 * t)
    signal = np.array([base + 0.05 * np.random.default_rng(i).standard_normal(1000) for i in range(4)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "4"}
    result = compute_connectivity_for_window(m_row, methods=("plv", "pli", "wpli"))
    assert result["status"] == "computed"
    assert result["n_channels"] == 4
    for m in ("plv", "pli", "wpli"):
        assert f"mean_{m}" in result
        assert np.isfinite(result[f"mean_{m}"])
        matrix = np.array(result[f"{m}_matrix"])
        assert matrix.shape == (4, 4)
        assert np.allclose(matrix, matrix.T)


def test_granger_opt_in_off_by_default(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.random.default_rng(0).standard_normal((3, 300))
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    result = compute_connectivity_for_window(m_row)
    assert "granger_causality_p_values" not in result


def test_granger_computed_when_requested(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.random.default_rng(0).standard_normal((3, 300))
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    result = compute_connectivity_for_window(m_row, compute_granger=True, granger_maxlag=3)
    assert "granger_causality_p_values" in result
    assert len(result["granger_causality_p_values"]) == 3 * 2
    assert "n_significant_granger_pairs" in result


def test_deterministic(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    t = np.linspace(0, 2, 500)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.2) for i in range(3)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    r1 = compute_connectivity_for_window(m_row)
    r2 = compute_connectivity_for_window(m_row)
    assert r1 == r2


def test_build_report_aggregates_and_bounds_sample_size(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    t = np.linspace(0, 2, 500)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.2) for i in range(4)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [
        {"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
        for i in range(10)
    ]
    t_rows = [_make_t_row(f"r{i}") for i in range(10)]

    report = build_connectivity_report(t_rows, m_rows, sample_size=3)
    assert report["status"] == "connectivity_computed"
    assert report["n_windows_computed"] == 3
    assert report["n_windows_total_candidates"] == 10
    assert np.isfinite(report["mean_plv"])


def test_build_report_no_sampling_by_default(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    t = np.linspace(0, 2, 500)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.2) for i in range(4)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [
        {"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
        for i in range(5)
    ]
    t_rows = [_make_t_row(f"r{i}") for i in range(5)]
    report = build_connectivity_report(t_rows, m_rows)
    assert report["n_windows_computed"] == 5
