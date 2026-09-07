"""Typed data models and schemas for streaming paired-cohort topology execution.

Strictly separates graph persistent homology from spatial topological charge.
Enforces null-safe, finite serialization, explicit execution states, and
Bayesian/clinical guardrails.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from typing import Any


class ExecutionStatus(str, Enum):
    DESCRIPTIVE_READY = "DESCRIPTIVE_READY"
    INSUFFICIENT_PAIRED_SUBJECTS = "INSUFFICIENT_PAIRED_SUBJECTS"
    INCOMPLETE_PROVENANCE = "INCOMPLETE_PROVENANCE"
    MISSING_OPTIONAL_DEPENDENCY = "MISSING_OPTIONAL_DEPENDENCY"
    INVALID_INPUT = "INVALID_INPUT"
    SYNTHETIC_DEMO_ONLY = "SYNTHETIC_DEMO_ONLY"
    NO_DATA = "NO_DATA"


class RefusalReasonCode(str, Enum):
    NO_DATA = "no_data"
    MALFORMED = "malformed"
    INSUFFICIENT_PAIRS = "insufficient_pairs"
    AMBIGUOUS_LABELS = "ambiguous_labels"
    INCOMPLETE_PROVENANCE = "incomplete_provenance"
    MISSING_DEPENDENCY = "missing_dependency"


@dataclass(frozen=True)
class WindowMetrics:
    channels: int
    samples: int
    is_finite: bool
    h0_intervals_count: int
    h1_intervals_count: int
    beta0_max: int
    beta0_mean: float
    beta1_max: int
    filtration_beta1_max: int
    mean_beta1: float
    integrated_beta1_landscape_area: float
    spatial_phase_charge: float | None
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
    beta0_summary: dict[str, Any]
    beta1_summary: dict[str, Any]
    integrated_beta1_landscape_area_summary: dict[str, Any]
    persistence_interval_counts: dict[str, int]
    spatial_phase_charge_summary: dict[str, Any]
    runtime_seconds: float = 0.0
    memory_telemetry: dict[str, Any] = field(default_factory=dict)

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
    persistence_distance: float | None = None
    delta_landscape_area: float | None = None
    runtime_seconds: float = 0.0
    memory_telemetry: dict[str, Any] = field(default_factory=dict)

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
            "persistence_distance": self.persistence_distance,
            "delta_landscape_area": self.delta_landscape_area,
            "runtime_seconds": self.runtime_seconds,
            "memory_telemetry": self.memory_telemetry,
        })


@dataclass
class CohortTopologyExecutionSummary:
    schema: str = "NeuroTopologySim.CohortTopologyExecutionSummary.v2"
    execution_status: str = ExecutionStatus.NO_DATA.value
    formal_bayes_factor: None = None
    scientific_pass: bool = False
    evidence_class: str = "descriptive_topology_only"
    manifest_path: str = ""
    manifest_status: str | None = None
    provenance_checksum: str = ""
    output_checksum: str = ""
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
    runtime_seconds: float = 0.0
    peak_memory_mb: float | None = None
    memory_telemetry: dict[str, Any] = field(default_factory=dict)
    scientific_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema": self.schema,
            "execution_status": self.execution_status,
            "formal_bayes_factor": self.formal_bayes_factor,
            "scientific_pass": self.scientific_pass,
            "evidence_class": self.evidence_class,
            "manifest_path": self.manifest_path,
            "manifest_status": self.manifest_status,
            "provenance_checksum": self.provenance_checksum,
            "output_checksum": self.output_checksum,
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
            "runtime_seconds": self.runtime_seconds,
            "peak_memory_mb": self.peak_memory_mb,
            "memory_telemetry": self.memory_telemetry,
            "scientific_note": self.scientific_note,
        })


def _safe_dict(val: Any) -> Any:
    """Recursively converts non-finite floats to None and preserves strict JSON types."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): _safe_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_dict(v) for v in val]
    return str(val)
