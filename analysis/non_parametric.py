"""Centralized non-parametric paired statistical testing with degenerate data guards."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence
import numpy as np
from scipy import stats


def wilcoxon_paired_test(
    sample_a: Sequence[float] | np.ndarray,
    sample_b: Sequence[float] | np.ndarray,
    alternative: str = "two-sided",
) -> Dict[str, Any]:
    """Perform a paired Wilcoxon signed-rank test with strict degenerate data guards.

    Guards:
    - Unequal sample lengths.
    - Non-finite values (NaN, Inf).
    - Insufficient paired sample size (N < 2).
    - Degenerate zero-variance differences (all pairs identical, d_i == 0).

    Args:
        sample_a: First paired condition array.
        sample_b: Second paired condition array.
        alternative: "two-sided", "greater", or "less".

    Returns:
        Dictionary with p_value, test_statistic, n_pairs, verdict, and valid boolean flag.
    """
    a = np.asarray(sample_a, dtype=np.float64)
    b = np.asarray(sample_b, dtype=np.float64)

    if a.shape != b.shape:
        raise ValueError(f"Paired samples must have identical shape; got {a.shape} vs {b.shape}")

    a_flat = a.ravel()
    b_flat = b.ravel()
    n = len(a_flat)

    if not np.all(np.isfinite(a_flat)) or not np.all(np.isfinite(b_flat)):
        return {
            "valid": False,
            "status": "non_finite_values_detected",
            "p_value": None,
            "statistic": None,
            "n_pairs": n,
            "verdict": "INVALID",
            "message": "Samples contain non-finite (NaN or Inf) values.",
        }

    if n < 2:
        return {
            "valid": False,
            "status": "insufficient_paired_subjects",
            "p_value": None,
            "statistic": None,
            "n_pairs": n,
            "verdict": "INSUFFICIENT_DATA",
            "message": f"Sample size N={n} is below minimum threshold (N >= 2) for paired inference.",
        }

    diffs = a_flat - b_flat
    nonzero_diffs = diffs[diffs != 0.0]

    if len(nonzero_diffs) == 0:
        return {
            "valid": False,
            "status": "zero_variance_differences",
            "p_value": None,
            "statistic": None,
            "n_pairs": n,
            "verdict": "IDENTICAL_PAIRS",
            "message": "All paired differences are exactly zero; test statistic is undefined.",
        }

    try:
        res = stats.wilcoxon(a_flat, b_flat, alternative=alternative)
        p_val = float(res.pvalue)
        stat = float(res.statistic)

        verdict = "SIGNIFICANT" if p_val < 0.05 else "NOT_SIGNIFICANT"
        return {
            "valid": True,
            "status": "success",
            "p_value": p_val,
            "statistic": stat,
            "n_pairs": n,
            "n_nonzero_pairs": len(nonzero_diffs),
            "mean_difference": float(np.mean(diffs)),
            "median_difference": float(np.median(diffs)),
            "alternative": alternative,
            "verdict": verdict,
            "message": f"Wilcoxon signed-rank test completed (p={p_val:.6g}, W={stat:.6g}).",
        }
    except Exception as exc:
        return {
            "valid": False,
            "status": "calculation_error",
            "p_value": None,
            "statistic": None,
            "n_pairs": n,
            "verdict": "ERROR",
            "message": f"Underlying stats calculation failed: {exc}",
        }
