"""Data models and schemas for paired-cohort descriptive and inferential statistics."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from typing import Any


class HypothesisAlternative(str, Enum):
    TWO_SIDED = "two-sided"
    GREATER = "greater"
    LESS = "less"


class MultiplicityMethod(str, Enum):
    HOLM = "holm"
    BONFERRONI = "bonferroni"
    FDR_BH = "fdr_bh"
    NONE = "none"


class ProvenanceStatus(str, Enum):
    EMPIRICAL = "empirical"
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    INCOMPLETE = "incomplete_provenance"


@dataclass(frozen=True)
class ExclusionRecord:
    subject: str
    metric: str
    reason: str


@dataclass(frozen=True)
class DescriptiveStats:
    n: int
    mean: float | None
    median: float | None
    variance: float | None
    standard_error: float | None

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass(frozen=True)
class PairedDifferenceStats:
    values: list[float]
    mean: float | None
    median: float | None
    variance: float | None
    standard_error: float | None
    median_difference: float | None
    cohens_d_z: float | None
    ci_95: tuple[float, float] | None

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass(frozen=True)
class InferentialStats:
    test_name: str
    status: str
    statistic: float | None
    p_value: float | None
    p_adjusted: float | None
    alternative: str
    zero_method: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass
class MetricCohortStats:
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
            "exclusion_records": [asdict(e) for e in self.exclusion_records],
            "condition_a_stats": self.condition_a_stats.to_dict(),
            "condition_b_stats": self.condition_b_stats.to_dict(),
            "difference_stats": self.difference_stats.to_dict(),
            "inferential_stats": self.inferential_stats.to_dict(),
        }


@dataclass
class CohortStatisticsReport:
    schema: str = "NeuroTopologySim.CohortStatisticsReport.v1"
    dataset_id: str | None = None
    condition_a_label: str = "condition_a"
    condition_b_label: str = "condition_b"
    total_subjects_evaluated: int = 0
    is_synthetic: bool = False
    provenance_status: str = ProvenanceStatus.EMPIRICAL.value
    multiplicity_method: str = MultiplicityMethod.HOLM.value
    min_pairs: int = 2
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
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): _safe_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_dict(v) for v in val]
    return str(val)
