"""Data models and serialization types for TDA backend reproducibility and equivalence auditing.

Strict invariant: All serialization must use allow_nan=False with explicit null values for NaN/Inf.
Strict invariant: Graph beta_1 cycle counts must remain separate from spatial phase charge.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence


class BackendId(str, enum.Enum):
    RIPSER = "ripser"
    GUDHI = "gudhi"
    GTDA = "gtda"
    RIPSERPLUSPLUS = "ripserplusplus"
    FALLBACK = "fallback"


class BackendStatus(str, enum.Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    DISABLED_OFFLINE = "disabled_offline"
    ERROR = "error"


class OutputNature(str, enum.Enum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    FIXTURE_ONLY = "fixture_only"


class AgreementStatus(str, enum.Enum):
    FULL_AGREEMENT = "full_agreement"
    DISAGREEMENT = "disagreement"
    SINGLE_BACKEND = "single_backend"
    NO_BACKENDS_AVAILABLE = "no_backends_available"


class InvariantName(str, enum.Enum):
    DISTANCE_MATRIX_SYMMETRY = "distance_matrix_symmetry"
    ZERO_DIAGONAL = "zero_diagonal"
    FINITE_INTERVALS = "finite_intervals"
    NODE_REORDERING_INVARIANCE = "node_reordering_invariance"
    BOUNDED_POINT_CAPACITY = "bounded_point_capacity"
    SPATIAL_CHARGE_ISOLATION = "spatial_charge_isolation"
    DETERMINISTIC_REPEATED_CHECKSUM = "deterministic_repeated_checksum"


def sanitize_float(val: Any) -> float | None:
    """Return float or None if val is NaN, infinite, or None. Never returns NaN or Inf."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PersistenceInterval:
    dimension: int
    birth: float
    death: float | None = None
    persistence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", int(self.dimension))
        object.__setattr__(self, "birth", float(self.birth))
        if self.death is not None:
            object.__setattr__(self, "death", float(self.death))
        if self.persistence is not None:
            object.__setattr__(self, "persistence", float(self.persistence))
        elif self.death is not None:
            object.__setattr__(self, "persistence", max(0.0, float(self.death) - float(self.birth)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "birth": sanitize_float(self.birth),
            "death": sanitize_float(self.death),
            "persistence": sanitize_float(self.persistence),
        }


@dataclass(frozen=True)
class BackendProbeReport:
    backend_id: str
    status: str
    is_available: bool
    version: str | None = None
    max_dimension_supported: int = 1
    supports_distance_matrix: bool = True
    supports_point_cloud: bool = True
    is_exact: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "status": self.status,
            "is_available": self.is_available,
            "version": self.version,
            "max_dimension_supported": self.max_dimension_supported,
            "supports_distance_matrix": self.supports_distance_matrix,
            "supports_point_cloud": self.supports_point_cloud,
            "is_exact": self.is_exact,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExecutionTelemetry:
    runtime_seconds: float
    peak_memory_delta_mb: float | None = None
    input_shape: list[int] = field(default_factory=list)
    point_count: int = 0
    max_dimension: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_seconds": sanitize_float(self.runtime_seconds),
            "peak_memory_delta_mb": sanitize_float(self.peak_memory_delta_mb),
            "input_shape": self.input_shape,
            "point_count": self.point_count,
            "max_dimension": self.max_dimension,
        }


@dataclass
class BackendExecutionResult:
    backend_id: str
    success: bool
    nature: str
    telemetry: ExecutionTelemetry
    diagrams: dict[int, list[PersistenceInterval]] = field(default_factory=dict)
    deterministic_checksum: str = ""
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        serialized_diagrams = {
            str(dim): [iv.to_dict() for iv in intervals]
            for dim, intervals in self.diagrams.items()
        }
        return {
            "backend_id": self.backend_id,
            "success": self.success,
            "nature": self.nature,
            "telemetry": self.telemetry.to_dict(),
            "diagrams": serialized_diagrams,
            "deterministic_checksum": self.deterministic_checksum,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class InvariantCheckResult:
    invariant_name: str
    passed: bool
    details: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        clean_metrics = {}
        for k, v in self.metrics.items():
            if isinstance(v, (int, bool, str)):
                clean_metrics[k] = v
            else:
                clean_metrics[k] = sanitize_float(v)
        return {
            "invariant_name": self.invariant_name,
            "passed": self.passed,
            "details": self.details,
            "metrics": clean_metrics,
        }


@dataclass(frozen=True)
class EquivalenceComparison:
    backend_a: str
    backend_b: str
    dimension: int
    equivalent: bool
    bottleneck_distance: float | None = None
    wasserstein_distance: float | None = None
    max_interval_diff: float | None = None
    interval_count_a: int = 0
    interval_count_b: int = 0
    disagreement_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_a": self.backend_a,
            "backend_b": self.backend_b,
            "dimension": self.dimension,
            "equivalent": self.equivalent,
            "bottleneck_distance": sanitize_float(self.bottleneck_distance),
            "wasserstein_distance": sanitize_float(self.wasserstein_distance),
            "max_interval_diff": sanitize_float(self.max_interval_diff),
            "interval_count_a": self.interval_count_a,
            "interval_count_b": self.interval_count_b,
            "disagreement_reason": self.disagreement_reason,
        }


@dataclass
class FixtureAuditResult:
    fixture_id: str
    fixture_description: str
    num_points: int
    dimension: int
    backend_results: dict[str, BackendExecutionResult] = field(default_factory=dict)
    invariant_checks: list[InvariantCheckResult] = field(default_factory=list)
    pairwise_comparisons: list[EquivalenceComparison] = field(default_factory=list)
    overall_agreement: str = AgreementStatus.NO_BACKENDS_AVAILABLE.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "fixture_description": self.fixture_description,
            "num_points": self.num_points,
            "dimension": self.dimension,
            "backend_results": {
                k: v.to_dict() for k, v in self.backend_results.items()
            },
            "invariant_checks": [c.to_dict() for c in self.invariant_checks],
            "pairwise_comparisons": [p.to_dict() for p in self.pairwise_comparisons],
            "overall_agreement": self.overall_agreement,
            "notes": self.notes,
        }


@dataclass
class AuditReport:
    schema_version: str
    created_at_utc: str
    python_version: str
    platform: str
    probes: list[BackendProbeReport]
    fixture_results: list[FixtureAuditResult]
    summary_counts: dict[str, Any]
    all_invariants_passed: bool
    spatial_charge_isolation_confirmed: bool
    scientific_disclaimer: str
    provenance_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "python_version": self.python_version,
            "platform": self.platform,
            "probes": [p.to_dict() for p in self.probes],
            "fixture_results": [f.to_dict() for f in self.fixture_results],
            "summary_counts": self.summary_counts,
            "all_invariants_passed": self.all_invariants_passed,
            "spatial_charge_isolation_confirmed": self.spatial_charge_isolation_confirmed,
            "scientific_disclaimer": self.scientific_disclaimer,
            "provenance_hash": self.provenance_hash,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Strict null-safe JSON serialization. Will error if NaN or Inf are emitted."""
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)


def compute_diagram_checksum(intervals: Sequence[PersistenceInterval], dimension: int) -> str:
    """Compute deterministic SHA-256 checksum over canonically sorted persistence intervals."""
    def fmt(iv: PersistenceInterval) -> str:
        b = f"{round(iv.birth, 8):.8f}"
        d = f"{round(iv.death, 8):.8f}" if iv.death is not None else "inf"
        return f"{iv.dimension}:{b}:{d}"

    sorted_entries = sorted(fmt(iv) for iv in intervals if iv.dimension == dimension)
    payload = f"dim={dimension}|intervals=[{','.join(sorted_entries)}]"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
