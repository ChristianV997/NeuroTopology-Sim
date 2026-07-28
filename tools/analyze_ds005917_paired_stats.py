#!/usr/bin/env python3
"""Paired drug-vs-placebo statistics for ds005917 (NIMH Ketamine Mechanism
of Action Study, MDD group, within-subject crossover).

Not a between-group ANOVA (that's what `dual_engine.fmri_tda_pipeline
.group_compare` does, correct for ds006644's between-subject design). Here
every subject contributes ONE value per condition (drug ses-d2, placebo
ses-p2), so the correct test is a PAIRED test on the per-subject
(drug - placebo) difference: paired t-test (parametric) and Wilcoxon
signed-rank (nonparametric, robust to the topology metrics' likely-skewed
distributions), plus the paired effect size d_z = mean(diff) / std(diff),
not the independent-samples Cohen's d in `analysis/stats.py` (which would
be the wrong formula for paired data).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_METRICS = ("betti1", "total_persistence_h1", "modularity", "global_efficiency", "mean_degree", "small_worldness")


def paired_effect_size(diff: np.ndarray) -> float:
    """d_z for a paired design: mean difference / SD of the differences."""
    sd = diff.std(ddof=1)
    return float(diff.mean() / sd) if sd > 0 else float("nan")


def analyze(cohort_result: dict) -> dict:
    clean = {
        sub: v for sub, v in cohort_result.items()
        if not v["drug"]["error"] and not v["placebo"]["error"]
    }
    n = len(clean)
    metrics_out = {}
    for m in _METRICS:
        drug = np.array([v["drug"][m] for v in clean.values()], dtype=float)
        placebo = np.array([v["placebo"][m] for v in clean.values()], dtype=float)
        diff = drug - placebo
        t_stat, t_p = stats.ttest_rel(drug, placebo)
        try:
            w_stat, w_p = stats.wilcoxon(diff)
        except ValueError:
            w_stat, w_p = float("nan"), float("nan")
        metrics_out[m] = {
            "n_subjects": n,
            "drug_mean": float(drug.mean()), "placebo_mean": float(placebo.mean()),
            "mean_diff": float(diff.mean()),
            "paired_t_p": float(t_p), "paired_t_stat": float(t_stat),
            "wilcoxon_p": float(w_p),
            "effect_size_dz": paired_effect_size(diff),
        }
    return {
        "dataset": "ds005917", "group": "MDD", "contrast": "drug(ses-d2)_vs_placebo(ses-p2)",
        "n_subjects_clean": n, "n_subjects_total": len(cohort_result),
        "metrics": metrics_out,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort-result", default="outputs/dual_engine/ds005917/cohort_result.json")
    p.add_argument("--output", default="outputs/dual_engine/ds005917/paired_stats.json")
    a = p.parse_args()

    cohort = json.loads(Path(a.cohort_result).read_text())
    result = analyze(cohort)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(result, indent=2))
    print(f"wrote {a.output}: n={result['n_subjects_clean']} clean subjects")
    for m, r in result["metrics"].items():
        print(f"  {m}: paired_t_p={r['paired_t_p']:.4f} wilcoxon_p={r['wilcoxon_p']:.4f} d_z={r['effect_size_dz']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
