"""Additional edge-case and scientific separation tests for cohort statistics."""
from __future__ import annotations

import math
import pytest

from analysis.cohort_statistics import (
    HypothesisAlternative,
    MultiplicityMethod,
    ProvenanceStatus,
    calculate_paired_cohort_report,
    compute_inferential_stats,
    compute_paired_effect_size_dz,
)


def test_scientific_metric_separation():
    """Verify graph beta-1, spatial winding, topological charge, and chirality are tracked distinctly."""
    cohort = {
        "sub-01": {
            "drug": {
                "graph_beta_1": 15.0,
                "spatial_winding": 1.2,
                "topological_charge": 0.8,
                "scalar_chirality": 0.05,
            },
            "placebo": {
                "graph_beta_1": 10.0,
                "spatial_winding": 0.4,
                "topological_charge": 0.2,
                "scalar_chirality": -0.01,
            },
        },
        "sub-02": {
            "drug": {
                "graph_beta_1": 14.0,
                "spatial_winding": 1.1,
                "topological_charge": 0.7,
                "scalar_chirality": 0.04,
            },
            "placebo": {
                "graph_beta_1": 9.0,
                "spatial_winding": 0.5,
                "topological_charge": 0.3,
                "scalar_chirality": 0.00,
            },
        },
        "sub-03": {
            "drug": {
                "graph_beta_1": 16.0,
                "spatial_winding": 1.3,
                "topological_charge": 0.9,
                "scalar_chirality": 0.06,
            },
            "placebo": {
                "graph_beta_1": 11.0,
                "spatial_winding": 0.3,
                "topological_charge": 0.1,
                "scalar_chirality": -0.02,
            },
        },
    }

    report = calculate_paired_cohort_report(
        cohort,
        condition_a_name="drug",
        condition_b_name="placebo",
        multiplicity_method=MultiplicityMethod.HOLM,
    )

    expected_metrics = {
        "graph_beta_1",
        "spatial_winding",
        "topological_charge",
        "scalar_chirality",
    }
    assert set(report.metrics.keys()) == expected_metrics

    # Graph beta-1: difference is exactly +5.0 across all 3 subjects
    beta1 = report.metrics["graph_beta_1"]
    assert beta1.difference_stats.mean == pytest.approx(5.0)
    assert beta1.valid_pairs_count == 3
    assert beta1.excluded_pairs_count == 0

    # Spatial winding: difference is ~0.8
    winding = report.metrics["spatial_winding"]
    assert winding.difference_stats.mean == pytest.approx(0.8)

    # Topological charge: difference is ~0.6
    charge = report.metrics["topological_charge"]
    assert charge.difference_stats.mean == pytest.approx(0.6)

    # Scalar chirality: difference is ~0.06
    chirality = report.metrics["scalar_chirality"]
    assert chirality.difference_stats.mean == pytest.approx(0.06)


def test_hypothesis_alternatives():
    diffs = [1.0, 1.5, 2.0, 1.2, 0.8]

    res_two_sided = compute_inferential_stats(diffs, alternative=HypothesisAlternative.TWO_SIDED)
    res_greater = compute_inferential_stats(diffs, alternative=HypothesisAlternative.GREATER)
    res_less = compute_inferential_stats(diffs, alternative=HypothesisAlternative.LESS)

    assert res_two_sided.p_value is not None
    assert res_greater.p_value is not None
    assert res_less.p_value is not None

    # Since all differences are positive, 'greater' should have a smaller p-value than 'less'
    assert res_greater.p_value < res_less.p_value


def test_inf_and_nan_in_difference():
    # Cohen's d_z with Inf or NaN should handle gracefully without crashing
    assert compute_paired_effect_size_dz([float("inf"), 1.0, 2.0]) is not None
    assert compute_paired_effect_size_dz([float("-inf"), float("nan")]) is None
