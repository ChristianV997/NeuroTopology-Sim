"""Tests for base_real_topology.py's Phase 6 addition: build_ml_decoding_report
-- a complementary validity check to build_group_significance_report, testing
whether a COMBINATION of real topology features decodes state_label above
chance with a proper permutation-test null.
"""
from __future__ import annotations

import numpy as np

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyRow,
    build_ml_decoding_report,
)


def _make_t_row(row_id, subject_id, q_net, q_abs, f_dress=0.05, defect_density=0.01, topology_quality=1.0):
    return LevelTRealTopologyRow(
        row_id=row_id, subject_id=subject_id, session_id=None, run_id=None, window_id="win-0",
        task_label="x", q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
        n_triangles=10, n_valid_triangles=10, topology_quality=topology_quality, null_method="real_none",
        null_seed=0, source_file="a", window_start_s=0.0, window_end_s=1.0, warnings=[],
    )


def _m_row(row_id, subject_id, state_label):
    return {"row_id": row_id, "subject_id": subject_id, "state_label": state_label}


def test_not_applicable_when_group_col_missing():
    rows = [_make_t_row("r1", "s1", 0.1, 0.2), _make_t_row("r2", "s2", 0.3, 0.4)]
    m_rows = [{"row_id": "r1", "subject_id": "s1"}, {"row_id": "r2", "subject_id": "s2"}]
    report = build_ml_decoding_report(rows, m_rows)
    assert report["status"] == "not_applicable"


def test_not_applicable_with_more_than_two_groups():
    rng = np.random.default_rng(0)
    rows, m_rows = [], []
    for i in range(15):
        rows.append(_make_t_row(f"r{i}", f"s{i}", float(rng.standard_normal()), float(rng.standard_normal())))
        m_rows.append(_m_row(f"r{i}", f"s{i}", ["a", "b", "c"][i % 3]))
    report = build_ml_decoding_report(rows, m_rows)
    assert report["status"] == "not_applicable"


def test_detects_genuine_class_separation_in_topology_features():
    """Construct two groups with a real difference in q_net/q_abs -- the
    decoder must find this above chance with a significant p-value."""
    rng = np.random.default_rng(1)
    rows, m_rows = [], []
    for i in range(25):
        q_net = float(rng.normal(0, 0.3))
        q_abs = float(rng.normal(0, 0.3))
        rows.append(_make_t_row(f"a{i}", f"s{i}", q_net, q_abs))
        m_rows.append(_m_row(f"a{i}", f"s{i}", "state_a"))
    for i in range(25):
        q_net = float(rng.normal(3.0, 0.3))
        q_abs = float(rng.normal(3.0, 0.3))
        rows.append(_make_t_row(f"b{i}", f"t{i}", q_net, q_abs))
        m_rows.append(_m_row(f"b{i}", f"t{i}", "state_b"))

    report = build_ml_decoding_report(rows, m_rows, n_permutations=200, cv_folds=5, seed=0)
    assert report["status"] == "computed"
    assert report["accuracy"] > 0.8
    assert report["p_value"] < 0.05
    assert report["group_col"] == "state_label"


def test_no_false_positive_on_indistinguishable_groups():
    rng = np.random.default_rng(2)
    rows, m_rows = [], []
    for i in range(25):
        rows.append(_make_t_row(f"a{i}", f"s{i}", float(rng.standard_normal()), float(rng.standard_normal())))
        m_rows.append(_m_row(f"a{i}", f"s{i}", "state_a"))
    for i in range(25):
        rows.append(_make_t_row(f"b{i}", f"t{i}", float(rng.standard_normal()), float(rng.standard_normal())))
        m_rows.append(_m_row(f"b{i}", f"t{i}", "state_b"))

    report = build_ml_decoding_report(rows, m_rows, n_permutations=200, cv_folds=5, seed=0)
    assert report["status"] == "computed"
    assert report["p_value"] > 0.05


def test_extra_feature_reports_widen_the_feature_set():
    rng = np.random.default_rng(3)
    rows, m_rows = [], []
    for i in range(15):
        rows.append(_make_t_row(f"a{i}", f"s{i}", float(rng.standard_normal()), float(rng.standard_normal())))
        m_rows.append(_m_row(f"a{i}", f"s{i}", "state_a"))
    for i in range(15):
        rows.append(_make_t_row(f"b{i}", f"t{i}", float(rng.standard_normal()), float(rng.standard_normal())))
        m_rows.append(_m_row(f"b{i}", f"t{i}", "state_b"))

    extra_connectivity_results = [
        {"row_id": r.row_id, "status": "computed", "mean_plv": float(rng.standard_normal())} for r in rows
    ]

    report = build_ml_decoding_report(
        rows, m_rows, n_permutations=50, cv_folds=5, seed=0,
        extra_feature_reports=[extra_connectivity_results],
    )
    assert report["status"] == "computed"
    assert "mean_plv" in report["feature_names"]
