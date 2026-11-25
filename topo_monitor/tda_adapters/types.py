"""Type definitions, enums, dataclasses, and serialization for TDA adapters.

Guarantees:
- Strict typing.
- Null serialization (no NaN or Infinity in output payloads).
- Deterministic SHA-256 checksums over canonical representation.
- Explicit scientific status separation.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np


class BackendName(str, enum.Enum):
    RIPSER = "ripser"
    RIPSER_PLUS_PLUS = "ripserplusplus"
    GUDHI = "gudhi"
    GIOTTO_TDA = "giotto-tda"
    FALLBACK = "deterministic-fallback"


class BackendCapabilityStatus(str, enum.Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    DISABLED_OFFLINE = "disabled_offline"
    FAILED = "failed"


class InputKind(str, enum.Enum):
    POINT_CLOUD = "point_cloud"
    DISTANCE_MATRIX = "distance_matrix"


class ScientificStatus(str, enum.Enum):
    STRICT_COHOMOLOGY = "strict_cohomology"
    APPROXIMATE_FIXTURE_ONLY = "approximate_fixture_only"
    BOUNDED_WINDOW_STREAMING = "bounded_window_streaming"


def sanitize_float(val: Any) -> float | None:
    """Return None if val is NaN, infinite, or None, else float."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def sanitize_value(val: Any) -> Any:
    """Recursively convert NaN, Inf, and numpy types to standard JSON-safe null/primitives."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, dict):
        return {str(k): sanitize_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [sanitize_value(v) for v in val]
    return val


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
class PersistencePair:
    dimension: int
    birth: float
    death: float | None = None
    birth_simplex: tuple[int, ...] | None = None
    death_simplex: tuple[int, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "birth": sanitize_float(self.birth),
            "death": sanitize_float(self.death),
            "birth_simplex": list(self.birth_simplex) if self.birth_simplex is not None else None,
            "death_simplex": list(self.death_simplex) if self.death_simplex is not None else None,
        }


@dataclass(frozen=True)
class BackendCapability:
    name: str
    status: BackendCapabilityStatus
    description: str
    supported_inputs: list[InputKind] = field(default_factory=lambda: [InputKind.POINT_CLOUD, InputKind.DISTANCE_MATRIX])
    max_dimension_supported: int = 1
    supports_exact_pairs: bool = False
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "description": self.description,
            "supported_inputs": [k.value for k in self.supported_inputs],
            "max_dimension_supported": self.max_dimension_supported,
            "supports_exact_pairs": self.supports_exact_pairs,
            "details": self.details,
        }


@dataclass(frozen=True)
class TDAConfig:
    max_edge_length: float | None = None
    max_dimension: int = 1
    compute_pairs: bool = True
    compute_landscape: bool = True
    landscape_layers: int = 5
    landscape_resolution: int = 101
    track_memory: bool = True
    node_order: list[int] | None = None

    def __post_init__(self) -> None:
        if self.max_edge_length is not None:
            if not np.isfinite(self.max_edge_length) or self.max_edge_length < 0.0:
                raise ValueError(f"max_edge_length must be finite and non-negative, got {self.max_edge_length}")
        if self.max_dimension < 0:
            raise ValueError(f"max_dimension must be >= 0, got {self.max_dimension}")
        if self.landscape_layers < 1:
            raise ValueError(f"landscape_layers must be >= 1, got {self.landscape_layers}")
        if self.landscape_resolution < 2:
            raise ValueError(f"landscape_resolution must be >= 2, got {self.landscape_resolution}")


def compute_deterministic_checksum(
    backend: str,
    filtration_range: tuple[float, float | None],
    beta_0_intervals: Sequence[PersistenceInterval],
    beta_1_intervals: Sequence[PersistenceInterval],
    input_kind: str,
    num_points: int,
    landscape_area: float | None = None,
) -> str:
    """Compute a reproducible SHA-256 digest over canonicalized TDA outputs."""
    def fmt_interval(iv: PersistenceInterval) -> str:
        b = f"{round(iv.birth, 6):.6f}"
        d = f"{round(iv.death, 6):.6f}" if iv.death is not None else "null"
        return f"{iv.dimension}:{b}:{d}"

    b0_str = ",".join(sorted(fmt_interval(iv) for iv in beta_0_intervals))
    b1_str = ",".join(sorted(fmt_interval(iv) for iv in beta_1_intervals))
    filt_min = f"{round(filtration_range[0], 6):.6f}"
    filt_max = f"{round(filtration_range[1], 6):.6f}" if filtration_range[1] is not None else "null"
    area_str = f"{round(landscape_area, 6):.6f}" if landscape_area is not None else "null"

    payload = f"backend={backend}|filt=[{filt_min},{filt_max}]|b0=[{b0_str}]|b1=[{b1_str}]|kind={input_kind}|n={num_points}|area={area_str}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class TDAPersistenceResult:
    beta_0_intervals: list[PersistenceInterval]
    beta_1_intervals: list[PersistenceInterval]
    persistence_pairs: list[PersistencePair]
    filtration_range: tuple[float, float | None]
    backend: str
    runtime_seconds: float
    memory_telemetry_bytes: int | None
    deterministic_checksum: str
    scientific_status: ScientificStatus
    input_kind: InputKind
    num_points: int
    landscape: list[list[float]] | None = None
    landscape_grid: list[float] | None = None
    landscape_integrated_area: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to a dictionary, ensuring all NaN/Inf values are null."""
        clean_landscape = None
        if self.landscape is not None:
            clean_landscape = [[sanitize_float(v) for v in row] for row in self.landscape]

        clean_grid = None
        if self.landscape_grid is not None:
            clean_grid = [sanitize_float(v) for v in self.landscape_grid]

        return {
            "beta_0_intervals": [iv.to_dict() for iv in self.beta_0_intervals],
            "beta_1_intervals": [iv.to_dict() for iv in self.beta_1_intervals],
            "persistence_pairs": [p.to_dict() for p in self.persistence_pairs],
            "filtration_range": [
                sanitize_float(self.filtration_range[0]),
                sanitize_float(self.filtration_range[1]),
            ],
            "backend": self.backend,
            "runtime_seconds": sanitize_float(self.runtime_seconds),
            "memory_telemetry_bytes": self.memory_telemetry_bytes,
            "deterministic_checksum": self.deterministic_checksum,
            "scientific_status": self.scientific_status.value,
            "input_kind": self.input_kind.value,
            "num_points": self.num_points,
            "landscape": clean_landscape,
            "landscape_grid": clean_grid,
            "landscape_integrated_area": sanitize_float(self.landscape_integrated_area),
            "metadata": sanitize_value(self.metadata) or {},
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Return JSON string with null representation instead of NaN/Infinity."""
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)


@dataclass(frozen=True)
class StreamingWindowConfig:
    window_size: int = 32
    step_size: int = 16
    max_allowed_points_per_window: int = 256
    backend: str | None = None
    max_edge_length: float | None = None


@dataclass
class StreamingTDAResult:
    window_results: list[TDAPersistenceResult]
    window_ranges: list[tuple[int, int]]
    mean_beta_0_count: float
    mean_beta_1_count: float
    max_beta_1_count: int
    peak_memory_bytes: int | None
    total_runtime_seconds: float
    deterministic_checksum: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_count": len(self.window_results),
            "window_ranges": self.window_ranges,
            "mean_beta_0_count": sanitize_float(self.mean_beta_0_count),
            "mean_beta_1_count": sanitize_float(self.mean_beta_1_count),
            "max_beta_1_count": self.max_beta_1_count,
            "peak_memory_bytes": self.peak_memory_bytes,
            "total_runtime_seconds": sanitize_float(self.total_runtime_seconds),
            "deterministic_checksum": self.deterministic_checksum,
            "window_results": [w.to_dict() for w in self.window_results],
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)
