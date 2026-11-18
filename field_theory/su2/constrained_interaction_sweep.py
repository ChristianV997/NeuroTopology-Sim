"""Bounded grid/anchor sensitivity studies for constrained SU(2) relaxation.

This module is deliberately separate from the static product-ansatz
interaction sweep. Each point delegates to the constrained pair-versus-two-
isolated relaxation and therefore reports a conditional finite-grid excess,
not a force, binding energy, physical time evolution, or continuum limit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import platform
import re
from numbers import Integral, Real
from typing import Literal, Sequence

import numpy as np

from .field import validate_spacing
from .constrained_interaction import (
    NumericalPreflightError,
    _MAX_BACKTRACKS,
    _MAX_ESTIMATED_NODE_VISITS,
    _MAX_GRID_NODES,
    _MAX_ITERATIONS,
    run_constrained_two_hedgehog_relaxation,
    serialize_constrained_result,
)


SWEEP_SCHEMA_VERSION = "su2.constrained_interaction_sensitivity.v1"
MAX_SWEEP_CASES = 16
MAX_SWEEP_ESTIMATED_NODE_VISITS = 100_000_000
_METRICS = {"euclidean", "continuum_l2"}
_EXPECTED_CASE_PREFLIGHT_REJECTIONS = {
    "each anchor patch must contain sampled grid sites": "anchor_sampling",
    "anchor pion vectors do not span two non-collinear directions": "anchor_identifiability",
    "anchor pion vectors have insufficient nonzero magnitude": "anchor_identifiability",
    "pair and isolated initial anchor patches disagree beyond tolerance": "initial_anchor_match",
    "pair and isolated initial anchor mismatch must be finite": "initial_anchor_match",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _finite_real(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real numeric scalar")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return number


def _integer(
    value: object, name: str, *, minimum: int, maximum: int
) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _sequence(value: object, name: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a nonempty sequence")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"{name} must be a nonempty sequence") from exc
    if not items:
        raise ValueError(f"{name} must be a nonempty sequence")
    return items


def _real_vector(value: object, name: str, length: int) -> tuple[float, ...]:
    items = _sequence(value, name)
    if len(items) != length:
        raise ValueError(f"{name} must contain {length} values")
    return tuple(_finite_real(item, name) for item in items)


def _unit_quaternion(value: object) -> tuple[float, float, float, float]:
    raw = _real_vector(value, "relative_isorotation", 4)
    scale = max(abs(component) for component in raw)
    norm = 0.0 if scale == 0.0 else scale * math.hypot(
        math.hypot(raw[0] / scale, raw[1] / scale),
        math.hypot(raw[2] / scale, raw[3] / scale),
    )
    if not math.isfinite(norm) or abs(norm - 1.0) > 1.0e-10:
        raise ValueError("relative_isorotation must have unit norm")
    return tuple(component / norm for component in raw)  # type: ignore[return-value]


def _grid_shape(value: object) -> tuple[int, int, int]:
    items = _sequence(value, "shape")
    if len(items) != 3 or any(
        isinstance(item, bool) or not isinstance(item, Integral) or int(item) < 5
        for item in items
    ):
        raise ValueError("shape must contain three integers >= 5")
    shape = tuple(int(item) for item in items)
    node_count = math.prod(shape)
    if node_count > _MAX_GRID_NODES:
        raise ValueError(f"grid exceeds the {_MAX_GRID_NODES}-node limit")
    return shape  # type: ignore[return-value]


@dataclass(frozen=True)
class ConstrainedSensitivityGridLevel:
    """One fixed-vacuum mesh in a common physical box."""

    level_id: str
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]

    def __post_init__(self) -> None:
        if not isinstance(self.level_id, str) or not self.level_id.strip():
            raise ValueError("level_id must be a nonempty string")
        shape = _grid_shape(self.shape)
        spacing = validate_spacing(self.spacing)
        cell_volume = spacing[0] * spacing[1] * spacing[2]
        extent = tuple(
            (size - 1) * step for size, step in zip(shape, spacing)
        )
        if (
            not math.isfinite(cell_volume)
            or cell_volume <= 0.0
            or not all(math.isfinite(value) and value > 0.0 for value in extent)
        ):
            raise ValueError("grid geometry must be finite and representable")
        object.__setattr__(self, "shape", shape)
        object.__setattr__(self, "spacing", tuple(float(x) for x in spacing))

    @property
    def node_count(self) -> int:
        return math.prod(self.shape)

    @property
    def box_extent(self) -> tuple[float, float, float]:
        return tuple(
            (size - 1) * step for size, step in zip(self.shape, self.spacing)
        )

    @property
    def cell_volume(self) -> float:
        return math.prod(self.spacing)

    def to_dict(self) -> dict[str, object]:
        return {
            "level_id": self.level_id,
            "shape": list(self.shape),
            "spacing": list(self.spacing),
            "box_extent": list(self.box_extent),
            "node_count": self.node_count,
            "cell_volume": self.cell_volume,
        }


@dataclass(frozen=True)
class ConstrainedInteractionSensitivitySpec:
    """Predeclared Cartesian product of mesh levels and frozen-anchor radii."""

    radius: float
    separation_vector: tuple[float, float, float]
    relative_isorotation: tuple[float, float, float, float]
    grid_levels: tuple[ConstrainedSensitivityGridLevel, ...]
    anchor_radii: tuple[float, ...]
    code_revision: str
    f_pi: float = 1.0
    e: float = 1.0
    max_iterations: int = 40
    initial_step: float = 1.0e-3
    gradient_tolerance: float = 1.0e-7
    max_backtracks: int = 8
    orientation_tolerance_rad: float = 1.0e-6
    orientation_residual_tolerance: float = 1.0e-8
    charge_drift_tolerance: float = 0.25
    stationarity_metric: Literal["euclidean", "continuum_l2"] = "continuum_l2"
    descent_metric: Literal["euclidean", "continuum_l2"] = "continuum_l2"

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _finite_real(self.radius, "radius", positive=True))
        object.__setattr__(
            self,
            "separation_vector",
            _real_vector(self.separation_vector, "separation_vector", 3),
        )
        object.__setattr__(
            self, "relative_isorotation", _unit_quaternion(self.relative_isorotation)
        )
        levels = _sequence(self.grid_levels, "grid_levels")
        if any(not isinstance(level, ConstrainedSensitivityGridLevel) for level in levels):
            raise ValueError(
                "grid_levels must contain ConstrainedSensitivityGridLevel values"
            )
        if len({level.level_id for level in levels}) != len(levels):
            raise ValueError("grid level ids must be unique")
        object.__setattr__(self, "grid_levels", levels)

        anchors = tuple(
            _finite_real(value, "anchor_radius", positive=True)
            for value in _sequence(self.anchor_radii, "anchor_radii")
        )
        if len(set(anchors)) != len(anchors):
            raise ValueError("anchor_radii must not contain duplicates")
        if any(value >= self.radius for value in anchors):
            raise ValueError("each anchor_radius must be smaller than radius")
        object.__setattr__(self, "anchor_radii", anchors)

        for name in ("f_pi", "e", "initial_step", "gradient_tolerance",
                     "orientation_tolerance_rad", "orientation_residual_tolerance",
                     "charge_drift_tolerance"):
            object.__setattr__(
                self, name, _finite_real(getattr(self, name), name, positive=True)
            )
        object.__setattr__(
            self,
            "max_iterations",
            _integer(
                self.max_iterations,
                "max_iterations",
                minimum=1,
                maximum=_MAX_ITERATIONS,
            ),
        )
        object.__setattr__(
            self,
            "max_backtracks",
            _integer(
                self.max_backtracks,
                "max_backtracks",
                minimum=0,
                maximum=_MAX_BACKTRACKS,
            ),
        )
        for name in ("stationarity_metric", "descent_metric"):
            metric = getattr(self, name)
            if not isinstance(metric, str) or metric not in _METRICS:
                raise ValueError(
                    f"{name} must be 'euclidean' or 'continuum_l2'"
                )
        if not isinstance(self.code_revision, str) or re.fullmatch(
            r"[0-9a-fA-F]{40}", self.code_revision
        ) is None:
            raise ValueError("code_revision must be a full 40-character commit SHA")
        self._validate_geometry_and_work()

    @property
    def point_count(self) -> int:
        return len(self.grid_levels) * len(self.anchor_radii)

    @property
    def separation(self) -> float:
        x, y, z = self.separation_vector
        return math.hypot(math.hypot(x, y), z)

    def _estimated_visits(self, level: ConstrainedSensitivityGridLevel) -> int:
        return 3 * level.node_count * (
            1 + self.max_iterations * (self.max_backtracks + 2) + 40
        )

    @property
    def planned_estimated_node_visits(self) -> int:
        return sum(
            self._estimated_visits(level) * len(self.anchor_radii)
            for level in self.grid_levels
        )

    def _validate_geometry_and_work(self) -> None:
        if self.separation <= 0.0:
            raise ValueError("separation_vector must be nonzero")
        if self.point_count > MAX_SWEEP_CASES:
            raise ValueError(f"sweep exceeds the {MAX_SWEEP_CASES}-case limit")

        reference_extent = self.grid_levels[0].box_extent
        for level in self.grid_levels:
            if any(
                not math.isclose(value, reference, rel_tol=1.0e-12, abs_tol=1.0e-12)
                for value, reference in zip(level.box_extent, reference_extent)
            ):
                raise ValueError("all grid levels must have the same box extent")
            estimated = self._estimated_visits(level)
            if estimated > _MAX_ESTIMATED_NODE_VISITS:
                raise ValueError(
                    "a sweep point exceeds the constrained-run node-visit limit"
                )

            margin = max(level.spacing)
            half_extents = tuple(value / 2.0 for value in level.box_extent)
            for anchor_radius in self.anchor_radii:
                if self.separation <= 2.0 * anchor_radius + 2.0 * margin:
                    raise ValueError(
                        "anchor patches must not overlap within the stencil margin"
                    )
                if self.separation <= self.radius + anchor_radius + margin:
                    raise ValueError(
                        "each anchor patch must clear the opposite core support and stencil"
                    )
                centers = tuple(
                    tuple(sign * component / 2.0 for component in self.separation_vector)
                    for sign in (-1.0, 1.0)
                )
                for center in centers:
                    available = tuple(
                        half_extents[axis] - abs(center[axis])
                        for axis in range(3)
                    )
                    if any(value <= self.radius + margin for value in available):
                        raise ValueError(
                            "core supports must clear the box boundary by a stencil margin"
                        )
                    if any(value <= anchor_radius + margin for value in available):
                        raise ValueError(
                            "anchor patches must clear the box boundary by a stencil margin"
                        )

        if self.planned_estimated_node_visits > MAX_SWEEP_ESTIMATED_NODE_VISITS:
            raise ValueError(
                "sweep exceeds the aggregate estimated node-visit budget of "
                f"{MAX_SWEEP_ESTIMATED_NODE_VISITS}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "code_revision": self.code_revision.lower(),
            "data_mode": "synthetic_only",
            "randomness": "none_deterministic",
            "radius": self.radius,
            "separation_vector": list(self.separation_vector),
            "separation": self.separation,
            "relative_isorotation": list(self.relative_isorotation),
            "grid_levels": [level.to_dict() for level in self.grid_levels],
            "anchor_radii": list(self.anchor_radii),
            "f_pi": self.f_pi,
            "e": self.e,
            "solver": "nearest_neighbor_forward_link_v2",
            "max_iterations_per_run": self.max_iterations,
            "initial_step": self.initial_step,
            "gradient_tolerance": self.gradient_tolerance,
            "max_backtracks_per_iteration": self.max_backtracks,
            "orientation_tolerance_rad": self.orientation_tolerance_rad,
            "orientation_residual_tolerance": self.orientation_residual_tolerance,
            "charge_drift_tolerance": self.charge_drift_tolerance,
            "stationarity_metric": self.stationarity_metric,
            "descent_metric": self.descent_metric,
            "fixed_box_extent": list(self.grid_levels[0].box_extent),
            "planned_work": {
                "case_count": self.point_count,
                "estimated_node_visits": self.planned_estimated_node_visits,
                "max_case_estimated_node_visits": max(
                    self._estimated_visits(level) for level in self.grid_levels
                ),
                "max_sweep_estimated_node_visits": MAX_SWEEP_ESTIMATED_NODE_VISITS,
                "max_case_node_visits": _MAX_ESTIMATED_NODE_VISITS,
                "unit_definition": (
                    "3*N*(1+iterations*(backtracks+2)+40), summed over all cases"
                ),
                "not_a_wall_time_or_peak_memory_bound": True,
            },
            "claim_scope": (
                "finite-grid, finite-box pair-minus-isolated excess conditional "
                "on the declared frozen anchor patches"
            ),
            "not_a_binding_energy": True,
            "not_a_force": True,
            "not_a_continuum_limit": True,
            "not_physical_time_evolution": True,
        }


def recommended_constrained_sensitivity_spec(
    code_revision: str,
) -> ConstrainedInteractionSensitivitySpec:
    """Return the predeclared six-point same-box grid/anchor design."""
    return ConstrainedInteractionSensitivitySpec(
        radius=2.5,
        separation_vector=(6.5, 0.0, 0.0),
        relative_isorotation=(1.0, 0.0, 0.0, 0.0),
        grid_levels=(
            ConstrainedSensitivityGridLevel("n15", (15, 15, 15), (1.0, 1.0, 1.0)),
            ConstrainedSensitivityGridLevel("n21", (21, 21, 21), (0.7, 0.7, 0.7)),
            ConstrainedSensitivityGridLevel("n29", (29, 29, 29), (0.5, 0.5, 0.5)),
        ),
        anchor_radii=(1.5, 2.0),
        code_revision=code_revision,
        f_pi=1.0,
        e=1.0,
        max_iterations=40,
        initial_step=1.0e-3,
        gradient_tolerance=1.0e-7,
        max_backtracks=8,
        stationarity_metric="continuum_l2",
        descent_metric="continuum_l2",
    )


def _case_digest(record: dict[str, object]) -> str:
    return _sha256({key: value for key, value in record.items() if key != "case_sha256"})


def _anchor_sensitivity_summary(
    levels: Sequence[ConstrainedSensitivityGridLevel],
    anchor_radii: Sequence[float],
    cases: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    summary = []
    index = 0
    for level in levels:
        level_cases = list(cases[index : index + len(anchor_radii)])
        index += len(anchor_radii)
        values = [
            case["final_pair_minus_isolated_energy"]
            for case in level_cases
            if case["comparison_available"]
        ]
        all_comparisons_available = (
            len(values) == len(anchor_radii)
            and all(isinstance(value, Real) and math.isfinite(float(value)) for value in values)
        )
        spread_assessed = all_comparisons_available and len(anchor_radii) >= 2
        if spread_assessed:
            numeric = [float(value) for value in values]
            low, high = min(numeric), max(numeric)
            if all(value > 0.0 for value in numeric):
                sign = "all_positive"
            elif all(value < 0.0 for value in numeric):
                sign = "all_negative"
            elif all(value == 0.0 for value in numeric):
                sign = "all_zero"
            else:
                sign = "mixed_or_includes_zero"
            spread = high - low
        else:
            low = high = spread = None
            sign = (
                "not_assessed_single_anchor"
                if all_comparisons_available and len(anchor_radii) < 2
                else "unavailable"
            )
        summary.append(
            {
                "level_id": level.level_id,
                "spacing": list(level.spacing),
                "anchor_radius_count": len(anchor_radii),
                "all_anchor_comparisons_available": all_comparisons_available,
                "anchor_spread_assessed": spread_assessed,
                "minimum_excess": low,
                "maximum_excess": high,
                "anchor_spread": spread,
                "sign_stability": sign,
                "interpretation": "descriptive_sensitivity_not_uncertainty",
            }
        )
    return summary


@dataclass(frozen=True)
class ConstrainedInteractionSensitivityResult:
    """Immutable serialized sensitivity output with finite canonical JSON."""

    _canonical_json_text: str

    def to_json(self) -> str:
        return self._canonical_json_text

    def to_dict(self) -> dict[str, object]:
        return json.loads(self._canonical_json_text)


def run_constrained_interaction_sensitivity_sweep(
    spec: ConstrainedInteractionSensitivitySpec,
) -> ConstrainedInteractionSensitivityResult:
    """Run every prevalidated mesh/anchor point serially and retain failures."""
    if not isinstance(spec, ConstrainedInteractionSensitivitySpec):
        raise ValueError("spec must be a ConstrainedInteractionSensitivitySpec")

    cases: list[dict[str, object]] = []
    case_index = 0
    for level in spec.grid_levels:
        for anchor_radius in spec.anchor_radii:
            case_input: dict[str, object] = {
                "case_index": case_index,
                "grid_level": level.to_dict(),
                "anchor_radius": anchor_radius,
            }
            common = {
                "shape": level.shape,
                "spacing": level.spacing,
                "radius": spec.radius,
                "separation_vector": spec.separation_vector,
                "relative_isorotation": spec.relative_isorotation,
                "anchor_radius": anchor_radius,
                "code_revision": spec.code_revision,
                "f_pi": spec.f_pi,
                "e": spec.e,
                "max_iterations": spec.max_iterations,
                "initial_step": spec.initial_step,
                "gradient_tolerance": spec.gradient_tolerance,
                "max_backtracks": spec.max_backtracks,
                "orientation_tolerance_rad": spec.orientation_tolerance_rad,
                "orientation_residual_tolerance": spec.orientation_residual_tolerance,
                "charge_drift_tolerance": spec.charge_drift_tolerance,
                "stationarity_metric": spec.stationarity_metric,
                "descent_metric": spec.descent_metric,
            }
            try:
                single_result = run_constrained_two_hedgehog_relaxation(**common)
                single_json = serialize_constrained_result(single_result)
                single_record = json.loads(single_json)
                comparison = single_record.get("comparison")
                if not isinstance(comparison, dict):
                    raise ValueError("single-run result is missing comparison metadata")
                comparison_available = comparison.get(
                    "available_only_if_all_three_converged_and_constraints_pass"
                )
                if not isinstance(comparison_available, bool):
                    raise ValueError("single-run comparison availability must be boolean")
                excess = comparison.get("final_pair_minus_isolated_energy")
                if comparison_available:
                    excess = _finite_real(excess, "final pair-minus-isolated energy")
                elif excess is not None:
                    raise ValueError(
                        "withheld single-run comparison must have a null final excess"
                    )
                status = str(single_record.get("status"))
                failure = None
            except NumericalPreflightError as exc:
                single_record = None
                comparison_available = False
                excess = None
                status = "NUMERICAL_PREFLIGHT_FAILURE"
                failure = {
                    "category": "numerical_preflight_failure",
                    "stage": exc.stage,
                    "failure_class": exc.failure_class,
                    "message": str(exc),
                }
            except ValueError as exc:
                stage = _EXPECTED_CASE_PREFLIGHT_REJECTIONS.get(str(exc))
                if stage is None:
                    raise
                single_record = None
                comparison_available = False
                excess = None
                status = "CASE_PREFLIGHT_REJECTED"
                failure = {
                    "category": "case_input_preflight_rejection",
                    "stage": stage,
                    "failure_class": type(exc).__name__,
                    "message": str(exc),
                }

            case: dict[str, object] = {
                "case_id": f"case-{case_index:04d}",
                "case_input": case_input,
                "status": status,
                "comparison_available": comparison_available,
                "final_pair_minus_isolated_energy": excess,
                "failure": failure,
                "single_run_result": single_record,
            }
            case["case_sha256"] = _case_digest(case)
            cases.append(case)
            case_index += 1

    comparison_count = sum(
        1 for case in cases if case["comparison_available"] is True
    )
    failure_count = sum(
        1 for case in cases if case["status"] == "NUMERICAL_PREFLIGHT_FAILURE"
    )
    rejection_count = sum(
        1 for case in cases if case["status"] == "CASE_PREFLIGHT_REJECTED"
    )
    payload: dict[str, object] = {
        "schema_version": SWEEP_SCHEMA_VERSION,
        "sweep_id": _sha256(
            {
                "schema_version": SWEEP_SCHEMA_VERSION,
                "spec": spec.to_dict(),
                "case_sha256": [case["case_sha256"] for case in cases],
            }
        ),
        "status": "ALL_CASES_EVALUATED",
        "evidence_class": "synthetic_constrained_lattice_sensitivity",
        "scientific_pass": False,
        "spec": spec.to_dict(),
        "case_count": len(cases),
        "comparison_available_count": comparison_count,
        "numerical_preflight_failure_count": failure_count,
        "case_preflight_rejection_count": rejection_count,
        "comparison_status": (
            "ALL_AVAILABLE"
            if comparison_count == len(cases)
            else "SOME_WITHHELD_OR_FAILED"
        ),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "cases": cases,
        "anchor_sensitivity_by_grid": _anchor_sensitivity_summary(
            spec.grid_levels, spec.anchor_radii, cases
        ),
        "limitations": [
            "each excess is conditional on the declared frozen anchor patches",
            "grid and anchor spread are sensitivity diagnostics, not uncertainty intervals",
            "no Richardson extrapolation or continuum limit is inferred",
            "no multistart or anchor-placement variation is included",
            "first-order convergence and a bounded curvature screen do not certify a minimum",
            "not a force, binding energy, physical energy, or physical time evolution",
            "synthetic engineering output only; no biological, consciousness, or rebirth inference",
        ],
    }
    payload["result_sha256"] = _sha256(payload)
    serialized = serialize_constrained_interaction_sensitivity_result(payload)
    return ConstrainedInteractionSensitivityResult(serialized)


def serialize_constrained_interaction_sensitivity_result(
    result: dict[str, object],
) -> str:
    """Verify nested run hashes, per-case hashes, counts, and envelope checksum."""
    if not isinstance(result, dict) or result.get("schema_version") != SWEEP_SCHEMA_VERSION:
        raise ValueError("unsupported constrained-sensitivity result schema")
    if result.get("status") != "ALL_CASES_EVALUATED":
        raise ValueError("sensitivity result status is inconsistent")
    if result.get("evidence_class") != "synthetic_constrained_lattice_sensitivity":
        raise ValueError("sensitivity result evidence class must remain synthetic")
    if result.get("scientific_pass") is not False:
        raise ValueError("sensitivity result cannot assert a scientific pass")
    spec = result.get("spec")
    if not isinstance(spec, dict) or spec.get("schema_version") != SWEEP_SCHEMA_VERSION:
        raise ValueError("sensitivity result spec is missing or malformed")
    if spec.get("data_mode") != "synthetic_only" or spec.get("randomness") != "none_deterministic":
        raise ValueError("sensitivity spec must remain synthetic and deterministic")
    for claim_flag in (
        "not_a_binding_energy",
        "not_a_force",
        "not_a_continuum_limit",
        "not_physical_time_evolution",
    ):
        if spec.get(claim_flag) is not True:
            raise ValueError(f"sensitivity spec claim limit {claim_flag} is required")
    try:
        validated_spec = ConstrainedInteractionSensitivitySpec(
            radius=spec["radius"],
            separation_vector=tuple(spec["separation_vector"]),
            relative_isorotation=tuple(spec["relative_isorotation"]),
            grid_levels=tuple(
                ConstrainedSensitivityGridLevel(
                    level["level_id"], tuple(level["shape"]), tuple(level["spacing"])
                )
                for level in spec["grid_levels"]
            ),
            anchor_radii=tuple(spec["anchor_radii"]),
            code_revision=spec["code_revision"],
            f_pi=spec["f_pi"],
            e=spec["e"],
            max_iterations=spec["max_iterations_per_run"],
            initial_step=spec["initial_step"],
            gradient_tolerance=spec["gradient_tolerance"],
            max_backtracks=spec["max_backtracks_per_iteration"],
            orientation_tolerance_rad=spec["orientation_tolerance_rad"],
            orientation_residual_tolerance=spec["orientation_residual_tolerance"],
            charge_drift_tolerance=spec["charge_drift_tolerance"],
            stationarity_metric=spec["stationarity_metric"],
            descent_metric=spec["descent_metric"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("sensitivity result spec does not satisfy its input schema") from exc
    if validated_spec.to_dict() != spec:
        raise ValueError("sensitivity result spec contains inconsistent derived values")
    levels = spec.get("grid_levels")
    anchor_radii = spec.get("anchor_radii")
    if not isinstance(levels, list) or not levels or not isinstance(anchor_radii, list) or not anchor_radii:
        raise ValueError("sensitivity spec must declare nonempty grid and anchor axes")
    if any(not isinstance(level, dict) for level in levels):
        raise ValueError("sensitivity spec grid levels must be objects")
    cases = result.get("cases")
    case_count = result.get("case_count")
    if (
        not isinstance(cases, list)
        or isinstance(case_count, bool)
        or not isinstance(case_count, Integral)
        or case_count != len(cases)
    ):
        raise ValueError("sensitivity result case count mismatch")
    expected_case_count = len(levels) * len(anchor_radii)
    if case_count != expected_case_count:
        raise ValueError("sensitivity cases do not exhaust the declared grid-anchor plan")
    identifiers = []
    comparison_count = 0
    failure_count = 0
    rejection_count = 0
    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError("sensitivity result cases must be objects")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("sensitivity case id must be a nonempty string")
        expected_level = levels[case_index // len(anchor_radii)]
        expected_anchor = anchor_radii[case_index % len(anchor_radii)]
        case_input = case.get("case_input")
        if (
            case_id != f"case-{case_index:04d}"
            or not isinstance(case_input, dict)
            or case_input.get("case_index") != case_index
            or case_input.get("grid_level") != expected_level
            or case_input.get("anchor_radius") != expected_anchor
        ):
            raise ValueError("sensitivity case input does not match the declared grid-anchor plan")
        identifiers.append(case_id)
        if case.get("case_sha256") != _case_digest(case):
            raise ValueError("sensitivity case checksum mismatch")
        nested = case.get("single_run_result")
        available = case.get("comparison_available")
        if not isinstance(available, bool):
            raise ValueError("comparison availability must be boolean")
        status = case.get("status")
        if nested is not None:
            if not isinstance(nested, dict):
                raise ValueError("single-run result must be an object or null")
            serialize_constrained_result(nested)
            nested_input = nested.get("input")
            if not isinstance(nested_input, dict):
                raise ValueError("single-run result is missing its input record")
            level_shape = expected_level.get("shape")
            level_spacing = expected_level.get("spacing")
            expected_runner_input = {
                "shape": level_shape,
                "spacing": level_spacing,
                "radius": spec.get("radius"),
                "anchor_radius": expected_anchor,
                "separation_vector": spec.get("separation_vector"),
                "relative_isorotation_input": spec.get("relative_isorotation"),
                "relative_isorotation_used": spec.get("relative_isorotation"),
                "code_revision": spec.get("code_revision"),
                "f_pi": spec.get("f_pi"),
                "e": spec.get("e"),
                "max_iterations_per_run": spec.get("max_iterations_per_run"),
                "initial_step": spec.get("initial_step"),
                "gradient_tolerance": spec.get("gradient_tolerance"),
                "max_backtracks_per_iteration": spec.get("max_backtracks_per_iteration"),
                "orientation_tolerance_rad": spec.get("orientation_tolerance_rad"),
                "orientation_residual_tolerance": spec.get("orientation_residual_tolerance"),
                "charge_drift_tolerance": spec.get("charge_drift_tolerance"),
                "stationarity_metric": spec.get("stationarity_metric"),
                "descent_metric": spec.get("descent_metric"),
                "solver": "nearest_neighbor_forward_link_v2",
            }
            if any(nested_input.get(key) != expected for key, expected in expected_runner_input.items()):
                raise ValueError("single-run input does not match its declared sweep case")
            if nested.get("status") not in {"COMPARISON_AVAILABLE", "COMPARISON_WITHHELD"}:
                raise ValueError("single-run status is outside the declared comparison status set")
            nested_comparison = nested.get("comparison")
            if not isinstance(nested_comparison, dict):
                raise ValueError("single-run result is missing comparison metadata")
            nested_available = nested_comparison.get(
                "available_only_if_all_three_converged_and_constraints_pass"
            )
            if available is not nested_available:
                raise ValueError("sweep availability disagrees with single-run result")
            if status != nested.get("status"):
                raise ValueError("sweep status disagrees with single-run result")
            if case.get("failure") is not None:
                raise ValueError("successful single-run record cannot include failure metadata")
            if available and case.get("final_pair_minus_isolated_energy") != nested_comparison.get(
                "final_pair_minus_isolated_energy"
            ):
                raise ValueError("sweep excess disagrees with single-run result")
        if available:
            comparison_count += 1
            _finite_real(
                case.get("final_pair_minus_isolated_energy"),
                "final pair-minus-isolated energy",
            )
            if nested is None:
                raise ValueError("available comparison requires a single-run result")
        elif case.get("final_pair_minus_isolated_energy") is not None:
            raise ValueError("unavailable comparison must have a null final excess")
        if status == "NUMERICAL_PREFLIGHT_FAILURE":
            failure_count += 1
            failure = case.get("failure")
            if nested is not None or not isinstance(failure, dict):
                raise ValueError("numerical preflight failure record is inconsistent")
            if failure.get("category") != "numerical_preflight_failure":
                raise ValueError("numerical preflight failure category is inconsistent")
            if any(
                not isinstance(failure.get(key), str) or not failure[key].strip()
                for key in ("stage", "failure_class", "message")
            ):
                raise ValueError("numerical preflight failure details are malformed")
        elif status == "CASE_PREFLIGHT_REJECTED":
            rejection_count += 1
            failure = case.get("failure")
            if nested is not None or not isinstance(failure, dict):
                raise ValueError("case preflight rejection record is inconsistent")
            if failure.get("category") != "case_input_preflight_rejection":
                raise ValueError("case preflight rejection category is inconsistent")
            if any(
                not isinstance(failure.get(key), str) or not failure[key].strip()
                for key in ("stage", "failure_class", "message")
            ):
                raise ValueError("case preflight rejection details are malformed")
        elif nested is None:
            raise ValueError("a case without a single-run result must have a failure status")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("sensitivity case ids must be unique")
    for name, observed in (
        ("comparison_available_count", comparison_count),
        ("numerical_preflight_failure_count", failure_count),
        ("case_preflight_rejection_count", rejection_count),
    ):
        value = result.get(name)
        if isinstance(value, bool) or not isinstance(value, Integral) or value != observed:
            raise ValueError(f"sensitivity result {name} mismatch")
    expected_comparison_status = (
        "ALL_AVAILABLE"
        if comparison_count == len(cases)
        else "SOME_WITHHELD_OR_FAILED"
    )
    if result.get("comparison_status") != expected_comparison_status:
        raise ValueError("sensitivity comparison status mismatch")
    expected_anchor_summary = _anchor_sensitivity_summary(
        validated_spec.grid_levels,
        validated_spec.anchor_radii,
        cases,
    )
    if result.get("anchor_sensitivity_by_grid") != expected_anchor_summary:
        raise ValueError("sensitivity anchor summary disagrees with case rows")
    expected_sweep_id = _sha256(
        {
            "schema_version": SWEEP_SCHEMA_VERSION,
            "spec": spec,
            "case_sha256": [case["case_sha256"] for case in cases],
        }
    )
    if result.get("sweep_id") != expected_sweep_id:
        raise ValueError("sensitivity sweep id mismatch")
    expected = result.get("result_sha256")
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    if not isinstance(expected, str) or expected != _sha256(payload):
        raise ValueError("sensitivity result checksum mismatch")
    return _canonical_json(result)
