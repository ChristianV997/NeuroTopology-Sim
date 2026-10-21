"""Data models and schemas for TDA backend semantic conformance.

Strict invariants:
1. Mathematical comparability is checked before comparing persistence diagrams.
2. If two complexes, filtrations, metrics, or coefficient fields are non-equivalent,
   they are strictly labeled NOT_COMPARABLE.
3. All serialization must produce finite JSON (null for Inf/NaN).
4. Implementation conformance only; no biological or consciousness claims.
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any, Sequence


class FiltrationType(str, enum.Enum):
    """Filtration type defining the simplicial/cell complex construction."""
    VIETORIS_RIPS = "vietoris_rips"
    CUBICAL_SUBLEVEL = "cubical_sublevel"
    ALPHA_COMPLEX = "alpha_complex"
    UNKNOWN = "unknown"


class MetricConvention(str, enum.Enum):
    """Metric or dissimilarity convention defining edge weights or cell values."""
    EUCLIDEAN_POINT_CLOUD = "euclidean_point_cloud"
    PRECOMPUTED_DISTANCE_MATRIX = "precomputed_distance_matrix"
    DISSIMILARITY_ONE_MINUS_PLV = "dissimilarity_1_minus_plv"
    DISSIMILARITY_ONE_MINUS_COHERENCE = "dissimilarity_1_minus_coherence"
    GRID_SCALAR_SUBLEVEL = "grid_scalar_sublevel"
    UNKNOWN = "unknown"


class CoefficientField(str, enum.Enum):
    """Field of coefficients for homology computation."""
    Z2 = "Z2"
    Z3 = "Z3"
    QP = "QP"
    UNKNOWN = "unknown"


class ComparabilityStatus(str, enum.Enum):
    """Outcome of mathematical comparability evaluation."""
    COMPARABLE = "comparable"
    NOT_COMPARABLE = "not_comparable"
    BACKEND_UNAVAILABLE = "backend_unavailable"


class NonComparableReason(str, enum.Enum):
    """Specific reasons why two configurations cannot be mathematically compared."""
    COMPLEX_TYPE_MISMATCH = "complex_type_mismatch"
    FILTRATION_MISMATCH = "filtration_mismatch"
    METRIC_MISMATCH = "metric_convention_mismatch"
    COEFFICIENT_FIELD_MISMATCH = "coefficient_field_mismatch"
    DIMENSION_MISMATCH = "homology_dimension_mismatch"
    THRESHOLD_TRUNCATION_MISMATCH = "threshold_truncation_mismatch"
    INPUT_IDENTITY_MISMATCH = "input_identity_mismatch"
    BACKEND_MISSING = "backend_missing"


def sanitize_float(val: Any) -> float | None:
    """Return float or None if val is NaN, infinite, or None."""
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
class PersistenceBar:
    """A single persistent homology interval [birth, death)."""
    dimension: int
    birth: float
    death: float | None = None

    @property
    def is_infinite(self) -> bool:
        return self.death is None or math.isinf(self.death)

    @property
    def lifetime(self) -> float | None:
        if self.is_infinite or self.death is None:
            return None
        return max(0.0, self.death - self.birth)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": int(self.dimension),
            "birth": sanitize_float(self.birth),
            "death": sanitize_float(self.death),
            "is_infinite": self.is_infinite,
            "lifetime": sanitize_float(self.lifetime),
        }

    @classmethod
    def from_pair(cls, dimension: int, birth: float, death: float | None) -> PersistenceBar:
        d = None if (death is None or math.isinf(death) or (isinstance(death, float) and math.isnan(death))) else float(death)
        return cls(dimension=int(dimension), birth=float(birth), death=d)


@dataclass(frozen=True)
class BackendMetadata:
    """Metadata regarding a TDA backend implementation."""
    backend_id: str
    is_available: bool
    version: str | None = None
    license_type: str = "Unknown"
    supported_filtrations: list[FiltrationType] = field(default_factory=list)
    supported_dimensions: list[int] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "is_available": self.is_available,
            "version": self.version,
            "license_type": self.license_type,
            "supported_filtrations": [f.value for f in self.supported_filtrations],
            "supported_dimensions": self.supported_dimensions,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ConformanceExecutionConfig:
    """Mathematical configuration of a TDA computation."""
    filtration_type: FiltrationType
    metric_convention: MetricConvention
    coefficient_field: CoefficientField = CoefficientField.Z2
    max_dimension: int = 1
    threshold: float | None = None
    tolerance: float = 1e-5
    input_identity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "filtration_type": self.filtration_type.value,
            "metric_convention": self.metric_convention.value,
            "coefficient_field": self.coefficient_field.value,
            "max_dimension": self.max_dimension,
            "threshold": sanitize_float(self.threshold),
            "tolerance": self.tolerance,
            "input_identity": self.input_identity,
        }


@dataclass
class BackendExecutionResult:
    """Result of running a TDA backend on an input fixture."""
    backend_meta: BackendMetadata
    config: ConformanceExecutionConfig
    success: bool
    diagrams: dict[int, list[PersistenceBar]] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    error_message: str | None = None

    def get_bars(self, dimension: int) -> list[PersistenceBar]:
        return self.diagrams.get(dimension, [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend_meta.to_dict(),
            "config": self.config.to_dict(),
            "success": self.success,
            "diagrams": {
                str(dim): [b.to_dict() for b in bars]
                for dim, bars in self.diagrams.items()
            },
            "runtime_seconds": sanitize_float(self.runtime_seconds),
            "error_message": self.error_message,
        }


@dataclass
class ConformanceComparisonResult:
    """Pairwise semantic conformance result between two backends."""
    status: ComparabilityStatus
    is_comparable: bool
    non_comparable_reasons: list[str] = field(default_factory=list)
    dimension: int = 0
    bar_count_a: int = 0
    bar_count_b: int = 0
    bottleneck_distance: float | None = None
    max_bar_coordinate_diff: float | None = None
    passed_tolerance: bool = False
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "is_comparable": self.is_comparable,
            "non_comparable_reasons": self.non_comparable_reasons,
            "dimension": self.dimension,
            "bar_count_a": self.bar_count_a,
            "bar_count_b": self.bar_count_b,
            "bottleneck_distance": sanitize_float(self.bottleneck_distance),
            "max_bar_coordinate_diff": sanitize_float(self.max_bar_coordinate_diff),
            "passed_tolerance": self.passed_tolerance,
            "details": self.details,
        }
