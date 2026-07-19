from __future__ import annotations

import argparse
import sys

from sciencer_d.btc_icft.level_t import ds001787_real_topology as topo


def _mock_m_rows() -> list[dict]:
    return [
        {"row_id":"sub-001_ses-01_norun_fixed_win-0_aaaa","subject_id":"sub-001","session_id":"ses-01","run_id":"","window_id":"win-0","task_label":"meditation","source_file":"mock/a.bdf","window_start_s":"0","window_end_s":"10","artifact_score":"0.1"},
        {"row_id":"sub-013_ses-01_norun_fixed_win-0_bbbb","subject_id":"sub-013","session_id":"ses-01","run_id":"","window_id":"win-0","task_label":"meditation","source_file":"mock/b.bdf","window_start_s":"0","window_end_s":"10","artifact_score":"0.2"},
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--m-windows", default="outputs/btc_icft/ds001787/m_real")
    p.add_argument("--out", default="outputs/btc_icft/ds001787/t_real")
    p.add_argument("--mock-fixture", action="store_true")
    p.add_argument("--real", action="store_true")
    p.add_argument("--compute-nulls", action="store_true", help="Run the (compute-heavy) real surrogate null gate; off by default.")
    p.add_argument("--n-surrogates", type=int, default=50, help="Surrogates per window for the null gate (only used with --compute-nulls).")
    p.add_argument("--gate-sample-size", type=int, default=20, help="Bound the number of windows the null gate runs on; 0 means gate all windows.")
    p.add_argument("--n-permutations", type=int, default=2000, help="Permutations for the group-significance report.")
    p.add_argument("--seed", type=int, default=0)
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
        dataset_id="ds001787", n_rows=len(rows), n_subjects=len({r.subject_id for r in rows}), n_windows=len(rows),
        topology_quality_report=q, null_placeholder_report=n, artifact_alignment_report=ar, omega_event=omega,
        safe_claim="Local DS001787-style EEG windows were mapped into operational Level T topology telemetry candidates for future M+T residual testing.",
        forbidden_claims=["No topology proof.","No consciousness proof.","No self or soul claim.","No liberation or enlightenment claim.","No afterlife claim.","No ontology proof.","No Q/self, Q/soul, Q_abs/suffering, or f_dress/karma equivalence."],
        warnings=[],
    )
    group_significance_report = topo.build_group_significance_report(
        rows, m_rows, n_permutations=a.n_permutations, seed=a.seed
    )
    null_gate_report = None
    if a.compute_nulls:
        null_gate_report = topo.build_null_gate_report(
            rows, m_rows, n_surrogates=a.n_surrogates, seed=a.seed,
            sample_size=(a.gate_sample_size if a.gate_sample_size > 0 else None),
        )
    paths = topo.write_level_t_topology_outputs(
        res, a.out, null_gate_report=null_gate_report, group_significance_report=group_significance_report
    )
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
