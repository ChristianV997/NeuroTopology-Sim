from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.level_t import ds003969_real_topology as topo


def _mock_m_rows() -> list[dict]:
    return [
        {"row_id":"sub-001_nosess_norun_noacq_med1breath_win-0_aaaa","subject_id":"sub-001","session_id":"","run_id":"","window_id":"win-0","task_label":"med1breath","source_file":"mock/a.bdf","window_start_s":"0","window_end_s":"10","artifact_score":"0.1"},
        {"row_id":"sub-001_nosess_norun_noacq_think1_win-1_bbbb","subject_id":"sub-001","session_id":"","run_id":"","window_id":"win-1","task_label":"think1","source_file":"mock/a.bdf","window_start_s":"10","window_end_s":"20","artifact_score":"0.2"},
        {"row_id":"sub-002_nosess_norun_noacq_med2_win-0_cccc","subject_id":"sub-002","session_id":"","run_id":"","window_id":"win-0","task_label":"med2","source_file":"mock/b.bdf","window_start_s":"0","window_end_s":"10","artifact_score":"0.15"},
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--m-windows", default="outputs/btc_icft/ds003969/m_real")
    p.add_argument("--out", default="outputs/btc_icft/ds003969/t_real")
    p.add_argument("--mock-fixture", action="store_true")
    p.add_argument("--real", action="store_true")
    a = p.parse_args()

    if a.real and a.mock_fixture:
        print("--real and --mock-fixture are mutually exclusive.", file=sys.stderr)
        return 2
    if not a.real and not a.mock_fixture:
        print("One of --real or --mock-fixture is required.", file=sys.stderr)
        return 2

    if a.mock_fixture:
        try:
            m_rows = topo.load_level_m_window_features(a.m_windows)
        except (FileNotFoundError, ValueError):
            m_rows = _mock_m_rows()
    else:
        try:
            m_rows = topo.load_level_m_window_features(a.m_windows)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 2

    rows = topo.build_level_t_rows_from_m_windows(
        m_rows, mock_fixture=a.mock_fixture, real=a.real
    )
    topo.result_rows_cache = rows
    q = topo.build_topology_quality_report(rows)
    n = topo.build_null_placeholder_report(rows)
    ar = topo.build_artifact_alignment_report(rows, m_rows)
    omega = topo.build_level_t_omega_event(rows)
    res = topo.LevelTRealTopologyResult(
        dataset_id="ds003969", n_rows=len(rows), n_subjects=len({r.subject_id for r in rows}), n_windows=len(rows),
        topology_quality_report=q, null_placeholder_report=n, artifact_alignment_report=ar, omega_event=omega,
        safe_claim="Local DS003969-style EEG windows were mapped into operational Level T topology telemetry candidates for future M+T residual testing.",
        forbidden_claims=["No topology proof.","No consciousness proof.","No self or soul claim.","No liberation or enlightenment claim.","No afterlife claim.","No ontology proof.","No Q/self, Q/soul, Q_abs/suffering, or f_dress/karma equivalence."],
        warnings=[],
    )
    paths = topo.write_level_t_topology_outputs(res, a.out)
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
