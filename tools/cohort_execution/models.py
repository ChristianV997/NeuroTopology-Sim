"""Typed data models and schemas for streaming paired-cohort topology execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from typing import Any


class ExecutionStatus(str, Enum):
    REFUSED = "REFUSED"
    VALID_COHORT_PROCESSED = "VALID_COHORT_PROCESSED"
    INSUFFICIENT_PAIRS_PROCESSED = "INSUFFICIENT_PAIRS_PROCESSED"
    SYNTHETIC_EVALUATION = "SYNTHETIC_EVALUATION"
    NO_PAIRS_PROCESSED = "NO_PAIRS_PROCESSED"


class RefusalReasonCode(str, Enum):
    NO_DATA = "no_data"
    MALFORMED = "malformed"
    INSUFFICIENT_PAIRS = "insufficient_pairs"
    AMBIGUOUS_LABELS = "ambiguous_labels"
    INCOMPLETE_PROVENANCE = "incomplete_provenance"


@dataclass(frozen=True)
class WindowMetrics:
    channels: int
    samples: int
    is_finite: bool
    beta1_max: int
    filtration_beta1_max: int
    mean_beta1: float
    integrated_landscape_area: float
    spatial_charge: float | None
    spatial_charge_available: bool


@dataclass
class ConditionStreamSummary:
    file_path: str
    format: str
    checksum: str
    subject: str | None
    session: str | None
    condition: str | None
    is_synthetic: bool
    provenance: dict[str, Any]
    sample_count: int
    channel_count: int
    sampling_rate_hz: float
    windows_processed: int
    finite_value_status: bool
    beta1_summary: dict[str, Any]
    landscape_area_summary: dict[str, Any]
    spatial_charge_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict(asdict(self))


@dataclass
class PairExecutionSummary:
    pair_index: int
    pairing_key: dict[str, str]
    is_synthetic: bool
    status: str
    reason: str | None = None
    finite_value_status: bool = True
    condition_a: ConditionStreamSummary | None = None
    condition_b: ConditionStreamSummary | None = None
    delta_landscape_area: float | None = None
    runtime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "pair_index": self.pair_index,
            "pairing_key": self.pairing_key,
            "is_synthetic": self.is_synthetic,
            "status": self.status,
            "reason": self.reason,
            "finite_value_status": self.finite_value_status,
            "condition_a": self.condition_a.to_dict() if self.condition_a else None,
            "condition_b": self.condition_b.to_dict() if self.condition_b else None,
            "delta_landscape_area": self.delta_landscape_area,
            "runtime_seconds": self.runtime_seconds,
        })


@dataclass
class CohortTopologyExecutionSummary:
    schema: str = "NeuroTopologySim.CohortTopologyExecutionSummary.v1"
    execution_status: str = ExecutionStatus.NO_PAIRS_PROCESSED.value
    manifest_path: str = ""
    manifest_status: str | None = None
    condition_a: str = "condition_a"
    condition_b: str = "condition_b"
    min_pairs_required: int = 2
    total_pairs_in_manifest: int = 0
    pairs_processed: int = 0
    pairs_skipped: int = 0
    empirical_pairs_count: int = 0
    synthetic_pairs_count: int = 0
    refusal_reasons: list[str] = field(default_factory=list)
    processed_pairs: list[dict[str, Any]] = field(default_factory=list)
    skipped_pairs: list[dict[str, Any]] = field(default_factory=list)
    descriptive_aggregate: dict[str, Any] = field(default_factory=dict)
    descriptive_wilcoxon: dict[str, Any] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    peak_memory_mb: float | None = None
    scientific_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema": self.schema,
            "execution_status": self.execution_status,
            "manifest_path": self.manifest_path,
            "manifest_status": self.manifest_status,
            "condition_a": self.condition_a,
            "condition_b": self.condition_b,
            "min_pairs_required": self.min_pairs_required,
            "total_pairs_in_manifest": self.total_pairs_in_manifest,
            "pairs_processed": self.pairs_processed,
            "pairs_skipped": self.pairs_skipped,
            "empirical_pairs_count": self.empirical_pairs_count,
            "synthetic_pairs_count": self.synthetic_pairs_count,
            "refusal_reasons": self.refusal_reasons,
            "processed_pairs": self.processed_pairs,
            "skipped_pairs": self.skipped_pairs,
            "descriptive_aggregate": self.descriptive_aggregate,
            "descriptive_wilcoxon": self.descriptive_wilcoxon,
            "runtime_seconds": self.runtime_seconds,
            "peak_memory_mb": self.peak_memory_mb,
            "scientific_note": self.scientific_note,
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
