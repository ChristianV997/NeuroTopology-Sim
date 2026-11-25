"""Deterministic engineering sweeps for the SU(2) nearest-neighbor relaxer.

Every sweep point starts from the same immutable input field. The module uses
no random numbers, external services, or optional plotting dependency. Its
JSON records solver behavior and numerical trajectories; they are not
scientific or physical validation. The model axes use ``lambda=e*f_pi`` and
``mu=f_pi/e``. Under the two-term Skyrme scaling, lambda sets inverse length
and the dimensionless grid geometry, while mu is the overall energy
prefactor. Physical units are not inferred by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice
import json
import math
from numbers import Integral, Real
import platform
from pathlib import Path
from typing import Any

import numpy as np

from .field import SU2GridField
from .nearest_neighbor import (
    CurvatureProbeDiagnostics,
    NearestNeighborRelaxationResult,
    relax_skyrme_field_nearest_neighbor,
)

SCHEMA_VERSION = "1.1.0"
ALGORITHM_ID = "su2-nearest-neighbor-relaxation-v1"
MAX_SWEEP_POINTS = 256
MAX_SWEEP_CANDIDATE_ATTEMPTS = 65_536


def _positive_values(values: tuple[float, ...], name: str) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a nonempty sequence of positive finite numbers")
    try:
        items = tuple(islice(iter(values), MAX_SWEEP_POINTS + 1))
    except TypeError as exc:
        raise ValueError(
            f"{name} must be a nonempty sequence of positive finite numbers"
        ) from exc
    if not items:
        raise ValueError(f"{name} must be a nonempty sequence of positive finite numbers")
    if len(items) > MAX_SWEEP_POINTS:
        raise ValueError(f"{name} exceeds the maximum axis size of {MAX_SWEEP_POINTS}")
    normalized: list[float] = []
    for value in items:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise ValueError(f"{name} values must be positive finite numbers")
        number = float(value)
        if not math.isfinite(number) or number <= 0.0:
            raise ValueError(f"{name} values must be positive finite numbers")
        normalized.append(number)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} values must not contain duplicates")
    return tuple(normalized)


def _positive_integers(values: tuple[int, ...], name: str) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a nonempty sequence of positive integers")
    try:
        items = tuple(islice(iter(values), MAX_SWEEP_POINTS + 1))
    except TypeError as exc:
        raise ValueError(f"{name} must be a nonempty sequence of positive integers") from exc
    if not items:
        raise ValueError(f"{name} must be a nonempty sequence of positive integers")
    if len(items) > MAX_SWEEP_POINTS:
        raise ValueError(f"{name} exceeds the maximum axis size of {MAX_SWEEP_POINTS}")
    normalized: list[int] = []
    for value in items:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
            raise ValueError(f"{name} values must be positive integers")
        integer = int(value)
        if integer < 1:
            raise ValueError(f"{name} values must be positive integers")
        normalized.append(integer)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} values must not contain duplicates")
    return tuple(normalized)


def _positive_integer(value: object, name: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    minimum = 0 if allow_zero else 1
    if result < minimum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be {qualifier}")
    return result


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


@dataclass(frozen=True)
class NearestNeighborSweepSpec:
    """Scale-separated model axes and dimensionless optimizer settings.

    The scale axes are ``lambda=e*f_pi`` and ``mu=f_pi/e``. The solver uses
    the normalized objective with ``solver_f_pi=solver_e=sqrt(lambda)`` and
    returns energy and curvature quantities rescaled by ``mu``. This avoids
    scale-dependent optimizer thresholds in the underlying solver.
    """

    inverse_length_scale_values: tuple[float, ...] = (1.0,)
    energy_prefactor_values: tuple[float, ...] = (1.0,)
    initial_dimensionless_step_values: tuple[float, ...] = (1.0e-3,)
    max_iterations_values: tuple[int, ...] = (10,)
    dimensionless_gradient_tolerance: float = 1.0e-7
    max_backtracks: int = 12

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "inverse_length_scale_values",
            _positive_values(
                self.inverse_length_scale_values, "inverse_length_scale_values"
            ),
        )
        object.__setattr__(
            self,
            "energy_prefactor_values",
            _positive_values(self.energy_prefactor_values, "energy_prefactor_values"),
        )
        object.__setattr__(
            self,
            "initial_dimensionless_step_values",
            _positive_values(
                self.initial_dimensionless_step_values,
                "initial_dimensionless_step_values",
            ),
        )
        object.__setattr__(
            self,
            "max_iterations_values",
            _positive_integers(self.max_iterations_values, "max_iterations_values"),
        )
        object.__setattr__(
            self,
            "dimensionless_gradient_tolerance",
            _positive_real(
                self.dimensionless_gradient_tolerance,
                "dimensionless_gradient_tolerance",
            ),
        )
        object.__setattr__(
            self,
            "max_backtracks",
            _positive_integer(self.max_backtracks, "max_backtracks", allow_zero=True),
        )
        if self.point_count > MAX_SWEEP_POINTS:
            raise ValueError(f"sweep exceeds the maximum point count of {MAX_SWEEP_POINTS}")
        _validate_candidate_attempt_budget(self)

    @property
    def point_count(self) -> int:
        return (
            len(self.inverse_length_scale_values)
            * len(self.energy_prefactor_values)
            * len(self.initial_dimensionless_step_values)
            * len(self.max_iterations_values)
        )

    @property
    def candidate_attempt_upper_bound(self) -> int:
        return (
            self.point_count
            * max(self.max_iterations_values)
            * (self.max_backtracks + 1)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_scale_axes": {
                "inverse_length_scale_values": list(self.inverse_length_scale_values),
                "energy_prefactor_values": list(self.energy_prefactor_values),
                "grid_mode": (
                    "fixed_input_grid; h_i=lambda*a_i and ell_i=lambda*L_i; "
                    "physical interpretation depends on caller-supplied units"
                ),
                "definitions": {
                    "inverse_length_scale": "e*f_pi",
                    "energy_prefactor": "f_pi/e",
                    "f_pi": "sqrt(inverse_length_scale*energy_prefactor)",
                    "e": "sqrt(inverse_length_scale/energy_prefactor)",
                    "dimensionless_spacing": "lambda*input_spacing",
                    "dimensionless_domain_extent": "lambda*input_domain_extent",
                    "solver_normalization": {
                        "solver_f_pi": "sqrt(inverse_length_scale)",
                        "solver_e": "sqrt(inverse_length_scale)",
                        "solver_energy_prefactor": 1.0,
                        "returned_energy_and_curvature_scale": "energy_prefactor",
                    },
                },
                "physical_units": "not_assessed",
            },
            "optimizer": {
                "initial_dimensionless_step_values": list(
                    self.initial_dimensionless_step_values
                ),
                "dimensionless_gradient_tolerance": self.dimensionless_gradient_tolerance,
                "max_iterations_values": list(self.max_iterations_values),
                "max_backtracks": self.max_backtracks,
                "finite_difference_step": "not_swept; analytic gradient ignores it",
                "interpretation": "numerical_controls_not_physical_time",
            },
            "planned_work": {
                "unit": "line_search_candidate_step",
                "upper_bound": self.candidate_attempt_upper_bound,
                "limit": MAX_SWEEP_CANDIDATE_ATTEMPTS,
                "excludes_gradient_and_curvature_probes": True,
                "not_a_wall_time_or_memory_bound": True,
            },
        }


@dataclass(frozen=True)
class RelaxationPointParameters:
    inverse_length_scale: float
    energy_prefactor: float
    f_pi: float
    e: float
    normalized_solver_f_pi: float
    normalized_solver_e: float
    input_domain_extent: tuple[float, float, float]
    dimensionless_spacing: tuple[float, float, float]
    dimensionless_domain_extent: tuple[float, float, float]
    initial_dimensionless_step: float
    solver_initial_step: float
    max_iterations: int
    dimensionless_gradient_tolerance: float
    solver_gradient_tolerance: float
    max_backtracks: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "inverse_length_scale": self.inverse_length_scale,
            "energy_prefactor": self.energy_prefactor,
            "f_pi": self.f_pi,
            "e": self.e,
            "normalized_solver_f_pi": self.normalized_solver_f_pi,
            "normalized_solver_e": self.normalized_solver_e,
            "input_domain_extent": list(self.input_domain_extent),
            "dimensionless_spacing": list(self.dimensionless_spacing),
            "dimensionless_domain_extent": list(self.dimensionless_domain_extent),
            "initial_dimensionless_step": self.initial_dimensionless_step,
            "solver_initial_step": self.solver_initial_step,
            "max_iterations": self.max_iterations,
            "dimensionless_gradient_tolerance": self.dimensionless_gradient_tolerance,
            "solver_gradient_tolerance": self.solver_gradient_tolerance,
            "max_backtracks": self.max_backtracks,
        }


@dataclass(frozen=True)
class NearestNeighborSweepPoint:
    point_id: str
    parameters: RelaxationPointParameters
    final_field_checksum_sha256: str
    energy_history: tuple[float, ...]
    topological_charge_history: tuple[float, ...]
    iterations: int
    termination: str
    stationarity_status: str
    curvature_diagnostics: CurvatureProbeDiagnostics | None
    minimum_certified: bool
    execution_status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        curvature = self.curvature_diagnostics
        return {
            "point_id": self.point_id,
            "parameters": self.parameters.to_dict(),
            "final_field_checksum_sha256": self.final_field_checksum_sha256,
            "energy_history": list(self.energy_history),
            "topological_charge_history": list(self.topological_charge_history),
            "iterations": self.iterations,
            "termination": self.termination,
            "stationarity_status": self.stationarity_status,
            "curvature_diagnostics": (
                None
                if curvature is None
                else {
                    "probe_count": curvature.probe_count,
                    "probe_step": curvature.probe_step,
                    "negative_curvature_tolerance": curvature.negative_curvature_tolerance,
                    "most_negative_directional_curvature": (
                        curvature.most_negative_directional_curvature
                    ),
                    "assessment": curvature.assessment,
                }
            ),
            "minimum_certified": self.minimum_certified,
            "execution_status": self.execution_status,
        }


@dataclass(frozen=True)
class NearestNeighborSweepResult:
    sweep_id: str
    input_checksum_sha256: str
    input_shape: tuple[int, int, int, int]
    spacing: tuple[float, float, float]
    boundary: str
    length_unit: str
    spec: NearestNeighborSweepSpec
    points: tuple[NearestNeighborSweepPoint, ...]
    python_version: str
    numpy_version: str
    schema_version: str = SCHEMA_VERSION
    algorithm_id: str = ALGORITHM_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm_id": self.algorithm_id,
            "sweep_id": self.sweep_id,
            "input": {
                "checksum_sha256": self.input_checksum_sha256,
                "shape": list(self.input_shape),
                "spacing": list(self.spacing),
                "boundary": self.boundary,
                "length_unit": self.length_unit,
                "physical_unit_conversion": "not_assessed",
                "grid_mode": "fixed_input_grid",
            },
            "spec": self.spec.to_dict(),
            "environment": {
                "python_version": self.python_version,
                "numpy_version": self.numpy_version,
            },
            "points": [point.to_dict() for point in self.points],
            "energy_output": {
                "conversion": "model_energy=energy_prefactor*normalized_solver_energy",
                "unit_status": "not_assessed",
            },
            "evidence_class": "engineering_numerical_output",
            "scientific_status": "NOT_ASSESSED",
            "convergence_claim": "NOT_ESTABLISHED",
            "claim_scope": "bounded_optimizer_behavior_only",
        }

    def to_json(self) -> str:
        """Return stable strict JSON; non-finite values are rejected."""
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def write_json(self, destination: str | Path) -> Path:
        """Write strict deterministic JSON and return the output path."""
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8", newline="\n")
        return target


def _field_checksum(field: SU2GridField) -> str:
    metadata = {
        "shape": list(field.components.shape),
        "spacing": list(field.spacing),
        "boundary": field.boundary,
        "length_unit": field.length_unit,
    }
    canonical_metadata = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    canonical_values = np.ascontiguousarray(field.components, dtype="<f8").tobytes(order="C")
    return hashlib.sha256(canonical_metadata + b"\0" + canonical_values).hexdigest()


def _sweep_id(input_checksum: str, spec: NearestNeighborSweepSpec) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_id": ALGORITHM_ID,
        "input_checksum_sha256": input_checksum,
        "spec": spec.to_dict(),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_candidate_attempt_budget(spec: NearestNeighborSweepSpec) -> int:
    """Validate and return a conservative optimizer-attempt count bound."""
    point_count = (
        len(
            _positive_values(
                spec.inverse_length_scale_values, "inverse_length_scale_values"
            )
        )
        * len(_positive_values(spec.energy_prefactor_values, "energy_prefactor_values"))
        * len(
            _positive_values(
                spec.initial_dimensionless_step_values,
                "initial_dimensionless_step_values",
            )
        )
        * len(_positive_integers(spec.max_iterations_values, "max_iterations_values"))
    )
    max_iterations = max(
        _positive_integers(spec.max_iterations_values, "max_iterations_values")
    )
    max_backtracks = _positive_integer(
        spec.max_backtracks, "max_backtracks", allow_zero=True
    )
    attempts = point_count * max_iterations * (max_backtracks + 1)
    if attempts > MAX_SWEEP_CANDIDATE_ATTEMPTS:
        raise ValueError(
            "sweep exceeds the candidate-attempt work budget of "
            f"{MAX_SWEEP_CANDIDATE_ATTEMPTS}"
        )
    return attempts


def _point_parameters(
    initial: SU2GridField,
    *,
    inverse_length_scale: float,
    energy_prefactor: float,
    initial_dimensionless_step: float,
    max_iterations: int,
    dimensionless_gradient_tolerance: float,
    max_backtracks: int,
) -> RelaxationPointParameters:
    """Derive solver coefficients and grid geometry from scale axes."""
    f_pi = math.sqrt(inverse_length_scale) * math.sqrt(energy_prefactor)
    e = math.sqrt(inverse_length_scale) / math.sqrt(energy_prefactor)
    normalized_solver_f_pi = math.sqrt(inverse_length_scale)
    normalized_solver_e = math.sqrt(inverse_length_scale)
    # Optimize E / E0 so the relaxer's absolute energy floor and gradient
    # tolerance cannot change behavior when only E0 changes.
    solver_initial_step = initial_dimensionless_step
    solver_gradient_tolerance = dimensionless_gradient_tolerance
    derived = (
        f_pi,
        e,
        normalized_solver_f_pi,
        normalized_solver_e,
        solver_initial_step,
        solver_gradient_tolerance,
    )
    if not all(math.isfinite(value) and value > 0.0 for value in derived):
        raise ValueError("model scales produce unrepresentable solver parameters")

    dimensionless_spacing = tuple(
        inverse_length_scale * spacing for spacing in initial.spacing
    )
    cell_counts = initial.components.shape[:3]
    extent_steps = (
        cell_counts
        if initial.boundary == "periodic"
        else tuple(count - 1 for count in cell_counts)
    )
    input_domain_extent = tuple(
        spacing * count for spacing, count in zip(initial.spacing, extent_steps)
    )
    dimensionless_domain_extent = tuple(
        inverse_length_scale * extent for extent in input_domain_extent
    )
    if not all(
        math.isfinite(value) and value > 0.0
        for value in input_domain_extent + dimensionless_spacing + dimensionless_domain_extent
    ):
        raise ValueError("inverse-length scale produces unrepresentable grid geometry")

    return RelaxationPointParameters(
        inverse_length_scale=inverse_length_scale,
        energy_prefactor=energy_prefactor,
        f_pi=f_pi,
        e=e,
        normalized_solver_f_pi=normalized_solver_f_pi,
        normalized_solver_e=normalized_solver_e,
        input_domain_extent=input_domain_extent,
        dimensionless_spacing=dimensionless_spacing,
        dimensionless_domain_extent=dimensionless_domain_extent,
        initial_dimensionless_step=initial_dimensionless_step,
        solver_initial_step=solver_initial_step,
        max_iterations=max_iterations,
        dimensionless_gradient_tolerance=dimensionless_gradient_tolerance,
        solver_gradient_tolerance=solver_gradient_tolerance,
        max_backtracks=max_backtracks,
    )


def _point_from_solver_result(
    point_id: str,
    parameters: RelaxationPointParameters,
    result: NearestNeighborRelaxationResult,
) -> NearestNeighborSweepPoint:
    energies = tuple(
        _rescale_energy(value, parameters.energy_prefactor, "energy history")
        for value in result.energy_history
    )
    charges = tuple(float(value) for value in result.topological_charge_history)
    if not energies or len(energies) != len(charges):
        raise ValueError(f"solver returned invalid trajectories for {point_id}")
    if not all(math.isfinite(value) for value in energies + charges):
        raise FloatingPointError(f"solver returned non-finite trajectories for {point_id}")
    curvature = result.curvature_diagnostics
    if curvature is not None:
        curvature = CurvatureProbeDiagnostics(
            probe_count=curvature.probe_count,
            probe_step=curvature.probe_step,
            negative_curvature_tolerance=_rescale_energy(
                curvature.negative_curvature_tolerance,
                parameters.energy_prefactor,
                "curvature tolerance",
            ),
            most_negative_directional_curvature=(
                None
                if curvature.most_negative_directional_curvature is None
                else _rescale_energy(
                    curvature.most_negative_directional_curvature,
                    parameters.energy_prefactor,
                    "directional curvature",
                )
            ),
            assessment=curvature.assessment,
        )
    return NearestNeighborSweepPoint(
        point_id=point_id,
        parameters=parameters,
        final_field_checksum_sha256=_field_checksum(result.field),
        energy_history=energies,
        topological_charge_history=charges,
        iterations=int(result.iterations),
        termination=result.termination,
        stationarity_status=result.stationarity_status,
        curvature_diagnostics=curvature,
        minimum_certified=bool(result.minimum_certified),
    )


def _rescale_energy(value: float, scale: float, label: str) -> float:
    """Scale normalized model energy; reject overflow and underflowed results.

    Nonzero subnormal outputs are rejected because their reduced precision makes
    the scale-converted energy or curvature unreliable for this artifact.
    """
    normalized_value = float(value)
    result = normalized_value * scale
    if not math.isfinite(result):
        raise FloatingPointError(f"{label} is not finite after model-scale conversion")
    if normalized_value != 0.0 and result == 0.0:
        raise FloatingPointError(f"{label} underflowed during model-scale conversion")
    if result != 0.0 and abs(result) < np.finfo(np.float64).tiny:
        raise FloatingPointError(
            f"{label} underflowed into the subnormal range during model-scale conversion"
        )
    return result


def run_nearest_neighbor_sweep(
    initial: SU2GridField, spec: NearestNeighborSweepSpec
) -> NearestNeighborSweepResult:
    """Run an ordered, bounded Cartesian sweep from the same initial field.

    A point failure raises immediately instead of silently omitting that point.
    Fixed point-count and candidate-attempt caps bound the declared optimizer
    work. They do not bound wall time or memory because cost per attempt scales
    with field size. Stable loop order makes output reproducible for identical
    input/config.
    """
    if not isinstance(initial, SU2GridField):
        raise ValueError("initial must be an SU2GridField")
    if not isinstance(spec, NearestNeighborSweepSpec):
        raise ValueError("spec must be a NearestNeighborSweepSpec")
    if spec.point_count > MAX_SWEEP_POINTS:
        raise ValueError(f"sweep exceeds the maximum point count of {MAX_SWEEP_POINTS}")
    # Repeat the constructor preflight before checksumming or invoking a solver;
    # this also protects against objects altered outside the frozen API.
    _validate_candidate_attempt_budget(spec)

    checksum = _field_checksum(initial)
    points: list[NearestNeighborSweepPoint] = []
    index = 0
    for inverse_length_scale in spec.inverse_length_scale_values:
        for energy_prefactor in spec.energy_prefactor_values:
            for initial_dimensionless_step in spec.initial_dimensionless_step_values:
                for max_iterations in spec.max_iterations_values:
                    parameters = _point_parameters(
                        initial,
                        inverse_length_scale=inverse_length_scale,
                        energy_prefactor=energy_prefactor,
                        initial_dimensionless_step=initial_dimensionless_step,
                        max_iterations=max_iterations,
                        dimensionless_gradient_tolerance=(
                            spec.dimensionless_gradient_tolerance
                        ),
                        max_backtracks=spec.max_backtracks,
                    )
                    solver_result = relax_skyrme_field_nearest_neighbor(
                        initial,
                        f_pi=parameters.normalized_solver_f_pi,
                        e=parameters.normalized_solver_e,
                        max_iterations=max_iterations,
                        initial_step=parameters.solver_initial_step,
                        gradient_tolerance=parameters.solver_gradient_tolerance,
                        max_backtracks=spec.max_backtracks,
                    )
                    points.append(
                        _point_from_solver_result(
                            f"point-{index:04d}", parameters, solver_result
                        )
                    )
                    index += 1

    return NearestNeighborSweepResult(
        sweep_id=_sweep_id(checksum, spec),
        input_checksum_sha256=checksum,
        input_shape=tuple(int(value) for value in initial.components.shape),
        spacing=tuple(float(value) for value in initial.spacing),
        boundary=initial.boundary,
        length_unit=initial.length_unit,
        spec=spec,
        points=tuple(points),
        python_version=platform.python_version(),
        numpy_version=np.__version__,
    )
