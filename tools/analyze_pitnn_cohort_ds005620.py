#!/usr/bin/env python3
"""Cohort statistics for the ds005620 PITNN + topology streaming run.

Consumes the per-subject records written by
`tools/stream_pitnn_cohort_ds005620.py` and produces the cohort-level inference
the earlier `scripts/run_cohort_eeg_topology.py` run could not: that run found a
single paired subject, so every Wilcoxon came back
`insufficient_paired_subjects`.

Statistics reuse `analysis/permutation.py` rather than re-deriving tests here:

  * `subject_blocked_permutation_test` aggregates each subject's windows to one
    value per (subject, condition) BEFORE permuting, so repeated windows within a
    subject cannot inflate significance. It auto-detects the within-subject design
    here and runs a paired sign-flip test reporting Cohen's dz.
  * `mixedlm_group_effect` fits a random-intercept model over the window-level
    rows as a second, distributional view of the same contrast.
  * A paired Wilcoxon over subject means is reported alongside, matching the
    metric the prior cohort artifact reported.

The PITNN side is summarised descriptively: `run_empirical_falsification` reserves
PASS strictly for Bayes factor K > 100, so the cohort's verdict distribution and
K range are reported as-is with no reinterpretation.
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

_METRICS = ("integrated_landscape_area", "beta1", "mean_plv")
_CONDITIONS = ("awake", "sedated")


def load_records(subjects_dir: Path) -> list[dict[str, Any]]:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(subjects_dir.glob("sub-*.json"))]
    if not records:
        raise FileNotFoundError(f"no subject records under {subjects_dir}")
    return records


def window_frame(records: list[dict[str, Any]]):
    """Long-format window-level table: one row per (subject, condition, window)."""
    import pandas as pd

    rows = []
    for record in records:
        for condition in _CONDITIONS:
            for window in record["topology_windows"][condition]:
                rows.append(
                    {
                        "subject": record["subject"],
                        "condition": condition,
                        "window": window["window"],
                        "integrated_landscape_area": window["integrated_landscape_area"],
                        "beta1": float(window["beta1"]),
                        "mean_plv": window["mean_plv"],
                    }
                )
    return pd.DataFrame(rows)


def paired_wilcoxon(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Paired Wilcoxon over per-subject condition means (awake - sedated)."""
    from scipy.stats import wilcoxon

    pairs = [
        (r["topology"]["awake"][key], r["topology"]["sedated"][key])
        for r in records
        if r["topology"]["awake"].get(key) is not None and r["topology"]["sedated"].get(key) is not None
    ]
    if len(pairs) < 2:
        return {"n_pairs": len(pairs), "statistic": None, "p_value": None, "status": "insufficient_paired_subjects"}
    awake, sedated = np.asarray(pairs, float).T
    if np.allclose(awake, sedated):
        return {"n_pairs": len(pairs), "statistic": 0.0, "p_value": 1.0, "status": "all_paired_differences_zero"}
    test = wilcoxon(awake, sedated, zero_method="wilcox", alternative="two-sided", method="auto")
    return {
        "n_pairs": len(pairs),
        "statistic": float(test.statistic),
        "p_value": float(test.pvalue),
        "median_awake": float(np.median(awake)),
        "median_sedated": float(np.median(sedated)),
        "status": "computed",
    }


def analyze(records: list[dict[str, Any]], n_permutations: int, seed: int) -> dict[str, Any]:
    from analysis.permutation import mixedlm_group_effect, subject_blocked_permutation_test

    frame = window_frame(records)
    per_metric: dict[str, Any] = {}

    for metric in _METRICS:
        permutation = subject_blocked_permutation_test(
            frame,
            value_col=metric,
            group_col="condition",
            subject_col="subject",
            n_permutations=n_permutations,
            seed=seed,
        )
        try:
            mixed = mixedlm_group_effect(
                frame, value_col=metric, group_col="condition", subject_col="subject"
            ).to_dict()
        except Exception as exc:  # a non-converging model must not void the permutation result
            mixed = {"error": str(exc)}
        per_metric[metric] = {"subject_blocked_permutation": permutation.to_dict(), "mixedlm": mixed}

    summary_key = {
        "integrated_landscape_area": "mean_landscape_area",
        "beta1": "mean_beta1",
        "mean_plv": "mean_plv",
    }
    for metric in _METRICS:
        per_metric[metric]["paired_wilcoxon_subject_means"] = paired_wilcoxon(records, summary_key[metric])

    bayes = np.asarray([r["pitnn"]["bayes_factor"] for r in records], float)
    verdicts: dict[str, int] = {}
    for record in records:
        verdicts[record["pitnn"]["verdict"]] = verdicts.get(record["pitnn"]["verdict"], 0) + 1

    # PITNN's own per-condition topology summary, contrasted the same paired way.
    pitnn_beta = [(r["pitnn"]["awake"]["mean_beta_1"], r["pitnn"]["sedated"]["mean_beta_1"]) for r in records]
    pitnn_beta_arr = np.asarray(pitnn_beta, float)

    return {
        "schema": "NeuroTopologySim.DS005620PITNNCohort.v1",
        "dataset_id": "ds005620",
        "n_paired_subjects": len(records),
        "subjects": [r["subject"] for r in records],
        "acquisition": {
            "sample_rate_hz": records[0]["sample_rate_hz"],
            "n_channels": records[0]["n_channels"],
            "n_samples_per_condition": records[0]["n_samples_per_condition"],
            "band_hz": records[0]["band_hz"],
            "windows_per_condition": len(records[0]["topology_windows"]["awake"]),
        },
        "topology_tests": per_metric,
        "pitnn": {
            "verdict_counts": verdicts,
            "bayes_factor_min": float(bayes.min()),
            "bayes_factor_max": float(bayes.max()),
            "bayes_factor_median": float(np.median(bayes)),
            "pass_threshold": 100.0,
            "n_above_pass_threshold": int(np.count_nonzero(bayes > 100.0)),
            "mean_beta_1_awake": float(pitnn_beta_arr[:, 0].mean()),
            "mean_beta_1_sedated": float(pitnn_beta_arr[:, 1].mean()),
            "paired_wilcoxon_mean_beta_1": _wilcoxon_pairs(pitnn_beta_arr),
        },
        "scientific_note": (
            "Persistent-H1 landscape area and PLV are descriptive EEG network measures. "
            "A paired difference between an eyes-closed awake recording and a propofol "
            "sedation recording does not identify a mechanism and is not a measure of "
            "consciousness. PITNN PASS is reserved strictly for Bayes factor K > 100."
        ),
    }


def _wilcoxon_pairs(arr: np.ndarray) -> dict[str, Any]:
    from scipy.stats import wilcoxon

    if arr.shape[0] < 2 or np.allclose(arr[:, 0], arr[:, 1]):
        return {"n_pairs": int(arr.shape[0]), "statistic": None, "p_value": None, "status": "not_computable"}
    test = wilcoxon(arr[:, 0], arr[:, 1], zero_method="wilcox", alternative="two-sided", method="auto")
    return {
        "n_pairs": int(arr.shape[0]),
        "statistic": float(test.statistic),
        "p_value": float(test.pvalue),
        "status": "computed",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cohort-dir", type=Path, default=_REPO_ROOT / "outputs" / "pitnn_cohort" / "ds005620")
    p.add_argument("--n-permutations", type=int, default=10000)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)

    records = load_records(args.cohort_dir / "subjects")
    summary = analyze(records, args.n_permutations, args.seed)

    (args.cohort_dir / "cohort_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Per-subject CSV so the cohort table is inspectable without parsing JSON.
    import csv

    with (args.cohort_dir / "cohort_per_subject.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "subject", "bayes_factor", "verdict",
                "awake_landscape_area", "sedated_landscape_area",
                "awake_beta1", "sedated_beta1",
                "awake_mean_plv", "sedated_mean_plv",
            ]
        )
        for r in records:
            writer.writerow(
                [
                    r["subject"], r["pitnn"]["bayes_factor"], r["pitnn"]["verdict"],
                    r["topology"]["awake"]["mean_landscape_area"], r["topology"]["sedated"]["mean_landscape_area"],
                    r["topology"]["awake"]["mean_beta1"], r["topology"]["sedated"]["mean_beta1"],
                    r["topology"]["awake"]["mean_plv"], r["topology"]["sedated"]["mean_plv"],
                ]
            )

    from runs.run_record import RunRecordV1, build_run_id

    inputs = {
        "dataset_id": "ds005620",
        "n_paired_subjects": summary["n_paired_subjects"],
        "band_hz": summary["acquisition"]["band_hz"],
        "sample_rate_hz": summary["acquisition"]["sample_rate_hz"],
        "n_permutations": args.n_permutations,
        "seed": args.seed,
    }
    headline = summary["topology_tests"]["integrated_landscape_area"]["subject_blocked_permutation"]
    run_id = build_run_id(
        "ds005620_pitnn_cohort", "NeuroTopology-Sim", "working-tree",
        ["tools/analyze_pitnn_cohort_ds005620.py"], inputs,
        {"p_value": headline["p_value"], "observed_stat": headline["observed_stat"]},
    )
    record = RunRecordV1.make(
        run_id, "eeg_cohort",
        claim_type="C", layer="biophysical", data_mode="empirical_local",
        dataset_id="ds005620",
        verdict=summary["pitnn"]["verdict_counts"],
        metrics=summary,
        artifacts={
            "cohort_summary": "cohort_summary.json",
            "per_subject_csv": "cohort_per_subject.csv",
            "pairing": "pairing.json",
        },
        source="tools/analyze_pitnn_cohort_ds005620.py",
    )
    record.input = inputs
    record.notes = summary["scientific_note"]
    record.write_json(args.cohort_dir / "RunRecord.json")

    print(json.dumps({
        "n_paired_subjects": summary["n_paired_subjects"],
        "landscape_area": {
            "p_permutation": headline["p_value"],
            "dz": headline["effect_size_d"],
            "p_wilcoxon": summary["topology_tests"]["integrated_landscape_area"]["paired_wilcoxon_subject_means"]["p_value"],
        },
        "pitnn_verdicts": summary["pitnn"]["verdict_counts"],
        "run_id": run_id,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
