"""Data models, schemas, and typed records for paired-cohort statistics and effect sizes.

Guarantees:
- Structured descriptive, difference, and inferential metrics.
- Explicit tracking of exclusion records and reasons.
- Strict finite/null serialization (never NaN or Infinity in outputs).
- Multiplicity and provenance metadata encapsulation.
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


@dataclass
class MetricCohortStats:
    """Complete paired statistics report for a single topological or signal metric."""
    metric_name: str
    valid_pairs_count: int
    excluded_pairs_count: int
    exclusion_records: list[ExclusionRecord]
    condition_a_stats: DescriptiveStats
    condition_b_stats: DescriptiveStats
    difference_stats: PairedDifferenceStats
    inferential_stats: InferentialStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "valid_pairs_count": self.valid_pairs_count,
            "excluded_pairs_count": self.excluded_pairs_count,
            "exclusion_records": [e.to_dict() for e in self.exclusion_records],
            "condition_a_stats": self.condition_a_stats.to_dict(),
            "condition_b_stats": self.condition_b_stats.to_dict(),
            "difference_stats": self.difference_stats.to_dict(),
            "inferential_stats": self.inferential_stats.to_dict(),
        }


@dataclass
class CohortStatisticsReport:
    """Top-level paired cohort statistics report artifact."""
    schema: str = "NeuroTopologySim.CohortStatisticsReport.v1"
    dataset_id: str | None = None
    condition_a_label: str = "condition_a"
    condition_b_label: str = "condition_b"
    total_subjects_evaluated: int = 0
    is_synthetic: bool = False
    provenance_status: str = ProvenanceStatus.EMPIRICAL.value
    multiplicity_method: str = MultiplicityMethod.HOLM.value
    min_pairs: int = 3
    checksum: str = ""
    metrics: dict[str, MetricCohortStats] = field(default_factory=dict)
    scientific_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema": self.schema,
            "dataset_id": self.dataset_id,
            "condition_a_label": self.condition_a_label,
            "condition_b_label": self.condition_b_label,
            "total_subjects_evaluated": self.total_subjects_evaluated,
            "is_synthetic": self.is_synthetic,
            "provenance_status": self.provenance_status,
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
