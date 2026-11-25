"""Regression coverage for fail-closed real-mode report eligibility."""
from __future__ import annotations

from sciencer_d.btc_icft.level_t.base_real_topology import (
    LevelTRealTopologyRow,
    build_ml_decoding_report,
)


def _missing_signal_row(index: int, state: str) -> LevelTRealTopologyRow:
    return LevelTRealTopologyRow(
        row_id=f"row-{index}",
        subject_id=f"sub-{index}",
        session_id=None,
        run_id=None,
        window_id="w0",
        task_label=state,
        q_net=0.0,
        q_abs=0.0,
        f_dress=0.0,
        defect_density=0.0,
        n_triangles=0,
        n_valid_triangles=0,
        topology_quality=0.0,
        null_method="real_none",
        null_seed=0,
        source_file="missing.edf",
        window_start_s=0.0,
        window_end_s=1.0,
        warnings=["source file not found: 'missing.edf'; topology skipped"],
    )


def test_missing_real_signal_rows_do_not_launch_ml_permutation_test():
    rows = [_missing_signal_row(i, "a" if i < 5 else "b") for i in range(10)]
    m_rows = [
        {"row_id": row.row_id, "state_label": row.task_label}
        for row in rows
    ]

    report = build_ml_decoding_report(rows, m_rows, n_permutations=1000, seed=5)

    assert report["status"] == "not_applicable"
    assert report["n_rows_total"] == 10
    assert report["n_rows_excluded"] == 10
    assert "signal-derived" in report["reason"]
