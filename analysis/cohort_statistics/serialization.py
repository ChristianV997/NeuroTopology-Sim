"""Deterministic serialization and report builder for paired-cohort statistics."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .calculator import evaluate_metric_cohort
from .models import (
    CohortStatisticsReport,
    HypothesisAlternative,
    InferentialStats,
    MultiplicityMethod,
    ProvenanceStatus,
)
from .multiplicity import adjust_p_values


def compute_report_checksum(payload: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 block hash of canonical report payload."""
    canonical_copy = dict(payload)
    canonical_copy["checksum"] = ""
    canonical_json = json.dumps(canonical_copy, sort_keys=True, indent=2, allow_nan=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def build_cohort_statistics_report(
    input_records: Sequence[Mapping[str, Any]],
    *,
    condition_a_label: str = "condition_a",
    condition_b_label: str = "condition_b",
    metrics: Sequence[str] | None = None,
    multiplicity_method: str | MultiplicityMethod = MultiplicityMethod.HOLM,
    alternative: str | HypothesisAlternative = HypothesisAlternative.TWO_SIDED,
    min_pairs: int = 2,
    is_synthetic: bool = False,
    provenance_status: str | ProvenanceStatus = ProvenanceStatus.EMPIRICAL,
    dataset_id: str | None = None,
) -> CohortStatisticsReport:
    """Builds comprehensive paired-cohort statistics report with multiplicity adjustments."""
    method_val = multiplicity_method.value if isinstance(multiplicity_method, MultiplicityMethod) else str(multiplicity_method)
    alt_val = alternative.value if isinstance(alternative, HypothesisAlternative) else str(alternative)
    prov_val = provenance_status.value if isinstance(provenance_status, ProvenanceStatus) else str(provenance_status)

    # Deterministically sort input records by subject
    sorted_records = sorted(input_records, key=lambda r: str(r.get("subject", "")))
    unique_subjects = {str(r.get("subject", "")) for r in sorted_records if r.get("subject")}

    # Discover metrics if not provided
    if metrics is None:
        found_metrics: set[str] = set()
        for r in sorted_records:
            a_mets = r.get("condition_a_metrics", {})
            b_mets = r.get("condition_b_metrics", {})
            if isinstance(a_mets, dict):
                found_metrics.update(a_mets.keys())
            if isinstance(b_mets, dict):
                found_metrics.update(b_mets.keys())
        target_metrics = sorted(list(found_metrics))
    else:
        target_metrics = list(metrics)

    metric_stats_map = {}
    raw_p_values = {}

    for metric in target_metrics:
        pair_list = []
        for r in sorted_records:
            subj = str(r.get("subject", "unknown"))
            a_val = None
            b_val = None

            # Handle direct dictionary metric nesting
            if "condition_a_metrics" in r and isinstance(r["condition_a_metrics"], dict):
                a_val = r["condition_a_metrics"].get(metric)
            elif "condition_a" in r and isinstance(r["condition_a"], dict):
                a_val = r["condition_a"].get(metric)

            if "condition_b_metrics" in r and isinstance(r["condition_b_metrics"], dict):
                b_val = r["condition_b_metrics"].get(metric)
            elif "condition_b" in r and isinstance(r["condition_b"], dict):
                b_val = r["condition_b"].get(metric)

            pair_list.append({
                "subject": subj,
                "condition_a": a_val,
                "condition_b": b_val,
            })

        evaluated = evaluate_metric_cohort(
            metric_name=metric,
            subject_pairs=pair_list,
            alternative=alt_val,
            min_pairs=min_pairs,
        )
        metric_stats_map[metric] = evaluated
        raw_p_values[metric] = evaluated.inferential_stats.p_value

    # Apply multiplicity correction
    adjusted_p_values = adjust_p_values(raw_p_values, method=method_val)

    # Update inferential stats with adjusted p-values
    for metric, evaluated in metric_stats_map.items():
        inf = evaluated.inferential_stats
        evaluated.inferential_stats = InferentialStats(
            test_name=inf.test_name,
            status=inf.status,
            statistic=inf.statistic,
            p_value=inf.p_value,
            p_adjusted=adjusted_p_values.get(metric),
            alternative=inf.alternative,
            zero_method=inf.zero_method,
            notes=inf.notes,
        )

    scientific_notes = [
        "Descriptive moments and differences characterize the observed cohort distribution; inferential tests (Wilcoxon) evaluate within-subject paired differences.",
        "beta_1 represents 1D persistent topological homology; it is distinct from physical montage spatial topological charge.",
        "Zero-difference handling uses the 'wilcox' method; all-zero paired difference cases report p=1.0 explicitly.",
        "Significance is never inferred from uncomputed, missing, or underpowered tests.",
        "No formal Bayes factor is produced or claimed by this descriptive/non-parametric statistics layer.",
    ]

    report = CohortStatisticsReport(
        schema="NeuroTopologySim.CohortStatisticsReport.v1",
        dataset_id=dataset_id,
        condition_a_label=condition_a_label,
        condition_b_label=condition_b_label,
        total_subjects_evaluated=len(unique_subjects),
        is_synthetic=is_synthetic,
        provenance_status=prov_val,
        multiplicity_method=method_val,
        min_pairs=min_pairs,
        checksum="",
        metrics=metric_stats_map,
        scientific_notes=scientific_notes,
    )

    # Compute deterministic SHA-256
    report.checksum = compute_report_checksum(report.to_dict())
    return report


def export_report_json(report: CohortStatisticsReport, path: str | Path | None = None) -> str:
    """Serializes report to deterministic JSON with allow_nan=False."""
    payload = report.to_dict()
    text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path is not None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return text


def export_report_csv(report: CohortStatisticsReport, path: str | Path | None = None) -> str:
    """Exports tabular summary of metrics and paired differences to CSV."""
    headers = [
        "metric",
        "valid_pairs",
        "excluded_pairs",
        "mean_a",
        "median_a",
        "var_a",
        "se_a",
        "mean_b",
        "median_b",
        "var_b",
        "se_b",
        "mean_diff",
        "median_diff",
        "cohens_d_z",
        "ci95_lower",
        "ci95_upper",
        "wilcoxon_stat",
        "p_value",
        "p_adjusted",
        "test_status",
    ]
    rows = []
    for metric_name, m in sorted(report.metrics.items()):
        ci_lower = f"{m.difference_stats.ci_95[0]:.6g}" if m.difference_stats.ci_95 else ""
        ci_upper = f"{m.difference_stats.ci_95[1]:.6g}" if m.difference_stats.ci_95 else ""

        def _fmt(val: float | None) -> str:
            return "" if val is None else f"{val:.6g}"

        rows.append({
            "metric": metric_name,
            "valid_pairs": str(m.valid_pairs_count),
            "excluded_pairs": str(m.excluded_pairs_count),
            "mean_a": _fmt(m.condition_a_stats.mean),
            "median_a": _fmt(m.condition_a_stats.median),
            "var_a": _fmt(m.condition_a_stats.variance),
            "se_a": _fmt(m.condition_a_stats.standard_error),
            "mean_b": _fmt(m.condition_b_stats.mean),
            "median_b": _fmt(m.condition_b_stats.median),
            "var_b": _fmt(m.condition_b_stats.variance),
            "se_b": _fmt(m.condition_b_stats.standard_error),
            "mean_diff": _fmt(m.difference_stats.mean),
            "median_diff": _fmt(m.difference_stats.median_difference),
            "cohens_d_z": _fmt(m.difference_stats.cohens_d_z),
            "ci95_lower": ci_lower,
            "ci95_upper": ci_upper,
            "wilcoxon_stat": _fmt(m.inferential_stats.statistic),
            "p_value": _fmt(m.inferential_stats.p_value),
            "p_adjusted": _fmt(m.inferential_stats.p_adjusted),
            "test_status": m.inferential_stats.status,
        })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_text = buf.getvalue()

    if path is not None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(csv_text, encoding="utf-8")
    return csv_text
