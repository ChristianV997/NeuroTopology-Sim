"""Deterministic bounded landscapes for static two-hedgehog ansatz energies.

This module composes the public static evaluator over declared separation,
relative-isorotation, and fixed-box grid-refinement axes. Results describe
product-ansatz excess energies only; they are not relaxed potentials, forces,
stability claims, physical predictions, or time evolution.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice
import json
import math
from numbers import Real
import platform
from typing import Any

import numpy as np

from .field import validate_spacing
from .interaction import evaluate_two_hedgehog_interaction

SWEEP_SCHEMA_VERSION = "su2.two_hedgehog_interaction_sweep.v1"
MAX_SWEEP_AXIS_VALUES = 256
MAX_SWEEP_POINTS = 256
MAX_SWEEP_GRID_NODES = 65_536
MAX_SWEEP_NODE_VOLUME = 5_000_000


def _bounded_tuple(values: object, name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a nonempty bounded sequence")
    try:
        items = tuple(islice(iter(values), MAX_SWEEP_AXIS_VALUES + 1))  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"{name} must be a nonempty bounded sequence") from exc
    if not items:
        raise ValueError(f"{name} must not be empty")
    if len(items) > MAX_SWEEP_AXIS_VALUES:
        raise ValueError(f"{name} exceeds the axis limit of {MAX_SWEEP_AXIS_VALUES}")
    return items


def _positive_real(value: object, name: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real scalar")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or (result == 0.0 and not allow_zero):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _real_vector(value: object, name: str, size: int) -> tuple[float, ...]:
    try:
        raw = np.asarray(value, dtype=object)
        if any(isinstance(item, (bool, np.bool_)) for item in raw.flat):
            raise ValueError(f"{name} must not contain booleans")
        numeric = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real vector of length {size}") from exc
    if numeric.shape != (size,) or numeric.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite real vector of length {size}")
    values = numeric.astype(np.float64, copy=False)
    if not np.isfinite(values).all():
        raise ValueError(f"{name} must be finite")
    return tuple(float(item) for item in values)


def _shape3(value: object) -> tuple[int, int, int]:
    if isinstance(value, (str, bytes)):
        raise ValueError("grid shape must contain three integers >= 2")
    try:
        raw = tuple(islice(iter(value), 4))  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError("grid shape must contain three integers >= 2") from exc
    if len(raw) != 3 or any(
        isinstance(item, (bool, np.bool_))
        or not isinstance(item, (int, np.integer))
        or int(item) < 2
        for item in raw
    ):
        raise ValueError("grid shape must contain three integers >= 2")
    return tuple(int(item) for item in raw)


def _separations(values: object) -> tuple[float, ...]:
    result = tuple(
        _positive_real(item, "separation", allow_zero=True)
        for item in _bounded_tuple(values, "separation_values")
    )
    if len(set(result)) != len(result):
        raise ValueError("separation_values must not contain duplicates")
    return result


def _unit_direction(value: object) -> tuple[float, float, float]:
    vector = _real_vector(value, "separation_direction", 3)
    norm = math.hypot(math.hypot(vector[0], vector[1]), vector[2])
    if not math.isfinite(norm) or abs(norm - 1.0) > 1.0e-10:
        raise ValueError("separation_direction must have unit norm")
    return tuple(component / norm for component in vector)


def _canonical_quaternion(value: object) -> tuple[float, float, float, float]:
    raw = _real_vector(value, "relative_isorotation", 4)
    norm = float(np.linalg.norm(raw))
    if not math.isfinite(norm) or abs(norm - 1.0) > 1.0e-10:
        raise ValueError("each relative_isorotation must have unit norm")
    normalized = tuple(float(component / norm) for component in raw)
    first_nonzero = next((component for component in normalized if component != 0.0), 1.0)
    if first_nonzero < 0.0:
        normalized = tuple(-component for component in normalized)
    return normalized


def _orientations(values: object) -> tuple[tuple[float, float, float, float], ...]:
    result = tuple(
        _canonical_quaternion(item)
        for item in _bounded_tuple(values, "relative_isorotations")
    )
    if len(set(result)) != len(result):
        raise ValueError("relative_isorotations must not contain duplicate rotations")
    return result


@dataclass(frozen=True)
class InteractionGridLevel:
    """One fixed-vacuum grid level on the common box used by a sweep."""

    level_id: str
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]

    def __post_init__(self) -> None:
        if not isinstance(self.level_id, str) or not self.level_id.strip():
            raise ValueError("level_id must be a nonempty string")
        shape = _shape3(self.shape)
        spacing = validate_spacing(self.spacing)
        node_count = math.prod(shape)
        if node_count > MAX_SWEEP_GRID_NODES:
            raise ValueError(
                f"grid level exceeds the sweep node limit of {MAX_SWEEP_GRID_NODES}"
            )
        extent = tuple((size - 1) * step for size, step in zip(shape, spacing))
        if not all(math.isfinite(value) and value > 0.0 for value in extent):
            raise ValueError("grid domain extent must be finite and positive")
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "spacing", spacing)

    @property
    def node_count(self) -> int:
        return math.prod(self.shape)

    @property
    def box_extent(self) -> tuple[float, float, float]:
        return tuple(
            (size - 1) * step for size, step in zip(self.shape, self.spacing)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id,
            "shape": list(self.shape),
            "spacing": list(self.spacing),
            "box_extent": list(self.box_extent),
            "node_count": self.node_count,
        }


@dataclass(frozen=True)
class TwoHedgehogSweepSpec:
    """A fixed model and Cartesian axes for a product-ansatz landscape."""

    radius: float
    separation_values: tuple[float, ...]
    relative_isorotations: tuple[tuple[float, float, float, float], ...]
    grid_levels: tuple[InteractionGridLevel, ...]
    separation_direction: tuple[float, float, float] = (1.0, 0.0, 0.0)
    f_pi: float = 1.0
    e: float = 1.0
    code_revision: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _positive_real(self.radius, "radius"))
        object.__setattr__(self, "separation_values", _separations(self.separation_values))
        object.__setattr__(
            self, "relative_isorotations", _orientations(self.relative_isorotations)
        )
        object.__setattr__(self, "separation_direction", _unit_direction(self.separation_direction))
        object.__setattr__(self, "f_pi", _positive_real(self.f_pi, "f_pi"))
        object.__setattr__(self, "e", _positive_real(self.e, "e"))
        levels = _bounded_tuple(self.grid_levels, "grid_levels")
        if any(not isinstance(level, InteractionGridLevel) for level in levels):
            raise ValueError("grid_levels must contain InteractionGridLevel values")
        if len({level.level_id for level in levels}) != len(levels):
            raise ValueError("grid level ids must be unique")
        if self.code_revision is not None and (
            not isinstance(self.code_revision, str) or not self.code_revision.strip()
        ):
            raise ValueError("code_revision must be a nonempty string or None")
        object.__setattr__(self, "grid_levels", levels)
        _validate_spec(self)

    @property
    def lambda_value(self) -> float:
        return self.e * self.f_pi

    @property
    def energy_scale(self) -> float:
        return self.f_pi / self.e

    @property
    def point_count(self) -> int:
        return (
            len(self.separation_values)
            * len(self.relative_isorotations)
            * len(self.grid_levels)
        )

    @property
    def node_volume_work(self) -> int:
        return (
            len(self.separation_values)
            * len(self.relative_isorotations)
            * sum(level.node_count for level in self.grid_levels)
        )

    def to_dict(self) -> dict[str, Any]:
        lambda_value = self.lambda_value
        energy_scale = self.energy_scale
        return {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "radius": self.radius,
            "separation_values": list(self.separation_values),
            "separation_direction": list(self.separation_direction),
            "relative_isorotations": [list(value) for value in self.relative_isorotations],
            "grid_levels": [level.to_dict() for level in self.grid_levels],
            "f_pi": self.f_pi,
            "e": self.e,
            "code_revision": self.code_revision,
            "grid_mode": "fixed_input_grid_per_level",
            "dimensionless_controls": {
                "lambda": lambda_value,
                "E0": energy_scale,
                "rho": lambda_value * self.radius,
                "s_values": [value / self.radius for value in self.separation_values],
            },
            "planned_work": {
                "point_count": self.point_count,
                "max_points": MAX_SWEEP_POINTS,
                "grid_node_volume_units": self.node_volume_work,
                "max_grid_node_volume_units": MAX_SWEEP_NODE_VOLUME,
                "unit_definition": "sum(grid_nodes for each evaluator call)",
                "not_a_wall_time_or_peak_memory_bound": True,
            },
        }


@dataclass(frozen=True)
class TwoHedgehogSweepPoint:
    point_id: str
    separation: float
    separation_vector: tuple[float, float, float]
    relative_isorotation: tuple[float, float, float, float]
    grid_level: InteractionGridLevel
    evaluator_result_json: str
    result_sha256: str

    def __post_init__(self) -> None:
        try:
            payload = json.loads(self.evaluator_result_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("evaluator_result_json must contain valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("evaluator_result_json must encode an object")
        canonical = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        if canonical != self.evaluator_result_json:
            raise ValueError("evaluator_result_json must use canonical finite JSON")
        if _canonical_json_sha256(payload) != self.result_sha256:
            raise ValueError("result_sha256 does not match evaluator_result_json")

    @property
    def evaluator_result(self) -> dict[str, Any]:
        """Return a detached copy so callers cannot stale stored checksums."""
        return json.loads(self.evaluator_result_json)

    def to_dict(self, lambda_value: float) -> dict[str, Any]:
        dimensionless_spacing = tuple(lambda_value * value for value in self.grid_level.spacing)
        dimensionless_extent = tuple(lambda_value * value for value in self.grid_level.box_extent)
        evaluator_result = self.evaluator_result
        metadata = evaluator_result["input_metadata"]
        return {
            "point_id": self.point_id,
            "separation": self.separation,
            "separation_vector": list(self.separation_vector),
            "relative_isorotation": list(self.relative_isorotation),
            "grid_level": self.grid_level.level_id,
            "grid_geometry": {
                **self.grid_level.to_dict(),
                "dimensionless_spacing_h": list(dimensionless_spacing),
                "dimensionless_extent_ell": list(dimensionless_extent),
            },
            "evaluator_input_sha256": evaluator_result["input_sha256"],
            "result_sha256": self.result_sha256,
            "dimensionless_excess_E_over_E0": evaluator_result["excess"]["V_h"],
            "stencil_overlap": evaluator_result["support_stencils_overlap"],
            "evaluator_input_metadata": metadata,
            "evaluator_result": evaluator_result,
        }


@dataclass(frozen=True)
class TwoHedgehogSweepResult:
    sweep_id: str
    spec: TwoHedgehogSweepSpec
    points: tuple[TwoHedgehogSweepPoint, ...]
    python_version: str
    numpy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "sweep_id": self.sweep_id,
            "spec": self.spec.to_dict(),
            "points": [
                point.to_dict(self.spec.lambda_value) for point in self.points
            ],
            "environment": {
                "python_version": self.python_version,
                "numpy_version": self.numpy_version,
            },
            "status": "SYNTHETIC_STATIC_PRODUCT_ANSATZ_LANDSCAPE",
            "evidence_class": "synthetic_static_model",
            "scientific_pass": False,
            "claim_scope": "product_ansatz_excess_energy_landscape_only",
            "not_a_force": True,
            "not_a_relaxed_potential": True,
            "not_a_physical_prediction": True,
            "not_time_evolution": True,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


def _canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value, allow_nan=False, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_spec(spec: TwoHedgehogSweepSpec) -> tuple[int, int]:
    radius = _positive_real(spec.radius, "radius")
    separations = _separations(spec.separation_values)
    orientations = _orientations(spec.relative_isorotations)
    direction = _unit_direction(spec.separation_direction)
    f_pi = _positive_real(spec.f_pi, "f_pi")
    coupling = _positive_real(spec.e, "e")
    levels = _bounded_tuple(spec.grid_levels, "grid_levels")
    if not separations or not orientations or not levels:
        raise ValueError("separation, orientation, and grid axes must be nonempty")
    if any(not isinstance(level, InteractionGridLevel) for level in levels):
        raise ValueError("grid_levels must contain InteractionGridLevel values")
    if len({level.level_id for level in levels}) != len(levels):
        raise ValueError("grid level ids must be unique")
    if not np.allclose(direction, spec.separation_direction, rtol=0.0, atol=1.0e-14):
        raise ValueError("separation direction must be canonical and unit normalized")

    extents = [level.box_extent for level in levels]
    first_extent = np.asarray(extents[0], dtype=np.float64)
    if any(
        not np.allclose(extent, first_extent, rtol=1.0e-12, atol=1.0e-12)
        for extent in extents[1:]
    ):
        raise ValueError("grid refinement levels must preserve the same box extent")

    lambda_value = coupling * f_pi
    energy_scale = f_pi / coupling
    controls = (lambda_value, energy_scale, lambda_value * radius)
    if not all(math.isfinite(value) and value > 0.0 for value in controls):
        raise ValueError("model dimensionless controls must be finite and positive")
    point_count = len(separations) * len(orientations) * len(levels)
    node_volume = len(separations) * len(orientations) * sum(
        level.node_count for level in levels
    )
    if point_count > MAX_SWEEP_POINTS:
        raise ValueError(f"sweep exceeds the point limit of {MAX_SWEEP_POINTS}")
    if node_volume > MAX_SWEEP_NODE_VOLUME:
        raise ValueError(
            "sweep exceeds the grid-node volume limit of "
            f"{MAX_SWEEP_NODE_VOLUME}"
        )
    for separation in separations:
        vector = tuple(separation * component for component in direction)
        distance = math.hypot(math.hypot(vector[0], vector[1]), vector[2])
        if not all(math.isfinite(value) for value in vector) or not math.isfinite(distance):
            raise ValueError("separation vector must remain finite")
        if not math.isfinite(distance / radius):
            raise ValueError("scaled separation must remain finite")
        for level in levels:
            half_extent = tuple(value / 2.0 for value in level.box_extent)
            available = tuple(
                half_extent[axis] - abs(vector[axis]) / 2.0
                for axis in range(3)
            )
            if any(value <= 0.0 or radius >= value for value in available):
                raise ValueError(
                    "both support radii must fit strictly inside every grid face "
                    "for every sweep point"
                )
    for level in levels:
        if any(
            not math.isfinite(lambda_value * value)
            for value in level.spacing + level.box_extent
        ):
            raise ValueError("dimensionless grid geometry must remain finite")
    return point_count, node_volume


def run_two_hedgehog_interaction_sweep(
    spec: TwoHedgehogSweepSpec,
) -> TwoHedgehogSweepResult:
    """Evaluate a fail-fast, bounded product-ansatz excess-energy landscape."""
    if not isinstance(spec, TwoHedgehogSweepSpec):
        raise ValueError("spec must be a TwoHedgehogSweepSpec")
    _validate_spec(spec)

    points: list[TwoHedgehogSweepPoint] = []
    point_index = 0
    for separation in spec.separation_values:
        separation_vector = tuple(
            separation * component for component in spec.separation_direction
        )
        for orientation in spec.relative_isorotations:
            for level in spec.grid_levels:
                result = evaluate_two_hedgehog_interaction(
                    shape=level.shape,
                    spacing=level.spacing,
                    radius=spec.radius,
                    separation_vector=separation_vector,
                    relative_isorotation=orientation,
                    f_pi=spec.f_pi,
                    e=spec.e,
                    code_revision=spec.code_revision,
                ).to_dict()
                result_json = json.dumps(
                    result,
                    allow_nan=False,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                result_sha = _canonical_json_sha256(result)
                points.append(
                    TwoHedgehogSweepPoint(
                        point_id=f"point-{point_index:04d}",
                        separation=separation,
                        separation_vector=separation_vector,
                        relative_isorotation=orientation,
                        grid_level=level,
                        evaluator_result_json=result_json,
                        result_sha256=result_sha,
                    )
                )
                point_index += 1

    spec_dict = spec.to_dict()
    sweep_id = _canonical_json_sha256(
        {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "spec": spec_dict,
            "point_result_sha256": [point.result_sha256 for point in points],
        }
    )
    return TwoHedgehogSweepResult(
        sweep_id=sweep_id,
        spec=spec,
        points=tuple(points),
        python_version=platform.python_version(),
        numpy_version=np.__version__,
    )
