"""Data models, schemas, and typed records for paired-cohort statistics and effect sizes.

Guarantees:
- Versioned paired-cohort statistics schema (v2).
- Explicit tracking of included/excluded subjects and exclusion reasons.
- Strict finite/null serialization (never NaN or Infinity in outputs).
- Multiplicity and provenance metadata encapsulation.
- Explicit non-evidence disclaimers:
    formal_bayes_factor = null
    scientific_pass = false
    evidence_class = "descriptive_or_paired_statistics"
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class HypothesisAlternative(str, Enum):
    """Directionality of paired hypothesis tests."""
    TWO_SIDED = "two-sided"
    GREATER = "greater"
    LESS = "less"


class MultiplicityMethod(str, Enum):
    """Multiple testing correction methods."""
    HOLM = "holm"
    BONFERRONI = "bonferroni"
    FDR_BH = "fdr_bh"
    NONE = "none"
    UNAVAILABLE = "multiplicity_unavailable"


class ProvenanceStatus(str, Enum):
    """Provenance and study origin classification."""
    EMPIRICAL = "empirical"
    SYNTHETIC_DEMO = "synthetic_demo"
    INCOMPLETE = "incomplete_provenance"


@dataclass(frozen=True)
class ExclusionRecord:
    """Record of an individual pair excluded from cohort analysis."""
    subject: str
    metric: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "metric": self.metric,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DescriptiveStats:
    """Summary statistics for a single experimental condition."""
    n: int
    mean: float | None
    median: float | None
    variance: float | None
    standard_error: float | None

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass(frozen=True)
class PairedDifferenceStats:
    """Statistics for within-subject paired differences (Condition A - Condition B)."""
    values: list[float]
    mean: float | None
    median: float | None
    variance: float | None
    standard_error: float | None
    median_difference: float | None
    effect_size_dz: float | None
    rank_biserial_r: float | None
    ci_95: tuple[float, float] | None

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass(frozen=True)
class InferentialStats:
    """Inferential non-parametric and parametric test results."""
    test_name: str
    status: str  # "available", "unavailable", "insufficient_pairs"
    statistic: float | None
    p_value: float | None
    p_adjusted: float | None
    alternative: str
    zero_method: str
    zero_count: int
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass(frozen=True)
class EffectSizeEstimates:
    """Paired effect size estimates labeled as estimates rather than formal evidence."""
    cohens_dz: float | None
    rank_biserial_r: float | None
    method: str
    effective_sample_size: int
    label: str = "effect_estimate_not_formal_evidence"

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass(frozen=True)
class ConfidenceInterval:
    """Confidence interval estimation for mean difference."""
    method: str
    ci_95: tuple[float, float] | None
    lower: float | None
    upper: float | None

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass
class MetricCohortStats:
    """Complete paired statistics report for a single topological or signal metric."""
    metric_name: str
    effective_paired_sample_size: int
    valid_pairs_count: int
    excluded_pairs_count: int
    exclusion_records: list[ExclusionRecord]
    condition_a_summary: DescriptiveStats
    condition_b_summary: DescriptiveStats
    paired_differences: PairedDifferenceStats
    wilcoxon_statistic: float | None
    wilcoxon_p_value: float | None
    tie_count: int
    zero_difference_count: int
    effect_size_estimates: EffectSizeEstimates
    confidence_interval: ConfidenceInterval
    multiplicity_method: str
    multiplicity_status: str  # "corrected", "multiplicity_unavailable", "none"
    p_adjusted: float | None
    status: str  # "available", "unavailable", "insufficient_pairs"
    notes: str

    # Backward compatibility properties
    @property
    def condition_a_stats(self) -> DescriptiveStats:
        return self.condition_a_summary

    @property
    def condition_b_stats(self) -> DescriptiveStats:
        return self.condition_b_summary

    @property
    def difference_stats(self) -> PairedDifferenceStats:
        return self.paired_differences

    @property
    def inferential_stats(self) -> InferentialStats:
        return InferentialStats(
            test_name="wilcoxon_signed_rank",
            status=self.status,
            statistic=self.wilcoxon_statistic,
            p_value=self.wilcoxon_p_value,
            p_adjusted=self.p_adjusted,
            alternative="two-sided",
            zero_method="pratt",
            zero_count=self.zero_difference_count,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "effective_paired_sample_size": self.effective_paired_sample_size,
            "valid_pairs_count": self.valid_pairs_count,
            "excluded_pairs_count": self.excluded_pairs_count,
            "exclusion_records": [e.to_dict() for e in self.exclusion_records],
            "condition_a_summary": self.condition_a_summary.to_dict(),
            "condition_b_summary": self.condition_b_summary.to_dict(),
            "condition_a_stats": self.condition_a_summary.to_dict(),
            "condition_b_stats": self.condition_b_summary.to_dict(),
            "paired_differences": self.paired_differences.to_dict(),
            "difference_stats": self.paired_differences.to_dict(),
            "wilcoxon_statistic": self.wilcoxon_statistic,
            "wilcoxon_p_value": self.wilcoxon_p_value,
            "tie_count": self.tie_count,
            "zero_difference_count": self.zero_difference_count,
            "effect_size_estimates": self.effect_size_estimates.to_dict(),
            "confidence_interval": self.confidence_interval.to_dict(),
            "multiplicity_method": self.multiplicity_method,
            "multiplicity_status": self.multiplicity_status,
            "p_adjusted": self.p_adjusted,
            "status": self.status,
            "notes": self.notes,
            "inferential_stats": self.inferential_stats.to_dict(),
        }


@dataclass
class CohortStatisticsReport:
    """Top-level versioned paired cohort statistics report artifact."""
    schema_version: str = "NeuroTopologySim.CohortStatisticsReport.v2"
    cohort_identifier: str | None = None
    condition_labels: list[str] = field(default_factory=list)
    pairing_key: str = "subject_id"
    subjects_included: list[str] = field(default_factory=list)
    subjects_excluded: list[str] = field(default_factory=list)
    exclusion_reasons: dict[str, list[str]] = field(default_factory=dict)
    effective_paired_sample_size: int = 0
    total_subjects_evaluated: int = 0
    formal_bayes_factor: None = None
    scientific_pass: bool = False
    evidence_class: str = "descriptive_or_paired_statistics"
    synthetic_status: str = ProvenanceStatus.EMPIRICAL.value
    provenance: str = ProvenanceStatus.EMPIRICAL.value
    finite_value_status: str = "all_finite"
    multiplicity_method: str = MultiplicityMethod.HOLM.value
    min_pairs: int = 3
    checksum: str = ""
    metrics: dict[str, MetricCohortStats] = field(default_factory=dict)
    scientific_notes: list[str] = field(default_factory=list)

    # Aliases for backward compatibility
    @property
    def schema(self) -> str:
        return self.schema_version

    @property
    def dataset_id(self) -> str | None:
        return self.cohort_identifier

    @property
    def is_synthetic(self) -> bool:
        return self.synthetic_status == ProvenanceStatus.SYNTHETIC_DEMO.value

    @property
    def provenance_status(self) -> str:
        return self.provenance

    @property
    def condition_a_label(self) -> str:
        return self.condition_labels[0] if self.condition_labels else "condition_a"

    @property
    def condition_b_label(self) -> str:
        return self.condition_labels[1] if len(self.condition_labels) > 1 else "condition_b"

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "schema": self.schema_version,
            "cohort_identifier": self.cohort_identifier,
            "dataset_id": self.cohort_identifier,
            "condition_labels": self.condition_labels,
            "condition_a_label": self.condition_a_label,
            "condition_b_label": self.condition_b_label,
            "pairing_key": self.pairing_key,
            "subjects_included": self.subjects_included,
            "subjects_excluded": self.subjects_excluded,
            "exclusion_reasons": self.exclusion_reasons,
            "effective_paired_sample_size": self.effective_paired_sample_size,
            "total_subjects_evaluated": self.total_subjects_evaluated,
            "formal_bayes_factor": None,
            "scientific_pass": False,
            "evidence_class": self.evidence_class,
            "synthetic_status": self.synthetic_status,
            "is_synthetic": self.is_synthetic,
            "provenance": self.provenance,
            "provenance_status": self.provenance,
            "finite_value_status": self.finite_value_status,
            "multiplicity_method": self.multiplicity_method,
            "min_pairs": self.min_pairs,
            "checksum": self.checksum,
            "metrics": {k: v.to_dict() for k, v in sorted(self.metrics.items())},
            "scientific_notes": self.scientific_notes,
        })


def _safe_dict(val: Any) -> Any:
    """Recursively convert data structures, enforcing finite values and mapping non-finite to null."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, dict):
        return {str(k): _safe_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_dict(v) for v in val]
    return str(val)
