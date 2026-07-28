"""Tests for the ds005917 paired drug-vs-placebo statistics (not a between-
group ANOVA -- every subject contributes one value per condition)."""
from __future__ import annotations

import numpy as np

from tools.analyze_ds005917_paired_stats import analyze, paired_effect_size


def test_paired_effect_size_zero_when_no_mean_difference():
    diff = np.array([1.0, -1.0, 2.0, -2.0])
    d = paired_effect_size(diff)
    assert abs(d) < 1e-9


def test_paired_effect_size_positive_for_consistent_positive_difference():
    diff = np.array([1.0, 1.2, 0.9, 1.1])
    d = paired_effect_size(diff)
    assert d > 3.0  # small variance, clear positive shift -> large d_z


def _fake_subject(drug_val: float, placebo_val: float, error: str = "") -> dict:
    def rec(v):
        return {
            "n_regions": 100, "n_timepoints": 240, "betti0": 1, "betti1": v,
            "total_persistence_h1": v, "modularity": v, "global_efficiency": v,
            "mean_degree": v, "small_worldness": v, "error": error,
        }
    return {"drug": rec(drug_val), "placebo": rec(placebo_val)}


def test_analyze_excludes_subjects_with_errors_in_either_arm():
    cohort = {
        "sub-A": _fake_subject(50, 40),
        "sub-B": _fake_subject(52, 41),
        "sub-C": {**_fake_subject(0, 41), "drug": {**_fake_subject(0, 41)["drug"], "error": "download failed"}},
    }
    result = analyze(cohort)
    assert result["n_subjects_clean"] == 2
    assert result["n_subjects_total"] == 3


def test_analyze_reports_paired_not_independent_test():
    cohort = {f"sub-{i}": _fake_subject(50 + i, 40 + i) for i in range(10)}
    result = analyze(cohort)
    betti1 = result["metrics"]["betti1"]
    # Constant +10 difference across all subjects -> paired t-test must find
    # this trivially significant (perfectly consistent within-subject shift).
    assert betti1["paired_t_p"] < 0.01
    assert betti1["mean_diff"] == 10.0
