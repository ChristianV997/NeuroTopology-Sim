#!/usr/bin/env python3
"""Surrogate-gate and permutation-test ds000245's global_efficiency headline.

Closes the deferred half of REPORT_gate_ds000245_ds005620.md. That report gated
ds005620's alpha-anteriorization finding (80/80 surrogate pass, permutation
p<=0.001) and deferred ds000245's global_efficiency (claimed eta^2=0.41,
CTL<ODN<ODP) because no raw BOLD or ROI timeseries survived a prior run to gate.

This script consumes the ROI timeseries `tools/fetch_ds000245.py` +
`dual_engine.fmri_tda_pipeline --save-timeseries` produced from a real re-fetch
and asks the same two questions that report asked for ds005620:

  Q1 (metric validity): is the real global_efficiency value, computed through the
     ENTIRE connectivity -> graph pipeline, more extreme than what the same
     pipeline produces on phase-randomized surrogates of the same ROI timeseries?
     Gates `validation.surrogate_testing.surrogate_test_topology_metric` per
     subject (network null, not a per-region confound check -- there is no
     spatial/channel confound analogous to EMG for a parcellated BOLD signal).

  Q2 (contrast reality): does the real CTL/ODN/ODP group difference in
     global_efficiency survive a label-shuffle permutation null on the
     eta-squared effect size, via the new `analysis.permutation.permutation_anova`
     (added alongside this script; ds000245 is a between-subjects design, so the
     existing two-group/paired functions in that module do not apply)?

No result here is assumed in advance; this reports whatever the gate finds.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _global_efficiency_from_roi_ts(ts: np.ndarray, *, connectivity_kind: str = "correlation") -> float:
    """`(n_regions, n_timepoints) -> global_efficiency`, the exact
    connectivity_matrix -> graph_metrics chain `run_subject` runs, so the gate's
    null distribution is over the SAME pipeline the real cohort_result.json used,
    not a simplified proxy.
    """
    from dual_engine.fmri_tda_pipeline import connectivity_matrix, graph_metrics

    conn = connectivity_matrix(ts.T, kind=connectivity_kind)  # (n_timepoints, n_regions) expected
    return float(graph_metrics(conn)["global_efficiency"])


def load_roi_timeseries(ts_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(ts_dir.glob("*_roi_timeseries.npz")):
        with np.load(path, allow_pickle=True) as npz:
            records.append(
                {
                    "subject_id": str(npz["subject_id"]),
                    "group": str(npz["group"]),
                    "timeseries": npz["timeseries"].astype(float),  # (n_timepoints, n_regions)
                    "path": str(path),
                }
            )
    if not records:
        raise FileNotFoundError(f"no *_roi_timeseries.npz files under {ts_dir}")
    return records


def gate_subject(record: dict[str, Any], n_surrogates: int, seed: int, n_jobs: int) -> dict[str, Any]:
    """Surrogate-gate one subject's real global_efficiency against phase-randomized nulls."""
    from validation.surrogate_testing import surrogate_test_topology_metric

    ts_regions_by_time = record["timeseries"]  # (T, R)
    ts_channels = ts_regions_by_time.T  # (R, T): surrogate_testing's (n_channels, n_timepoints) convention

    def metric_fn(arr: np.ndarray) -> float:
        return _global_efficiency_from_roi_ts(arr)  # arr is already (R, T), matching the helper's input

    result = surrogate_test_topology_metric(
        ts_channels,
        metric_fn,
        n_surrogates=n_surrogates,
        method="ft",
        two_sided=True,  # no prior directional hypothesis for this metric
        random_state=seed,
        n_jobs=n_jobs,
    )
    return {
        "subject_id": record["subject_id"],
        "group": record["group"],
        "real_value": result["real_value"],
        "surrogate_mean": result["surrogate_mean"],
        "surrogate_std": result["surrogate_std"],
        "z_score": result["z_score"],
        "p_value": result["p_value"],
        "n_surrogates": result["n_surrogates"],
        "passes_gate_p05": result["passes_gate_p05"],
    }


def run(ts_dir: Path, n_surrogates: int, n_permutations: int, seed: int, n_jobs: int, limit: int | None) -> dict[str, Any]:
    from analysis.permutation import permutation_anova

    records = load_roi_timeseries(ts_dir)
    if limit is not None:
        records = records[:limit]

    # Q2 first (cheap): real per-subject global_efficiency + group-label permutation ANOVA.
    real_values = np.array([_global_efficiency_from_roi_ts(r["timeseries"].T) for r in records])
    groups = np.array([r["group"] for r in records])
    group_means = {g: float(real_values[groups == g].mean()) for g in sorted(set(groups.tolist()))}
    anova = permutation_anova(real_values, groups, n_permutations=n_permutations, seed=seed)

    # Q1: surrogate-gate every subject's real value (expensive: n_surrogates full pipeline runs each).
    subject_gates = [gate_subject(r, n_surrogates, seed, n_jobs) for r in records]
    n_pass = sum(1 for g in subject_gates if g["passes_gate_p05"])

    return {
        "schema": "NeuroTopologySim.DS000245GlobalEfficiencyGate.v1",
        "dataset_id": "ds000245",
        "n_subjects": len(records),
        "group_n": {g: int(np.sum(groups == g)) for g in sorted(set(groups.tolist()))},
        "group_means_global_efficiency": group_means,
        "question_b_contrast_reality": {
            "method": "permutation_anova_label_shuffle",
            **anova.to_dict(),
        },
        "question_a_metric_validity": {
            "method": "surrogate_test_topology_metric_ft_two_sided",
            "n_subjects_gated": len(subject_gates),
            "n_pass_p05": n_pass,
            "fraction_pass": float(n_pass) / len(subject_gates) if subject_gates else None,
            "per_subject": subject_gates,
        },
        "scientific_note": (
            "global_efficiency is computed on a K=100 coordinate (non-anatomical) parcellation -- "
            "the original headline's own choice, not a Schaefer/anatomical atlas -- so a real "
            "spatial-normalization or anatomical claim is not being tested here, only whether the "
            "numeric group effect and its network structure are statistically real for THIS "
            "parcellation. group_means/eta_squared do not by themselves establish a clinical or "
            "anatomical Parkinson's mechanism."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ts-dir", type=Path, default=_REPO_ROOT / "outputs" / "ds000245_fmri_tda" / "roi_timeseries")
    parser.add_argument("--out", type=Path, default=_REPO_ROOT / "outputs" / "ds000245_fmri_tda" / "global_efficiency_gate.json")
    parser.add_argument("--n-surrogates", type=int, default=200)
    parser.add_argument("--n-permutations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="gate only the first N subjects (testing)")
    args = parser.parse_args()

    payload = run(args.ts_dir, args.n_surrogates, args.n_permutations, args.seed, args.n_jobs, args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(
        {
            "n_subjects": payload["n_subjects"],
            "group_means": payload["group_means_global_efficiency"],
            "eta_squared": payload["question_b_contrast_reality"]["observed_eta_squared"],
            "permutation_p": payload["question_b_contrast_reality"]["p_value"],
            "surrogate_gate_pass_fraction": payload["question_a_metric_validity"]["fraction_pass"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
