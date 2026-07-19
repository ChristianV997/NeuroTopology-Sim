"""Tests for base_real_topology.py's Phase 3 additions: real surrogate null
gating and group significance reporting -- both replace what were previously
self-reporting "not run" placeholders.
"""
from __future__ import annotations

import numpy as np

from sciencer_d.btc_icft.level_t.base_real_topology import (
    build_group_significance_report,
    build_null_gate_report,
    compute_surrogate_gate_for_window,
)


def _make_t_row(row_id, subject_id, q_net=0.1, q_abs=0.2, f_dress=0.05, defect_density=0.01):
    from sciencer_d.btc_icft.level_t.base_real_topology import LevelTRealTopologyRow

    return LevelTRealTopologyRow(
        row_id=row_id, subject_id=subject_id, session_id=None, run_id=None, window_id="win-0",
        task_label="x", q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
        n_triangles=10, n_valid_triangles=10, topology_quality=1.0, null_method="real_none",
        null_seed=0, source_file="a", window_start_s=0.0, window_end_s=1.0, warnings=[],
    )


# ---------------------------------------------------------------------------
# compute_surrogate_gate_for_window / build_null_gate_report
# ---------------------------------------------------------------------------

def test_surrogate_gate_skips_missing_source_file():
    m_row = {"row_id": "r1", "source_file": "/does/not/exist.edf", "window_start_s": "0", "window_end_s": "1"}
    result = compute_surrogate_gate_for_window(m_row, n_surrogates=5)
    assert result["status"] == "skipped"
    assert "not found" in result["reason"]


def test_surrogate_gate_computes_real_z_score(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    # structured, genuinely cross-channel-correlated signal (not independent noise)
    t = np.linspace(0, 1, 200)
    base = np.sin(2 * np.pi * 5 * t)
    signal = np.array([base + 0.1 * np.random.default_rng(i).standard_normal(200) for i in range(6)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "1"}
    result = compute_surrogate_gate_for_window(m_row, n_surrogates=20, seed=0)
    assert result["status"] == "gated"
    assert result["n_surrogates"] == 20
    assert "z" in result and "observed" in result and "null_mean" in result


def test_surrogate_gate_deterministic(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.array([[float((i + ch * 3) % 11) for i in range(100)] for ch in range(4)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)
    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "1"}
    r1 = compute_surrogate_gate_for_window(m_row, n_surrogates=10, seed=42)
    r2 = compute_surrogate_gate_for_window(m_row, n_surrogates=10, seed=42)
    assert r1 == r2


def test_null_gate_report_aggregates_and_bounds_sample_size(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.array([[float((i + ch * 3) % 11) for i in range(100)] for ch in range(4)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [
        {"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "1"}
        for i in range(10)
    ]
    t_rows = [_make_t_row(f"r{i}", "sub-001") for i in range(10)]

    report = build_null_gate_report(t_rows, m_rows, n_surrogates=5, seed=0, sample_size=3)
    assert report["real_nulls_performed"] is True
    assert report["n_windows_gated"] == 3  # bounded by sample_size
    assert report["n_windows_total_candidates"] == 10
    assert report["status"] == "real_nulls_performed"


def test_null_gate_report_no_sampling_when_sample_size_none(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    signal = np.array([[float((i + ch * 3) % 11) for i in range(100)] for ch in range(4)])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [{"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "1"} for i in range(5)]
    t_rows = [_make_t_row(f"r{i}", "sub-001") for i in range(5)]
    report = build_null_gate_report(t_rows, m_rows, n_surrogates=3, sample_size=None)
    assert report["n_windows_gated"] == 5


# ---------------------------------------------------------------------------
# build_group_significance_report
# ---------------------------------------------------------------------------

def test_group_significance_not_applicable_when_group_col_missing():
    t_rows = [_make_t_row("r1", "sub-001")]
    m_rows = [{"row_id": "r1"}]  # no state_label
    report = build_group_significance_report(t_rows, m_rows)
    assert report["status"] == "not_applicable"


def test_group_significance_not_applicable_with_more_than_two_groups():
    t_rows = [_make_t_row(f"r{i}", f"sub-{i}") for i in range(3)]
    m_rows = [{"row_id": f"r{i}", "state_label": g} for i, g in enumerate(["a", "b", "c"])]
    report = build_group_significance_report(t_rows, m_rows)
    assert report["status"] == "not_applicable"
    assert "2 distinct" not in report["reason"] or "3 distinct" in report["reason"]


def test_group_significance_computes_real_permutation_results():
    rng = np.random.default_rng(0)
    t_rows = []
    m_rows = []
    for i in range(20):
        group = "expert" if i < 10 else "novice"
        q_abs = rng.normal(0.1, 0.02) if group == "expert" else rng.normal(0.3, 0.02)
        rid = f"r{i}"
        t_rows.append(_make_t_row(rid, f"sub-{i}", q_abs=q_abs))
        m_rows.append({"row_id": rid, "state_label": group})

    report = build_group_significance_report(t_rows, m_rows, n_permutations=500, seed=0)
    assert report["status"] == "computed"
    assert set(report["groups"]) == {"expert", "novice"}
    q_abs_result = report["metrics"]["q_abs"]
    assert "window_pooled" in q_abs_result and "subject_blocked" in q_abs_result
    # real, large separation (0.1 vs 0.3) with tight sd -- must be significant
    assert q_abs_result["window_pooled"]["p_value"] < 0.05
    assert q_abs_result["subject_blocked"]["p_value"] < 0.05


def test_group_significance_deterministic():
    rng = np.random.default_rng(1)
    t_rows, m_rows = [], []
    for i in range(10):
        group = "a" if i < 5 else "b"
        rid = f"r{i}"
        t_rows.append(_make_t_row(rid, f"sub-{i}", q_abs=rng.normal(0, 1)))
        m_rows.append({"row_id": rid, "state_label": group})
    r1 = build_group_significance_report(t_rows, m_rows, n_permutations=200, seed=5)
    r2 = build_group_significance_report(t_rows, m_rows, n_permutations=200, seed=5)
    assert r1 == r2
