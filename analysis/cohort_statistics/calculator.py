"""Mathematical and statistical computation engine for paired-cohort metrics.

Implements:
- Deterministic subject pairing with strict identifier sorting.
- Explicit non-silent exclusion recording for missing/corrupt arms or non-finite values.
- Within-subject paired difference statistics.
- Paired effect size Cohen's d_z = mean(diff) / std(diff, ddof=1).
- Non-parametric rank-biserial correlation r for Wilcoxon signed-rank.
- Wilcoxon signed-rank test with explicit zero-difference handling and SciPy fallback.
- Multiplicity correction propagation across evaluated metrics.
- Deterministic SHA-256 integrity checksumming.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

try:
    import scipy.stats as sp_stats
except ImportError:
    sp_stats = None

from .models import (
    CohortStatisticsReport,
    DescriptiveStats,
    ExclusionRecord,
    HypothesisAlternative,
    InferentialStats,
    MetricCohortStats,
    MultiplicityMethod,
    PairedDifferenceStats,
    ProvenanceStatus,
    _safe_dict,
)
from .multiplicity import adjust_p_values


def _student_t_crit_975(df: int) -> float:
    """Return two-sided 95% critical value t_0.975 for Student-t distribution."""
    if df <= 0:
        return 1.95996
    # Exact lookup for small degrees of freedom
    t_table = {
        1: 12.7062, 2: 4.3027, 3: 3.1824, 4: 2.7764, 5: 2.5706,
        6: 2.4469, 7: 2.3646, 8: 2.3060, 9: 2.2622, 10: 2.2281,
        11: 2.2010, 12: 2.1788, 13: 2.1604, 14: 2.1448, 15: 2.1314,
        16: 2.1199, 17: 2.1098, 18: 2.1009, 19: 2.0930, 20: 2.0860,
        25: 2.0595, 30: 2.0423, 40: 2.0211, 50: 2.0086, 60: 2.0003,
        80: 1.9901, 100: 1.9840, 120: 1.9799,
    }
    if df in t_table:
        return t_table[df]
    if sp_stats is not None:
        try:
            return float(sp_stats.t.ppf(0.975, df=df))
        except Exception:
            pass
    # Asymptotic approximation for df > 20
    return 1.95996 + 2.372 / df + 2.82 / (df ** 2)


def compute_descriptive_stats(values: Sequence[float]) -> DescriptiveStats:
    """Compute descriptive statistics for a condition array."""
    finite_vals = [v for v in values if math.isfinite(v)]
    n = len(finite_vals)
    if n == 0:
        return DescriptiveStats(n=0, mean=None, median=None, variance=None, standard_error=None)

    mean_val = sum(finite_vals) / n
    sorted_vals = sorted(finite_vals)
    mid = n // 2
    if n % 2 == 1:
        median_val = sorted_vals[mid]
    else:
        median_val = (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0

    if n > 1:
        variance_val = sum((x - mean_val) ** 2 for x in finite_vals) / (n - 1)
        se_val = math.sqrt(variance_val / n)
    else:
        variance_val = None
        se_val = None

    return DescriptiveStats(
        n=n,
        mean=mean_val,
        median=median_val,
        variance=variance_val,
        standard_error=se_val,
    )


def compute_paired_effect_size_dz(diffs: Sequence[float]) -> float | None:
    """Compute Cohen's d_z for paired data: mean(diff) / std(diff, ddof=1)."""
    finite_diffs = [d for d in diffs if math.isfinite(d)]
    n = len(finite_diffs)
    if n < 2:
        return None

    mean_d = sum(finite_diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in finite_diffs) / (n - 1)
    std_d = math.sqrt(var_d)

    if std_d == 0.0:
        return 0.0 if mean_d == 0.0 else None

    return mean_d / std_d


def compute_rank_biserial_r(diffs: Sequence[float]) -> float | None:
    """Compute rank-biserial correlation r for paired signed ranks: (W+ - W-) / (W+ + W-)."""
    finite_diffs = [d for d in diffs if math.isfinite(d)]
    non_zero = [d for d in finite_diffs if d != 0.0]
    if not non_zero:
        return 0.0 if finite_diffs else None

    # Compute ranks of absolute differences with standard average tie resolution
    indexed_abs = sorted(enumerate(non_zero), key=lambda x: abs(x[1]))
    n = len(indexed_abs)
    ranks: list[float] = [0.0] * n

    i = 0
    while i < n:
        j = i
        while j < n - 1 and abs(indexed_abs[j][1]) == abs(indexed_abs[j + 1][1]):
            j += 1
        # Average rank for ties (1-based ranking)
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            orig_idx = indexed_abs[k][0]
            ranks[orig_idx] = avg_rank
        i = j + 1

    w_pos = sum(r for r, d in zip(ranks, non_zero) if d > 0.0)
    w_neg = sum(r for r, d in zip(ranks, non_zero) if d < 0.0)
    w_tot = w_pos + w_neg

    if w_tot == 0.0:
        return 0.0

    return (w_pos - w_neg) / w_tot


def compute_paired_difference_stats(diffs: Sequence[float]) -> PairedDifferenceStats:
    """Compute comprehensive difference and effect-size statistics for paired data."""
    finite_diffs = [d for d in diffs if math.isfinite(d)]
    n = len(finite_diffs)
    if n == 0:
        return PairedDifferenceStats(
            values=[],
            mean=None,
            median=None,
            variance=None,
            standard_error=None,
            median_difference=None,
            effect_size_dz=None,
            rank_biserial_r=None,
            ci_95=None,
        )

    mean_d = sum(finite_diffs) / n
    sorted_d = sorted(finite_diffs)
    mid = n // 2
    if n % 2 == 1:
        median_d = sorted_d[mid]
    else:
        median_d = (sorted_d[mid - 1] + sorted_d[mid]) / 2.0

    if n > 1:
        var_d = sum((d - mean_d) ** 2 for d in finite_diffs) / (n - 1)
        se_d = math.sqrt(var_d / n)
        t_crit = _student_t_crit_975(df=n - 1)
        ci_95 = (mean_d - t_crit * se_d, mean_d + t_crit * se_d)
    else:
        var_d = None
        se_d = None
        ci_95 = None

    dz = compute_paired_effect_size_dz(finite_diffs)
    rb_r = compute_rank_biserial_r(finite_diffs)

    return PairedDifferenceStats(
        values=[float(d) for d in finite_diffs],
        mean=mean_d,
        median=median_d,
        variance=var_d,
        standard_error=se_d,
        median_difference=median_d,
        effect_size_dz=dz,
        rank_biserial_r=rb_r,
        ci_95=ci_95,
    )


def compute_inferential_stats(
    diffs: Sequence[float],
    alternative: HypothesisAlternative | str = HypothesisAlternative.TWO_SIDED,
    min_pairs: int = 3,
    zero_method: str = "pratt",
) -> InferentialStats:
    """Execute Wilcoxon signed-rank test or produce explicit unavailable/insufficient status."""
    if isinstance(alternative, str):
        try:
            alternative = HypothesisAlternative(alternative.lower())
        except ValueError:
            alternative = HypothesisAlternative.TWO_SIDED

    finite_diffs = [d for d in diffs if math.isfinite(d)]
    n = len(finite_diffs)
    zero_count = sum(1 for d in finite_diffs if d == 0.0)

    if sp_stats is None:
        return InferentialStats(
            test_name="wilcoxon_signed_rank",
            status="unavailable",
            statistic=None,
            p_value=None,
            p_adjusted=None,
            alternative=alternative.value,
            zero_method=zero_method,
            zero_count=zero_count,
            notes="SciPy unavailable in execution environment; inferential test deferred.",
        )

    if n < min_pairs:
        return InferentialStats(
            test_name="wilcoxon_signed_rank",
            status="insufficient_pairs",
            statistic=None,
            p_value=None,
            p_adjusted=None,
            alternative=alternative.value,
            zero_method=zero_method,
            zero_count=zero_count,
            notes=f"Valid paired count ({n}) is below minimum threshold ({min_pairs}).",
        )

    # All differences exactly zero
    if zero_count == n:
        return InferentialStats(
            test_name="wilcoxon_signed_rank",
            status="available",
            statistic=0.0,
            p_value=1.0,
            p_adjusted=None,
            alternative=alternative.value,
            zero_method=zero_method,
            zero_count=zero_count,
            notes="All paired differences are zero.",
        )

    try:
        res = sp_stats.wilcoxon(
            finite_diffs,
            alternative=alternative.value,
            zero_method=zero_method,
        )
        stat = float(res.statistic) if math.isfinite(res.statistic) else None
        p = float(res.pvalue) if math.isfinite(res.pvalue) else None
        status = "available" if p is not None else "unavailable"
        notes = "Wilcoxon signed-rank test computed successfully."
    except Exception as exc:
        status = "unavailable"
        stat = None
        p = None
        notes = f"Wilcoxon calculation raised: {exc}"

    return InferentialStats(
        test_name="wilcoxon_signed_rank",
        status=status,
        statistic=stat,
        p_value=p,
        p_adjusted=None,
        alternative=alternative.value,
        zero_method=zero_method,
        zero_count=zero_count,
        notes=notes,
    )


def compute_report_checksum(report_dict: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 digest over sorted JSON representation of report."""
    canonical = {k: v for k, v in report_dict.items() if k != "checksum"}
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def calculate_paired_cohort_report(
    cohort_data: Mapping[str, Any],
    condition_a_name: str = "condition_a",
    condition_b_name: str = "condition_b",
    metrics: Sequence[str] | None = None,
    dataset_id: str | None = None,
    alternative: HypothesisAlternative | str = HypothesisAlternative.TWO_SIDED,
    multiplicity_method: MultiplicityMethod | str = MultiplicityMethod.HOLM,
    min_pairs: int = 3,
    is_synthetic: bool = False,
    provenance_status: ProvenanceStatus | str = ProvenanceStatus.EMPIRICAL,
    zero_method: str = "pratt",
    extra_notes: Sequence[str] | None = None,
) -> CohortStatisticsReport:
    """Evaluate paired cohort statistics across specified metrics with full provenance and guardrails.

    Input cohort_data format:
      dict mapping subject_id -> {
          condition_a_name: {metric1: val, ..., "error": ""},
          condition_b_name: {metric1: val, ..., "error": ""},
      }
    """
    if isinstance(alternative, str):
        try:
            alternative = HypothesisAlternative(alternative.lower())
        except ValueError:
            alternative = HypothesisAlternative.TWO_SIDED

    if isinstance(multiplicity_method, str):
        try:
            multiplicity_method = MultiplicityMethod(multiplicity_method.lower())
        except ValueError:
            multiplicity_method = MultiplicityMethod.HOLM

    if isinstance(provenance_status, str):
        try:
            provenance_status = ProvenanceStatus(provenance_status.lower())
        except ValueError:
            provenance_status = ProvenanceStatus.EMPIRICAL

    # Deterministic sorting of subject IDs
    sorted_subject_ids = sorted(cohort_data.keys())
    total_subjects = len(sorted_subject_ids)

    # Discover metrics if not explicitly passed
    if metrics is None:
        discovered_metrics: set[str] = set()
        for sub_id in sorted_subject_ids:
            sub_rec = cohort_data[sub_id]
            if isinstance(sub_rec, dict):
                for arm_name in (condition_a_name, condition_b_name):
                    arm_val = sub_rec.get(arm_name)
                    if isinstance(arm_val, dict):
                        for m_key in arm_val.keys():
                            if m_key not in ("error", "status", "notes"):
                                discovered_metrics.add(m_key)
        metrics = sorted(discovered_metrics)

    metric_reports: dict[str, MetricCohortStats] = {}
    metric_p_values: list[float | None] = []
    metric_names_in_order: list[str] = []

    for metric in sorted(metrics):
        metric_names_in_order.append(metric)
        clean_a_vals: list[float] = []
        clean_b_vals: list[float] = []
        diffs: list[float] = []
        exclusions: list[ExclusionRecord] = []

        seen_subjects: set[str] = set()

        for sub_id in sorted_subject_ids:
            if sub_id in seen_subjects:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason="duplicate_subject_id")
                )
                continue
            seen_subjects.add(sub_id)

            sub_val = cohort_data[sub_id]
            if not isinstance(sub_val, dict):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason="subject_record_not_dict")
                )
                continue

            # Check Condition A
            if condition_a_name not in sub_val:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"missing_{condition_a_name}")
                )
                continue
            arm_a = sub_val[condition_a_name]
            if not isinstance(arm_a, dict):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"{condition_a_name}_not_dict")
                )
                continue
            err_a = arm_a.get("error")
            if err_a:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"{condition_a_name}_error: {err_a}")
                )
                continue

            # Check Condition B
            if condition_b_name not in sub_val:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"missing_{condition_b_name}")
                )
                continue
            arm_b = sub_val[condition_b_name]
            if not isinstance(arm_b, dict):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"{condition_b_name}_not_dict")
                )
                continue
            err_b = arm_b.get("error")
            if err_b:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"{condition_b_name}_error: {err_b}")
                )
                continue

            # Check metric presence
            if metric not in arm_a:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"metric_missing_in_{condition_a_name}")
                )
                continue
            if metric not in arm_b:
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"metric_missing_in_{condition_b_name}")
                )
                continue

            raw_a = arm_a[metric]
            raw_b = arm_b[metric]

            try:
                val_a = float(raw_a)
            except (ValueError, TypeError):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"unparseable_{condition_a_name}_val")
                )
                continue

            try:
                val_b = float(raw_b)
            except (ValueError, TypeError):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"unparseable_{condition_b_name}_val")
                )
                continue

            if not math.isfinite(val_a):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"non_finite_{condition_a_name}_val")
                )
                continue

            if not math.isfinite(val_b):
                exclusions.append(
                    ExclusionRecord(subject=sub_id, metric=metric, reason=f"non_finite_{condition_b_name}_val")
                )
                continue

            clean_a_vals.append(val_a)
            clean_b_vals.append(val_b)
            diffs.append(val_a - val_b)

        # Compute stats for metric
        desc_a = compute_descriptive_stats(clean_a_vals)
        desc_b = compute_descriptive_stats(clean_b_vals)
        diff_stats = compute_paired_difference_stats(diffs)
        inf_stats = compute_inferential_stats(
            diffs,
            alternative=alternative,
            min_pairs=min_pairs,
            zero_method=zero_method,
        )

        metric_p_values.append(inf_stats.p_value)

        metric_reports[metric] = MetricCohortStats(
            metric_name=metric,
            valid_pairs_count=len(diffs),
            excluded_pairs_count=len(exclusions),
            exclusion_records=exclusions,
            condition_a_stats=desc_a,
            condition_b_stats=desc_b,
            difference_stats=diff_stats,
            inferential_stats=inf_stats,
        )

    # Multiplicity correction
    adjusted_p_values = adjust_p_values(metric_p_values, method=multiplicity_method)
    for metric_name, adj_p in zip(metric_names_in_order, adjusted_p_values):
        old_inf = metric_reports[metric_name].inferential_stats
        # Update inferential stats with adjusted p-value
        new_inf = InferentialStats(
            test_name=old_inf.test_name,
            status=old_inf.status,
            statistic=old_inf.statistic,
            p_value=old_inf.p_value,
            p_adjusted=adj_p,
            alternative=old_inf.alternative,
            zero_method=old_inf.zero_method,
            zero_count=old_inf.zero_count,
            notes=old_inf.notes,
        )
        metric_reports[metric_name].inferential_stats = new_inf

    scientific_notes = [
        "Paired difference calculated as: condition_a - condition_b.",
        "Paired effect size d_z computed as mean(diff) / std(diff, ddof=1).",
        "Rank-biserial correlation r reflects Wilcoxon signed-rank sum-of-ranks contrast (W+ - W-) / (W+ + W-).",
        "Multiple comparison correction applied across metrics without inflating hypothesis count for missing tests.",
        "GUARDRAIL: Paired statistical significance does NOT establish biological proof, clinical efficacy, or ontology promotion.",
    ]
    if extra_notes:
        scientific_notes.extend(extra_notes)

    report = CohortStatisticsReport(
        dataset_id=dataset_id,
        condition_a_label=condition_a_name,
        condition_b_label=condition_b_name,
        total_subjects_evaluated=total_subjects,
        is_synthetic=is_synthetic,
        provenance_status=provenance_status.value,
        multiplicity_method=multiplicity_method.value,
        min_pairs=min_pairs,
        checksum="",
        metrics=metric_reports,
        scientific_notes=scientific_notes,
    )

    # Compute checksum
    report_dict = report.to_dict()
    checksum = compute_report_checksum(report_dict)
    report.checksum = checksum

    return report
