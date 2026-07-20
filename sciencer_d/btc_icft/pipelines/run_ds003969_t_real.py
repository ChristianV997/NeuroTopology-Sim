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
    p.add_argument("--compute-nulls", action="store_true", help="Run the (compute-heavy) real surrogate null gate; off by default.")
    p.add_argument("--n-surrogates", type=int, default=50, help="Surrogates per window for the null gate (only used with --compute-nulls).")
    p.add_argument("--gate-sample-size", type=int, default=20, help="Bound the number of windows the null gate runs on; 0 means gate all windows.")
    p.add_argument("--n-permutations", type=int, default=2000, help="Permutations for the group-significance report.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--phase-band", default="alpha", help="EEG band for the real band-specific Hilbert-phase topology report (delta/theta/alpha/beta/gamma_low).")
    p.add_argument("--phase-topology-sample-size", type=int, default=0, help="Bound the number of windows the phase-based topology report runs on; 0 means all windows (cheap, unlike the null gate).")
    p.add_argument("--connectivity-methods", nargs="*", default=["plv", "pli", "wpli"], help="Connectivity methods to compute (plv/pli/wpli).")
    p.add_argument("--connectivity-sample-size", type=int, default=0, help="Bound the number of windows the connectivity report runs on; 0 means all windows.")
    p.add_argument("--compute-granger", action="store_true", help="Also compute directed Granger causality (compute-heavy: O(channels^2) OLS-based tests per window); off by default.")
    p.add_argument("--granger-maxlag", type=int, default=5)
    p.add_argument("--spatial-band", default="alpha", help="EEG band for the real montage-aware spatial winding-number topology report.")
    p.add_argument("--spatial-sample-size", type=int, default=20, help="Bound the number of windows the spatial topology report runs on (griddata interpolation is meaningfully more expensive than the other reports); 0 means all windows.")
    p.add_argument("--spatial-grid-size", type=int, default=24)
    p.add_argument("--spatial-n-time-samples", type=int, default=10)
    p.add_argument("--microstate-n-clusters", type=int, default=4)
    p.add_argument("--microstate-sample-size", type=int, default=5, help="Bound the number of distinct RECORDINGS (not windows) the microstate report fits; 0 means all recordings.")
    p.add_argument("--microstate-max-duration-s", type=float, default=120.0, help="Truncate each recording to this many seconds before fitting (bounds ModKMeans compute cost); 0 means use the full recording.")
    p.add_argument("--ml-decoding-n-permutations", type=int, default=1000, help="Permutations for the ML decoding report's permutation-test null.")
    p.add_argument("--ml-decoding-cv-folds", type=int, default=5)
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
    group_significance_report = topo.build_group_significance_report(
        rows, m_rows, n_permutations=a.n_permutations, seed=a.seed
    )
    null_gate_report = None
    if a.compute_nulls:
        null_gate_report = topo.build_null_gate_report(
            rows, m_rows, n_surrogates=a.n_surrogates, seed=a.seed,
            sample_size=(a.gate_sample_size if a.gate_sample_size > 0 else None),
        )
    phase_based_topology_report = topo.build_phase_based_topology_report(
        rows, m_rows, band=a.phase_band, seed=a.seed,
        sample_size=(a.phase_topology_sample_size if a.phase_topology_sample_size > 0 else None),
    )
    connectivity_report = topo.build_connectivity_report(
        rows, m_rows, methods=tuple(a.connectivity_methods), seed=a.seed,
        sample_size=(a.connectivity_sample_size if a.connectivity_sample_size > 0 else None),
        compute_granger=a.compute_granger, granger_maxlag=a.granger_maxlag,
    )
    spatial_topology_report = topo.build_spatial_topology_report(
        rows, m_rows, band=a.spatial_band, seed=a.seed,
        sample_size=(a.spatial_sample_size if a.spatial_sample_size > 0 else None),
        grid_size=a.spatial_grid_size, n_time_samples=a.spatial_n_time_samples,
    )
    microstate_report = topo.build_microstate_report(
        m_rows, seed=a.seed, n_clusters=a.microstate_n_clusters,
        sample_size=(a.microstate_sample_size if a.microstate_sample_size > 0 else None),
        max_duration_s=(a.microstate_max_duration_s if a.microstate_max_duration_s > 0 else None),
    )
    ml_decoding_report = topo.build_ml_decoding_report(
        rows, m_rows, n_permutations=a.ml_decoding_n_permutations, cv_folds=a.ml_decoding_cv_folds, seed=a.seed,
        extra_feature_reports=[connectivity_report.get("results", [])],
    )
    paths = topo.write_level_t_topology_outputs(
        res, a.out, null_gate_report=null_gate_report, group_significance_report=group_significance_report,
        phase_based_topology_report=phase_based_topology_report, connectivity_report=connectivity_report,
        spatial_topology_report=spatial_topology_report, microstate_report=microstate_report,
        ml_decoding_report=ml_decoding_report,
    )
    for k, v in paths.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
