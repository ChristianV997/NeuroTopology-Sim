"""Calculation engine for paired-cohort descriptive and non-parametric statistics."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence
import numpy as np

from .models import (
    DescriptiveStats,
    ExclusionRecord,
    HypothesisAlternative,
    InferentialStats,
    MetricCohortStats,
    PairedDifferenceStats,
)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def calculate_descriptive_moments(values: Sequence[float]) -> DescriptiveStats:
    """Calculates n, mean, median, sample variance (ddof=1), and standard error."""
    arr = np.asarray(values, dtype=float)
    n = int(arr.size)
    if n == 0:
        return DescriptiveStats(n=0, mean=None, median=None, variance=None, standard_error=None)

    mean_val = float(np.mean(arr))
    median_val = float(np.median(arr))

    if n > 1:
        var_val = float(np.var(arr, ddof=1))
        se_val = float(np.std(arr, ddof=1) / math.sqrt(n))
    else:
        var_val = None
        se_val = None

    return DescriptiveStats(
        n=n,
        mean=mean_val,
        median=median_val,
        variance=var_val,
        standard_error=se_val,
    )


def calculate_paired_differences(
    cond_a: Sequence[float],
    cond_b: Sequence[float],
) -> PairedDifferenceStats:
    """Calculates paired differences (cond_b - cond_a), Cohen's d_z, and 95% CI."""
    a = np.asarray(cond_a, dtype=float)
    b = np.asarray(cond_b, dtype=float)
    if a.size != b.size:
        raise ValueError(f"Mismatched pair lengths: cond_a={a.size}, cond_b={b.size}")

    diffs = b - a
    n = int(diffs.size)
    if n == 0:
        return PairedDifferenceStats(
            values=[],
            mean=None,
            median=None,
            variance=None,
            standard_error=None,
            median_difference=None,
            cohens_d_z=None,
            ci_95=None,
        )

    mean_diff = float(np.mean(diffs))
    median_diff = float(np.median(diffs))

    if n > 1:
        var_diff = float(np.var(diffs, ddof=1))
        std_diff = float(np.std(diffs, ddof=1))
        se_diff = float(std_diff / math.sqrt(n))
        cohens_d = float(mean_diff / std_diff) if std_diff > 0 else (0.0 if mean_diff == 0 else None)

        # 95% Confidence interval for mean difference
        try:
            from scipy import stats
            t_crit = float(stats.t.ppf(0.975, df=n - 1))
        except ImportError:
            t_crit = 1.959964

        margin = t_crit * se_diff
        ci_95: tuple[float, float] | None = (float(mean_diff - margin), float(mean_diff + margin))
    else:
        var_diff = None
        se_diff = None
        cohens_d = None
        ci_95 = None

    return PairedDifferenceStats(
        values=[float(d) for d in diffs],
        mean=mean_diff,
        median=median_diff,
        variance=var_diff,
        standard_error=se_diff,
        median_difference=median_diff,
        cohens_d_z=cohens_d,
        ci_95=ci_95,
    )


def calculate_wilcoxon_test(
    cond_a: Sequence[float],
    cond_b: Sequence[float],
    *,
    alternative: str | HypothesisAlternative = HypothesisAlternative.TWO_SIDED,
    min_pairs: int = 2,
    zero_method: str = "wilcox",
) -> InferentialStats:
    """Executes Wilcoxon signed-rank test with explicit zero handling and readiness gating."""
    alt_str = alternative.value if isinstance(alternative, HypothesisAlternative) else str(alternative)
    if alt_str not in ("two-sided", "greater", "less"):
        raise ValueError(f"Invalid alternative hypothesis '{alt_str}'. Expected 'two-sided', 'greater', or 'less'.")

    a = np.asarray(cond_a, dtype=float)
    b = np.asarray(cond_b, dtype=float)
    n = int(a.size)

    try:
        from scipy import stats
    except ImportError:
        return InferentialStats(
            test_name="Wilcoxon signed-rank test",
            status="scipy_unavailable",
            statistic=None,
            p_value=None,
            p_adjusted=None,
            alternative=alt_str,
            zero_method=zero_method,
            notes="SciPy is unavailable in environment; inferential statistics omitted without claiming significance.",
        )

    if n < min_pairs:
        return InferentialStats(
            test_name="Wilcoxon signed-rank test",
            status="insufficient_pairs",
            statistic=None,
            p_value=None,
            p_adjusted=None,
            alternative=alt_str,
            zero_method=zero_method,
            notes=f"Valid pair count ({n}) is strictly below the configured minimum-paired gate ({min_pairs}). Test remained descriptive.",
        )

    diffs = b - a
    if np.allclose(diffs, 0.0):
        return InferentialStats(
            test_name="Wilcoxon signed-rank test",
            status="all_paired_differences_zero",
            statistic=0.0,
            p_value=1.0,
            p_adjusted=1.0,
            alternative=alt_str,
            zero_method=zero_method,
            notes="All paired differences between condition A and condition B are exactly zero.",
        )

    try:
        # Note: testing b vs a evaluates whether condition_b is greater/less than condition_a
        res = stats.wilcoxon(b, a, zero_method=zero_method, alternative=alt_str)
        return InferentialStats(
            test_name="Wilcoxon signed-rank test",
            status="computed",
            statistic=float(res.statistic),
            p_value=float(res.pvalue),
            p_adjusted=None,
            alternative=alt_str,
            zero_method=zero_method,
            notes=f"Computed non-parametric test ({alt_str}, zero_method={zero_method}).",
        )
    except Exception as exc:
        return InferentialStats(
            test_name="Wilcoxon signed-rank test",
            status="execution_error",
            statistic=None,
            p_value=None,
            p_adjusted=None,
            alternative=alt_str,
            zero_method=zero_method,
            notes=f"Wilcoxon computation failed: {exc}",
        )


def evaluate_metric_cohort(
    metric_name: str,
    subject_pairs: Sequence[Mapping[str, Any]],
    *,
    alternative: str | HypothesisAlternative = HypothesisAlternative.TWO_SIDED,
    min_pairs: int = 2,
) -> MetricCohortStats:
    """Evaluates descriptive and inferential statistics for a single metric across paired subjects."""
    valid_a: list[float] = []
    valid_b: list[float] = []
    exclusions: list[ExclusionRecord] = []

    # Sort subject pairs deterministically by subject identifier
    sorted_pairs = sorted(subject_pairs, key=lambda p: str(p.get("subject", "")))

    for p in sorted_pairs:
        subj = str(p.get("subject", "unknown"))
        raw_a = p.get("condition_a")
        raw_b = p.get("condition_b")

        if raw_a is None:
            exclusions.append(ExclusionRecord(subject=subj, metric=metric_name, reason="missing_condition_a_metric"))
            continue
        if raw_b is None:
            exclusions.append(ExclusionRecord(subject=subj, metric=metric_name, reason="missing_condition_b_metric"))
            continue

        try:
            val_a = float(raw_a)
            val_b = float(raw_b)
        except (TypeError, ValueError) as exc:
            exclusions.append(ExclusionRecord(subject=subj, metric=metric_name, reason=f"non_numeric_metric_value: {exc}"))
            continue

        if not math.isfinite(val_a):
            exclusions.append(ExclusionRecord(subject=subj, metric=metric_name, reason=f"non_finite_metric_value: condition_a={val_a}"))
            continue
        if not math.isfinite(val_b):
            exclusions.append(ExclusionRecord(subject=subj, metric=metric_name, reason=f"non_finite_metric_value: condition_b={val_b}"))
            continue

        valid_a.append(val_a)
        valid_b.append(val_b)

    desc_a = calculate_descriptive_moments(valid_a)
    desc_b = calculate_descriptive_moments(valid_b)
    diff_stats = calculate_paired_differences(valid_a, valid_b)
    inferential = calculate_wilcoxon_test(valid_a, valid_b, alternative=alternative, min_pairs=min_pairs)

    return MetricCohortStats(
        metric_name=metric_name,
        valid_pairs_count=len(valid_a),
        excluded_pairs_count=len(exclusions),
        exclusion_records=exclusions,
        condition_a_stats=desc_a,
        condition_b_stats=desc_b,
        difference_stats=diff_stats,
        inferential_stats=inferential,
    )
