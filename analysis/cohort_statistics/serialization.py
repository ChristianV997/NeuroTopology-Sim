"""Serialization, validation, and I/O handlers for paired cohort statistics reports.

Enforces:
- Strict JSON specification compliance (no NaN/Inf; mapped to null).
- Safe atomic persistence with UTF-8 encoding.
- Checksum recalculation and tamper verification.
- Input loading from multiple structured cohort formats.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .calculator import compute_report_checksum
from .models import (
    CohortStatisticsReport,
    ConfidenceInterval,
    DescriptiveStats,
    EffectSizeEstimates,
    ExclusionRecord,
    InferentialStats,
    MetricCohortStats,
    PairedDifferenceStats,
    _safe_dict,
)


def load_cohort_input(path_or_data: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and normalize cohort metric input data from file path or dictionary.

    Supports:
    - Path to JSON file.
    - Dict mapping subject_id -> {arm_a: {...}, arm_b: {...}}
    - Dict with top-level 'cohort' or 'subjects' key.
    - Dict with 'pairs' list.
    """
    if isinstance(path_or_data, (str, Path)):
        path = Path(path_or_data)
        if not path.exists():
            raise FileNotFoundError(f"Cohort input file not found: {path}")
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    elif isinstance(path_or_data, Mapping):
        data = dict(path_or_data)
    else:
        raise TypeError(f"Expected path or mapping, got {type(path_or_data)}")

    if not isinstance(data, dict):
        raise ValueError(f"Cohort data must be a JSON object, got {type(data)}")

    # Unpack nested structures if present
    if "cohort" in data and isinstance(data["cohort"], dict):
        return data["cohort"]
    if "subjects" in data and isinstance(data["subjects"], dict):
        return data["subjects"]
    if "pairs" in data and isinstance(data["pairs"], list):
        normalized: dict[str, Any] = {}
        for item in data["pairs"]:
            if isinstance(item, dict) and "subject" in item:
                sub_id = str(item["subject"])
                normalized[sub_id] = item
        return normalized

    return data


def export_cohort_report_dict(report: CohortStatisticsReport) -> dict[str, Any]:
    """Export CohortStatisticsReport to a sanitized dictionary guaranteed free of NaN/Inf."""
    return report.to_dict()


def save_cohort_report(
    report: CohortStatisticsReport,
    output_path: str | Path,
    indent: int = 2,
) -> Path:
    """Save report to JSON file with strict allow_nan=False enforcement."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    report_dict = export_cohort_report_dict(report)

    # allow_nan=False guarantees standard RFC-8259 JSON compliance
    json_str = json.dumps(report_dict, indent=indent, allow_nan=False)

    # Atomic write pattern
    temp_p = out_p.with_suffix(f"{out_p.suffix}.tmp")
    try:
        temp_p.write_text(json_str, encoding="utf-8")
        temp_p.replace(out_p)
    finally:
        if temp_p.exists():
            try:
                temp_p.unlink()
            except OSError:
                pass

    return out_p


def verify_report_checksum(report_dict: dict[str, Any]) -> bool:
    """Verify whether report dictionary checksum matches calculated SHA-256 digest."""
    reported_checksum = report_dict.get("checksum", "")
    if not reported_checksum:
        return False
    expected_checksum = compute_report_checksum(report_dict)
    return reported_checksum == expected_checksum


def load_cohort_report(path_or_data: str | Path | Mapping[str, Any]) -> CohortStatisticsReport:
    """Reconstruct a CohortStatisticsReport object from file path or dictionary."""
    if isinstance(path_or_data, (str, Path)):
        raw_text = Path(path_or_data).read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    elif isinstance(path_or_data, Mapping):
        raw = dict(path_or_data)
    else:
        raise TypeError(f"Expected path or mapping, got {type(path_or_data)}")

    raw_metrics = raw.get("metrics", {})
    metrics_map: dict[str, MetricCohortStats] = {}

    for m_name, m_data in raw_metrics.items():
        exclusions = [
            ExclusionRecord(
                subject=e.get("subject", ""),
                metric=e.get("metric", m_name),
                reason=e.get("reason", ""),
            )
            for e in m_data.get("exclusion_records", [])
        ]
        c_a = m_data.get("condition_a_summary") or m_data.get("condition_a_stats", {})
        cond_a = DescriptiveStats(
            n=c_a.get("n", 0),
            mean=c_a.get("mean"),
            median=c_a.get("median"),
            variance=c_a.get("variance"),
            standard_error=c_a.get("standard_error"),
        )
        c_b = m_data.get("condition_b_summary") or m_data.get("condition_b_stats", {})
        cond_b = DescriptiveStats(
            n=c_b.get("n", 0),
            mean=c_b.get("mean"),
            median=c_b.get("median"),
            variance=c_b.get("variance"),
            standard_error=c_b.get("standard_error"),
        )
        diff_d = m_data.get("paired_differences") or m_data.get("difference_stats", {})
        ci_raw = diff_d.get("ci_95")
        ci_tuple = tuple(ci_raw) if isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2 else None
        diff_stats = PairedDifferenceStats(
            values=diff_d.get("values", []),
            mean=diff_d.get("mean"),
            median=diff_d.get("median"),
            variance=diff_d.get("variance"),
            standard_error=diff_d.get("standard_error"),
            median_difference=diff_d.get("median_difference"),
            effect_size_dz=diff_d.get("effect_size_dz"),
            rank_biserial_r=diff_d.get("rank_biserial_r"),
            ci_95=ci_tuple,  # type: ignore[arg-type]
        )

        eff_raw = m_data.get("effect_size_estimates", {})
        effect_sizes = EffectSizeEstimates(
            cohens_dz=eff_raw.get("cohens_dz", diff_stats.effect_size_dz),
            rank_biserial_r=eff_raw.get("rank_biserial_r", diff_stats.rank_biserial_r),
            method=eff_raw.get("method", "paired_cohens_dz_and_rank_biserial"),
            effective_sample_size=eff_raw.get("effective_sample_size", m_data.get("valid_pairs_count", 0)),
            label=eff_raw.get("label", "effect_estimate_not_formal_evidence"),
        )

        ci_data = m_data.get("confidence_interval", {})
        conf_int = ConfidenceInterval(
            method=ci_data.get("method", "student_t_95"),
            ci_95=tuple(ci_data["ci_95"]) if isinstance(ci_data.get("ci_95"), (list, tuple)) else ci_tuple,
            lower=ci_data.get("lower"),
            upper=ci_data.get("upper"),
        )

        inf_d = m_data.get("inferential_stats", {})
        stat = m_data.get("wilcoxon_statistic") if m_data.get("wilcoxon_statistic") is not None else inf_d.get("statistic")
        pval = m_data.get("wilcoxon_p_value") if m_data.get("wilcoxon_p_value") is not None else inf_d.get("p_value")

        metrics_map[m_name] = MetricCohortStats(
            metric_name=m_name,
            effective_paired_sample_size=m_data.get("effective_paired_sample_size", m_data.get("valid_pairs_count", 0)),
            valid_pairs_count=m_data.get("valid_pairs_count", 0),
            excluded_pairs_count=m_data.get("excluded_pairs_count", 0),
            exclusion_records=exclusions,
            condition_a_summary=cond_a,
            condition_b_summary=cond_b,
            paired_differences=diff_stats,
            wilcoxon_statistic=stat,
            wilcoxon_p_value=pval,
            tie_count=m_data.get("tie_count", 0),
            zero_difference_count=m_data.get("zero_difference_count", inf_d.get("zero_count", 0)),
            effect_size_estimates=effect_sizes,
            confidence_interval=conf_int,
            multiplicity_method=m_data.get("multiplicity_method", "holm"),
            multiplicity_status=m_data.get("multiplicity_status", "none"),
            p_adjusted=m_data.get("p_adjusted", inf_d.get("p_adjusted")),
            status=m_data.get("status", inf_d.get("status", "available")),
            notes=m_data.get("notes", inf_d.get("notes", "")),
        )

    cond_labels = raw.get("condition_labels") or [
        raw.get("condition_a_label", "condition_a"),
        raw.get("condition_b_label", "condition_b"),
    ]

    return CohortStatisticsReport(
        schema_version=raw.get("schema_version") or raw.get("schema", "NeuroTopologySim.CohortStatisticsReport.v2"),
        cohort_identifier=raw.get("cohort_identifier") or raw.get("dataset_id"),
        condition_labels=cond_labels,
        pairing_key=raw.get("pairing_key", "subject_id"),
        subjects_included=raw.get("subjects_included", []),
        subjects_excluded=raw.get("subjects_excluded", []),
        exclusion_reasons=raw.get("exclusion_reasons", {}),
        effective_paired_sample_size=raw.get("effective_paired_sample_size", 0),
        total_subjects_evaluated=raw.get("total_subjects_evaluated", 0),
        formal_bayes_factor=None,
        scientific_pass=False,
        evidence_class=raw.get("evidence_class", "descriptive_or_paired_statistics"),
        synthetic_status=raw.get("synthetic_status") or ("synthetic_demo" if raw.get("is_synthetic") else "empirical"),
        provenance=raw.get("provenance") or raw.get("provenance_status", "empirical"),
        finite_value_status=raw.get("finite_value_status", "all_finite"),
        multiplicity_method=raw.get("multiplicity_method", "holm"),
        min_pairs=raw.get("min_pairs", 3),
        checksum=raw.get("checksum", ""),
        metrics=metrics_map,
        scientific_notes=raw.get("scientific_notes", []),
    )
