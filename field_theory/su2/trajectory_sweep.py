"""Bounded deterministic parameter sweeps for Lorentzian SU(2) trajectories.

The sweep varies dimensionless model and integration parameters on one fixed
input grid. Every point starts from the same immutable field and velocity.
Results retain compact diagnostic histories and hashes, not full field
snapshots; use the trajectory solver directly when spatial snapshots are
needed. These are exploratory numerical outputs, not physical validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice, product
import json
import math
import platform
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import numpy as np

from .field import SU2GridField, validate_spacing
from .lorentzian import LorentzianSkyrmeTrajectory, evolve_lorentzian_skyrme


SWEEP_SCHEMA_VERSION = "su2.lorentzian_trajectory_sweep.v1"
SWEEP_ALGORITHM_ID = "su2-lorentzian-rk4-sweep-v1"
MAX_SWEEP_AXIS_VALUES = 64
MAX_SWEEP_POINTS = 64
MAX_SWEEP_RK_STAGE_SITE_EVALUATIONS = 40_000_000
MAX_SWEEP_RECORD_SITE_VISITS = 40_000_000
MAX_SWEEP_SNAPSHOTS_PER_POINT = 32
MAX_SWEEP_SNAPSHOT_BYTES_PER_POINT = 128 * 1024 * 1024
MAX_GRID_NODES = 32_768
MAX_STEPS = 100_000
_STEP_RATIO_REL_TOLERANCE = 1.0e-10


def _bounded_reals(
    values: object, name: str, *, allow_zero: bool = False
) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a nonempty bounded sequence of real numbers")
    try:
        items = tuple(islice(iter(values), MAX_SWEEP_AXIS_VALUES + 1))  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            f"{name} must be a nonempty bounded sequence of real numbers"
        ) from exc
    if not items:
        raise ValueError(f"{name} must not be empty")
    if len(items) > MAX_SWEEP_AXIS_VALUES:
        raise ValueError(f"{name} exceeds the axis limit of {MAX_SWEEP_AXIS_VALUES}")
    normalized: list[float] = []
    for value in items:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise ValueError(f"{name} values must be finite real numbers")
        number = float(value)
        valid = math.isfinite(number) and (number >= 0.0 if allow_zero else number > 0.0)
        if not valid:
            qualifier = "nonnegative" if allow_zero else "positive"
            raise ValueError(f"{name} values must be finite and {qualifier}")
        normalized.append(number)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} values must not contain duplicates")
    return tuple(normalized)


def _bounded_integer(
    value: object, name: str, *, minimum: int, maximum: int
) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _steps_for(final_time: float, dt: float) -> int:
    ratio = final_time / dt
    if not math.isfinite(ratio) or ratio < 1.0 or ratio > MAX_STEPS:
        raise ValueError(f"final_time/dt must give between 1 and {MAX_STEPS} steps")
    steps = int(round(ratio))
    tolerance = _STEP_RATIO_REL_TOLERANCE * max(1.0, abs(ratio))
    if steps < 1 or abs(ratio - steps) > tolerance:
        raise ValueError("each dt must divide final_time into an integer step count")
    return steps


def _saved_count(steps: int, stride: int) -> int:
    return 1 + steps // stride + (1 if steps % stride else 0)


def _field_checksum(field: SU2GridField) -> str:
    metadata = {
        "shape": list(field.components.shape),
        "spacing": list(field.spacing),
        "boundary": field.boundary,
        "length_unit": field.length_unit,
    }
    encoded = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    values = np.asarray(field.components, dtype="<f8", order="C")
    return hashlib.sha256(encoded + b"\0" + values.tobytes(order="C")).hexdigest()


def _array_checksum(values: np.ndarray) -> str:
    canonical = np.asarray(values, dtype="<f8", order="C")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _scale_proxies(
    field: SU2GridField, *, f_pi: float, e: float, damping: float, dt: float
) -> tuple[float, float, tuple[float, float, float], tuple[float, float, float], float, float]:
    inverse_length = e * f_pi
    energy_prefactor = f_pi / e
    if not math.isfinite(inverse_length) or inverse_length <= 0.0:
        raise ValueError("e*f_pi scale proxy is not representable")
    if not math.isfinite(energy_prefactor) or energy_prefactor <= 0.0:
        raise ValueError("f_pi/e scale proxy is not representable")
    shape = field.components.shape[:3]
    extents = tuple(
        (int(size) if field.boundary == "periodic" else int(size) - 1) * spacing
        for size, spacing in zip(shape, field.spacing)
    )
    dimensionless_spacing = tuple(inverse_length * spacing for spacing in field.spacing)
    dimensionless_extent = tuple(inverse_length * extent for extent in extents)
    dimensionless_dt = inverse_length * dt
    dimensionless_damping = damping / inverse_length
    derived = (
        *dimensionless_spacing,
        *dimensionless_extent,
        dimensionless_dt,
        dimensionless_damping,
    )
    if not all(math.isfinite(value) for value in derived):
        raise ValueError("dimensionless grid, time, or damping scale proxy is not representable")
    positive_proxies = (
        *zip(field.spacing, dimensionless_spacing),
        *zip(extents, dimensionless_extent),
        (dt, dimensionless_dt),
    )
    if any(source > 0.0 and proxy == 0.0 for source, proxy in positive_proxies):
        raise ValueError("a positive dimensionless grid or time proxy underflowed to zero")
    if damping > 0.0 and dimensionless_damping == 0.0:
        raise ValueError("positive dimensionless damping proxy underflowed to zero")
    return (
        inverse_length,
        energy_prefactor,
        dimensionless_spacing,
        dimensionless_extent,
        dimensionless_dt,
        dimensionless_damping,
    )


def _dimensionless_initial_condition_proxies(
    velocity: np.ndarray, inverse_length: float, final_time: float
) -> tuple[float, float, float]:
    """Return dimensionless horizon and RMS/max initial speed proxies."""
    horizon = inverse_length * final_time
    speed = np.hypot.reduce(np.abs(velocity), axis=-1)
    maximum_speed = float(np.max(speed))
    rms_speed = (
        0.0
        if maximum_speed == 0.0
        else maximum_speed * math.sqrt(float(np.mean((speed / maximum_speed) ** 2)))
    )
    rms_velocity = rms_speed / inverse_length
    maximum_velocity = maximum_speed / inverse_length
    if not all(math.isfinite(value) for value in (horizon, rms_velocity, maximum_velocity)):
        raise ValueError("dimensionless horizon or initial-velocity proxy is not representable")
    if horizon <= 0.0:
        raise ValueError("positive dimensionless time horizon underflowed to zero")
    if maximum_speed > 0.0 and (rms_velocity == 0.0 or maximum_velocity == 0.0):
        raise ValueError("positive dimensionless initial velocity proxy underflowed to zero")
    return horizon, rms_velocity, maximum_velocity


@dataclass(frozen=True)
class LorentzianSweepSpec:
    """Declared axes for a fixed-final-time trajectory sweep.

    Couplings and damping are dimensionless model parameters. The dt axis is
    a numerical-resolution axis: every dt must divide final_time exactly
    within floating-point tolerance. No physical parameter range is implied.
    """

    f_pi_values: tuple[float, ...] = (1.0,)
    e_values: tuple[float, ...] = (1.0,)
    damping_values: tuple[float, ...] = (0.0,)
    dt_values: tuple[float, ...] = (0.01,)
    final_time: float = 0.1
    max_saved_snapshots_per_point: int = 32
    max_total_rk_stage_site_evaluations: int = (
        MAX_SWEEP_RK_STAGE_SITE_EVALUATIONS
    )
    max_total_record_site_visits: int = MAX_SWEEP_RECORD_SITE_VISITS
    max_linearized_damping_step: float = 2.5
    max_snapshot_bytes_per_point: int = MAX_SWEEP_SNAPSHOT_BYTES_PER_POINT
    max_linearized_cfl: float = 2.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "f_pi_values", _bounded_reals(self.f_pi_values, "f_pi_values"))
        object.__setattr__(self, "e_values", _bounded_reals(self.e_values, "e_values"))
        object.__setattr__(
            self,
            "damping_values",
            _bounded_reals(self.damping_values, "damping_values", allow_zero=True),
        )
        object.__setattr__(self, "dt_values", _bounded_reals(self.dt_values, "dt_values"))
        object.__setattr__(self, "final_time", _positive_real(self.final_time, "final_time"))
        object.__setattr__(
            self,
            "max_saved_snapshots_per_point",
            _bounded_integer(
                self.max_saved_snapshots_per_point,
                "max_saved_snapshots_per_point",
                minimum=2,
                maximum=MAX_SWEEP_SNAPSHOTS_PER_POINT,
            ),
        )
        object.__setattr__(
            self,
            "max_total_rk_stage_site_evaluations",
            _bounded_integer(
                self.max_total_rk_stage_site_evaluations,
                "max_total_rk_stage_site_evaluations",
                minimum=1,
                maximum=MAX_SWEEP_RK_STAGE_SITE_EVALUATIONS,
            ),
        )
        object.__setattr__(
            self,
            "max_total_record_site_visits",
            _bounded_integer(
                self.max_total_record_site_visits,
                "max_total_record_site_visits",
                minimum=1,
                maximum=MAX_SWEEP_RECORD_SITE_VISITS,
            ),
        )
        object.__setattr__(
            self,
            "max_linearized_damping_step",
            _positive_real(
                self.max_linearized_damping_step, "max_linearized_damping_step"
            ),
        )
        object.__setattr__(
            self,
            "max_snapshot_bytes_per_point",
            _bounded_integer(
                self.max_snapshot_bytes_per_point,
                "max_snapshot_bytes_per_point",
                minimum=1,
                maximum=MAX_SWEEP_SNAPSHOT_BYTES_PER_POINT,
            ),
        )
        object.__setattr__(
            self,
            "max_linearized_cfl",
            _positive_real(self.max_linearized_cfl, "max_linearized_cfl"),
        )
        for dt in self.dt_values:
            _steps_for(self.final_time, dt)
        if self.point_count > MAX_SWEEP_POINTS:
            raise ValueError(f"sweep exceeds the point limit of {MAX_SWEEP_POINTS}")

    @property
    def point_count(self) -> int:
        return (
            len(self.f_pi_values)
            * len(self.e_values)
            * len(self.damping_values)
            * len(self.dt_values)
        )

    def steps_for(self, dt: float) -> int:
        return _steps_for(self.final_time, dt)

    def save_every_for(self, dt: float) -> int:
        steps = self.steps_for(dt)
        return max(1, math.ceil(steps / (self.max_saved_snapshots_per_point - 1)))

    def point_parameters(self):
        return product(
            self.f_pi_values,
            self.e_values,
            self.damping_values,
            self.dt_values,
        )

    def rk_stage_site_work(self, n_sites: int) -> int:
        coupling_points = (
            len(self.f_pi_values) * len(self.e_values) * len(self.damping_values)
        )
        return (
            4
            * n_sites
            * coupling_points
            * sum(self.steps_for(dt) for dt in self.dt_values)
        )

    def record_site_visits(self, n_sites: int) -> int:
        coupling_points = (
            len(self.f_pi_values) * len(self.e_values) * len(self.damping_values)
        )
        return coupling_points * n_sites * sum(
            _saved_count(self.steps_for(dt), self.save_every_for(dt))
            for dt in self.dt_values
        )

    def snapshot_bytes(self, n_sites: int) -> int:
        largest = 0
        for dt in self.dt_values:
            steps = self.steps_for(dt)
            stride = self.save_every_for(dt)
            largest = max(largest, _saved_count(steps, stride))
        return largest * n_sites * 4 * np.dtype(np.float64).itemsize * 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "axes": {
                "f_pi_values": list(self.f_pi_values),
                "e_values": list(self.e_values),
                "damping_values": list(self.damping_values),
                "dt_values": list(self.dt_values),
                "final_time": self.final_time,
                "step_counts_by_dt": [
                    {"dt": dt, "steps": self.steps_for(dt)} for dt in self.dt_values
                ],
                "interpretation": (
                    "dimensionless model parameters and numerical dt; "
                    "no physical calibration implied"
                ),
            },
            "limits": {
                "max_points": MAX_SWEEP_POINTS,
                "max_total_rk_stage_site_evaluations": (
                    self.max_total_rk_stage_site_evaluations
                ),
                "max_total_record_site_visits": self.max_total_record_site_visits,
                "max_linearized_damping_step": self.max_linearized_damping_step,
                "max_saved_snapshots_per_point": self.max_saved_snapshots_per_point,
                "max_snapshot_bytes_per_point": self.max_snapshot_bytes_per_point,
                "max_linearized_cfl": self.max_linearized_cfl,
            },
        }


@dataclass(frozen=True)
class LorentzianSweepPoint:
    point_id: str
    f_pi: float
    e: float
    damping: float
    dt: float
    steps: int
    final_time: float
    save_every: int
    linearized_cfl_indicator: float
    inverse_length_scale_proxy: float
    energy_prefactor_proxy: float
    dimensionless_spacing_proxy: tuple[float, float, float]
    dimensionless_domain_extent_proxy: tuple[float, float, float]
    dimensionless_dt_proxy: float
    dimensionless_damping_proxy: float
    dimensionless_final_time_proxy: float
    dimensionless_initial_velocity_rms_proxy: float
    dimensionless_initial_velocity_max_proxy: float
    time_history: tuple[float, ...]
    energy_sigma_history: tuple[float, ...]
    energy_skyrme_history: tuple[float, ...]
    kinetic_sigma_history: tuple[float, ...]
    kinetic_skyrme_history: tuple[float, ...]
    total_energy_history: tuple[float, ...]
    dissipated_energy_history: tuple[float, ...]
    energy_balance_residual_history: tuple[float, ...]
    approximate_charge_history: tuple[float, ...]
    time_kinetic_min_eigenvalue_history: tuple[float, ...]
    time_kinetic_max_condition_history: tuple[float, ...]
    max_unit_norm_error: float
    max_tangency_error: float
    initial_field_checksum_sha256: str
    initial_velocity_checksum_sha256: str
    final_field_checksum_sha256: str
    hyperbolicity_status: str = "not_certified"
    termination: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "parameters": {
                "f_pi": self.f_pi,
                "e": self.e,
                "damping": self.damping,
                "dt": self.dt,
                "steps": self.steps,
                "final_time": self.final_time,
                "save_every": self.save_every,
                "linearized_cfl_indicator": self.linearized_cfl_indicator,
                "derived_scale_proxies": {
                    "inverse_length_scale_e_times_f_pi": self.inverse_length_scale_proxy,
                    "energy_prefactor_f_pi_over_e": self.energy_prefactor_proxy,
                    "dimensionless_spacing": list(self.dimensionless_spacing_proxy),
                    "dimensionless_domain_extent": list(self.dimensionless_domain_extent_proxy),
                    "dimensionless_dt": self.dimensionless_dt_proxy,
                    "dimensionless_damping": self.dimensionless_damping_proxy,
                    "dimensionless_final_time": self.dimensionless_final_time_proxy,
                    "dimensionless_initial_velocity_rms": self.dimensionless_initial_velocity_rms_proxy,
                    "dimensionless_initial_velocity_max": self.dimensionless_initial_velocity_max_proxy,
                    "physical_calibration": "not_assessed",
                },
            },
            "time_history": list(self.time_history),
            "energy_sigma_history": list(self.energy_sigma_history),
            "energy_skyrme_history": list(self.energy_skyrme_history),
            "kinetic_sigma_history": list(self.kinetic_sigma_history),
            "kinetic_skyrme_history": list(self.kinetic_skyrme_history),
            "total_energy_history": list(self.total_energy_history),
            "dissipated_energy_history": list(self.dissipated_energy_history),
            "energy_balance_residual_history": list(
                self.energy_balance_residual_history
            ),
            "approximate_charge_history": list(self.approximate_charge_history),
            "time_kinetic_min_eigenvalue_history": list(
                self.time_kinetic_min_eigenvalue_history
            ),
            "time_kinetic_max_condition_history": list(
                self.time_kinetic_max_condition_history
            ),
            "max_unit_norm_error": self.max_unit_norm_error,
            "max_tangency_error": self.max_tangency_error,
            "input_checksums": {
                "field_sha256": self.initial_field_checksum_sha256,
                "velocity_sha256": self.initial_velocity_checksum_sha256,
            },
            "final_field_checksum_sha256": self.final_field_checksum_sha256,
            "hyperbolicity_status": self.hyperbolicity_status,
            "termination": self.termination,
        }


@dataclass(frozen=True)
class LorentzianSweepResult:
    sweep_id: str
    initial_field_checksum_sha256: str
    initial_velocity_checksum_sha256: str
    input_shape: tuple[int, int, int, int]
    spacing: tuple[float, float, float]
    boundary: str
    length_unit: str
    spec: LorentzianSweepSpec
    points: tuple[LorentzianSweepPoint, ...]
    python_version: str
    numpy_version: str
    schema_version: str = SWEEP_SCHEMA_VERSION
    algorithm_id: str = SWEEP_ALGORITHM_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm_id": self.algorithm_id,
            "sweep_id": self.sweep_id,
            "input": {
                "field_checksum_sha256": self.initial_field_checksum_sha256,
                "velocity_checksum_sha256": self.initial_velocity_checksum_sha256,
                "shape": list(self.input_shape),
                "spacing": list(self.spacing),
                "boundary": self.boundary,
                "length_unit": self.length_unit,
                "physical_unit_conversion": "not_assessed",
            },
            "spec": self.spec.to_dict(),
            "environment": {
                "python_version": self.python_version,
                "numpy_version": self.numpy_version,
                "randomness": "none",
            },
            "points": [point.to_dict() for point in self.points],
            "evidence_class": "engineering_numerical_output",
            "scientific_status": "NOT_ASSESSED",
            "convergence_claim": "NOT_ESTABLISHED",
            "claim_scope": "bounded_dimensionless_lorentzian_trajectory_sweep",
            "field_snapshots_included": False,
        }

    def to_json(self) -> str:
        """Return stable strict JSON; reject non-finite or non-serializable values."""
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def write_json(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8", newline="\n")
        return target


def _validate_velocity(field: SU2GridField, initial_velocity: object) -> np.ndarray:
    raw = np.asarray(initial_velocity)
    if raw.dtype.kind not in "fiu" or raw.shape != field.components.shape:
        raise ValueError("initial_velocity must be a real array matching field.components")
    velocity = np.asarray(raw, dtype=np.float64).copy()
    if not np.all(np.isfinite(velocity)):
        raise ValueError("initial_velocity must be finite")
    with np.errstate(over="ignore", invalid="ignore"):
        speed = np.hypot.reduce(np.abs(velocity), axis=-1)
        tangent_error = np.abs(np.sum(field.components * velocity, axis=-1))
    if not np.all(np.isfinite(speed)) or not np.all(np.isfinite(tangent_error)):
        raise ValueError("initial_velocity magnitude must be representable")
    scale = max(1.0, float(np.max(speed)))
    if float(np.max(tangent_error)) > 1.0e-9 * scale:
        raise ValueError("initial_velocity must be tangent to S3 at every site")
    if field.boundary == "fixed_vacuum":
        fixed = np.zeros(field.components.shape[:3], dtype=bool)
        fixed[[0, -1], :, :] = True
        fixed[:, [0, -1], :] = True
        fixed[:, :, [0, -1]] = True
        if np.any(speed[fixed] > 1.0e-9 * scale):
            raise ValueError("initial_velocity must be zero at fixed-vacuum sites")
    return velocity


def _finite_real_vector(values: object, name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.dtype.kind not in "fiu":
        raise ValueError(f"solver returned malformed or non-real numeric {name}")
    converted = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(converted).all():
        raise ValueError(f"solver returned non-finite {name}")
    return converted


def _finite_real_scalar(value: object, name: str) -> float:
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"solver returned non-real numeric {name}")
    converted = float(raw)
    if not math.isfinite(converted):
        raise ValueError(f"solver returned non-finite {name}")
    return converted


def _validate_trajectory_output(
    trajectory: LorentzianSkyrmeTrajectory,
    *,
    initial: SU2GridField,
    f_pi: float,
    e: float,
    damping: float,
    dt: float,
    steps: int,
    save_every: int,
    final_time: float,
) -> None:
    """Reject malformed or non-finite solver results before a point is recorded."""
    if not isinstance(trajectory, LorentzianSkyrmeTrajectory):
        raise ValueError("solver returned an unexpected trajectory type")
    times = _finite_real_vector(trajectory.time_history, "time history")
    if times.size < 2:
        raise ValueError("solver returned a malformed time history")
    if times[0] != 0.0 or any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("solver time history must start at zero and increase strictly")
    saved_steps = [0]
    saved_steps.extend(range(save_every, steps + 1, save_every))
    if saved_steps[-1] != steps:
        saved_steps.append(steps)
    expected_times = tuple(float(step * dt) for step in saved_steps)
    if times.size != len(expected_times) or any(
        not math.isclose(
            float(actual), expected,
            rel_tol=_STEP_RATIO_REL_TOLERANCE,
            abs_tol=0.0,
        )
        for actual, expected in zip(times, expected_times)
    ):
        raise ValueError("solver time history does not match requested dt and save cadence")
    if not math.isclose(
        float(times[-1]),
        final_time,
        rel_tol=_STEP_RATIO_REL_TOLERANCE,
        abs_tol=0.0,
    ):
        raise ValueError("solver time history does not reach the requested final time")
    real_metadata = (
        trajectory.dt,
        trajectory.f_pi,
        trajectory.e,
        trajectory.damping,
    )
    integer_metadata = (trajectory.steps, trajectory.save_every)
    if any(
        isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
        for value in real_metadata
    ) or any(
        isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral)
        for value in integer_metadata
    ):
        raise ValueError("solver trajectory metadata has invalid numeric types")
    if (
        trajectory.dt != dt
        or trajectory.steps != steps
        or trajectory.save_every != save_every
    ):
        raise ValueError("solver trajectory does not match requested dt, steps, and save cadence")
    if trajectory.f_pi != f_pi or trajectory.e != e or trajectory.damping != damping:
        raise ValueError("solver trajectory does not match requested couplings")
    if trajectory.termination != "completed":
        raise ValueError("solver trajectory is not marked completed")
    if trajectory.hyperbolicity_status != "not_certified":
        raise ValueError("solver returned an unknown hyperbolicity status")

    histories = (
        "energy_sigma_history",
        "energy_skyrme_history",
        "kinetic_sigma_history",
        "kinetic_skyrme_history",
        "total_energy_history",
        "dissipated_energy_history",
        "energy_balance_residual_history",
        "approximate_charge_history",
        "time_kinetic_min_eigenvalue_history",
        "time_kinetic_max_condition_history",
    )
    for name in histories:
        values = _finite_real_vector(getattr(trajectory, name), name)
        if values.size != times.size:
            raise ValueError(f"solver returned malformed {name}")

    if len(trajectory.fields) != times.size or len(trajectory.velocities) != times.size:
        raise ValueError("solver snapshots do not match diagnostic history length")
    for field, velocity in zip(trajectory.fields, trajectory.velocities):
        if not isinstance(field, SU2GridField):
            raise ValueError("solver returned a field snapshot with the wrong type")
        if (
            field.components.shape != initial.components.shape
            or field.spacing != initial.spacing
            or field.boundary != initial.boundary
            or field.length_unit != initial.length_unit
        ):
            raise ValueError("solver field snapshot metadata changed during evolution")
        components = np.asarray(field.components)
        if components.dtype.kind not in "fiu" or not np.isfinite(components).all():
            raise ValueError("solver returned a malformed or non-finite field snapshot")
        raw_velocity = np.asarray(velocity)
        if (
            raw_velocity.dtype.kind not in "fiu"
            or raw_velocity.shape != initial.components.shape
            or not np.isfinite(raw_velocity).all()
        ):
            raise ValueError("solver returned a malformed or non-finite velocity snapshot")

    scalar_diagnostics = (
        (trajectory.max_unit_norm_error, "max_unit_norm_error"),
        (trajectory.max_tangency_error, "max_tangency_error"),
        (trajectory.cell_volume, "cell_volume"),
        (trajectory.linearized_cfl_indicator, "linearized_cfl_indicator"),
    )
    for value, name in scalar_diagnostics:
        _finite_real_scalar(value, name)

def _sweep_id(
    field_checksum: str, velocity_checksum: str, spec: LorentzianSweepSpec
) -> str:
    payload = {
        "schema_version": SWEEP_SCHEMA_VERSION,
        "algorithm_id": SWEEP_ALGORITHM_ID,
        "field_checksum_sha256": field_checksum,
        "velocity_checksum_sha256": velocity_checksum,
        "spec": spec.to_dict(),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_lorentzian_sweep(
    initial: SU2GridField,
    initial_velocity: object,
    spec: LorentzianSweepSpec,
) -> LorentzianSweepResult:
    """Run a deterministic bounded Cartesian sweep at one common final time.

    All axes and aggregate work/memory/CFL limits are checked before the first
    call to the evolution solver. Each point receives the same immutable input
    field and a private copy of its initial velocity. Only compact histories
    and a final-field checksum are retained in the result.
    """
    if not isinstance(initial, SU2GridField):
        raise ValueError("initial must be an SU2GridField")
    if not isinstance(spec, LorentzianSweepSpec):
        raise ValueError("spec must be a LorentzianSweepSpec")
    if spec.point_count < 1 or spec.point_count > MAX_SWEEP_POINTS:
        raise ValueError(f"sweep point count must be at most {MAX_SWEEP_POINTS}")
    _bounded_reals(spec.f_pi_values, "f_pi_values")
    _bounded_reals(spec.e_values, "e_values")
    _bounded_reals(spec.damping_values, "damping_values", allow_zero=True)
    dt_values = _bounded_reals(spec.dt_values, "dt_values")
    final_time = _positive_real(spec.final_time, "final_time")
    for dt in dt_values:
        _steps_for(final_time, dt)
    max_snapshots = _bounded_integer(
        spec.max_saved_snapshots_per_point,
        "max_saved_snapshots_per_point",
        minimum=2,
        maximum=MAX_SWEEP_SNAPSHOTS_PER_POINT,
    )
    work_limit = _bounded_integer(
        spec.max_total_rk_stage_site_evaluations,
        "max_total_rk_stage_site_evaluations",
        minimum=1,
        maximum=MAX_SWEEP_RK_STAGE_SITE_EVALUATIONS,
    )
    record_limit = _bounded_integer(
        spec.max_total_record_site_visits,
        "max_total_record_site_visits",
        minimum=1,
        maximum=MAX_SWEEP_RECORD_SITE_VISITS,
    )
    damping_step_limit = _positive_real(
        spec.max_linearized_damping_step, "max_linearized_damping_step"
    )
    snapshot_limit = _bounded_integer(
        spec.max_snapshot_bytes_per_point,
        "max_snapshot_bytes_per_point",
        minimum=1,
        maximum=MAX_SWEEP_SNAPSHOT_BYTES_PER_POINT,
    )
    cfl_limit = _positive_real(spec.max_linearized_cfl, "max_linearized_cfl")
    velocity = _validate_velocity(initial, initial_velocity)
    spacing = validate_spacing(initial.spacing)
    n_sites = math.prod(initial.components.shape[:3])
    if n_sites > MAX_GRID_NODES:
        raise ValueError("field grid exceeds max_grid_nodes")
    requested_work = spec.rk_stage_site_work(n_sites)
    if requested_work > work_limit:
        raise ValueError(
            "requested sweep exceeds max_total_rk_stage_site_evaluations work budget"
        )
    requested_record_visits = spec.record_site_visits(n_sites)
    if requested_record_visits > record_limit:
        raise ValueError("requested sweep exceeds max_total_record_site_visits budget")
    for damping in spec.damping_values:
        for dt in dt_values:
            damping_step = damping * dt
            if not math.isfinite(damping_step) or damping_step > damping_step_limit:
                raise ValueError(
                    "a sweep damping*dt exceeds max_linearized_damping_step; "
                    "reduce damping or dt, or explicitly raise the declared limit"
                )
    for f_pi in spec.f_pi_values:
        for e in spec.e_values:
            for damping in spec.damping_values:
                for dt in dt_values:
                    scales = _scale_proxies(
                        initial, f_pi=f_pi, e=e, damping=damping, dt=dt
                    )
                    _dimensionless_initial_condition_proxies(
                        velocity, scales[0], final_time
                    )
    requested_snapshot_bytes = spec.snapshot_bytes(n_sites)
    if requested_snapshot_bytes > snapshot_limit:
        raise ValueError(
            "requested sweep point exceeds max_snapshot_bytes_per_point"
        )
    try:
        omega_max = 2.0 * math.hypot(*(1.0 / h for h in spacing))
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("spacing gives an unrepresentable vacuum frequency bound") from exc
    for dt in dt_values:
        cfl = dt * omega_max
        if not math.isfinite(cfl) or cfl > cfl_limit:
            raise ValueError(
                "a sweep dt exceeds max_linearized_cfl; remove that dt or "
                "explicitly raise the declared limit"
            )

    field_checksum = _field_checksum(initial)
    velocity_checksum = _array_checksum(velocity)
    points: list[LorentzianSweepPoint] = []
    for index, (f_pi, e, damping, dt) in enumerate(spec.point_parameters()):
        steps = spec.steps_for(dt)
        save_every = spec.save_every_for(dt)
        scales = _scale_proxies(
            initial, f_pi=f_pi, e=e, damping=damping, dt=dt
        )
        state_proxies = _dimensionless_initial_condition_proxies(
            velocity, scales[0], final_time
        )
        point_id = f"point-{index:04d}"
        try:
            trajectory = evolve_lorentzian_skyrme(
                initial,
                velocity.copy(),
                dt=dt,
                steps=steps,
                save_every=save_every,
                f_pi=f_pi,
                e=e,
                damping=damping,
                max_rk_stage_site_evaluations=work_limit,
                max_snapshots=max_snapshots,
                max_snapshot_bytes=snapshot_limit,
                max_linearized_cfl=cfl_limit,
            )
            _validate_trajectory_output(
                trajectory,
                initial=initial,
                f_pi=f_pi,
                e=e,
                damping=damping,
                dt=dt,
                steps=steps,
                save_every=save_every,
                final_time=final_time,
            )
            final_field_checksum = _array_checksum(trajectory.fields[-1].components)
        except Exception as exc:
            raise RuntimeError(
                f"trajectory sweep failed at {point_id} "
                f"(f_pi={f_pi:g}, e={e:g}, damping={damping:g}, dt={dt:g})"
            ) from exc
        points.append(
            LorentzianSweepPoint(
                point_id=point_id,
                f_pi=f_pi,
                e=e,
                damping=damping,
                dt=dt,
                steps=steps,
                final_time=final_time,
                save_every=save_every,
                linearized_cfl_indicator=trajectory.linearized_cfl_indicator,
                inverse_length_scale_proxy=scales[0],
                energy_prefactor_proxy=scales[1],
                dimensionless_spacing_proxy=scales[2],
                dimensionless_domain_extent_proxy=scales[3],
                dimensionless_dt_proxy=scales[4],
                dimensionless_damping_proxy=scales[5],
                dimensionless_final_time_proxy=state_proxies[0],
                dimensionless_initial_velocity_rms_proxy=state_proxies[1],
                dimensionless_initial_velocity_max_proxy=state_proxies[2],
                time_history=trajectory.time_history,
                energy_sigma_history=trajectory.energy_sigma_history,
                energy_skyrme_history=trajectory.energy_skyrme_history,
                kinetic_sigma_history=trajectory.kinetic_sigma_history,
                kinetic_skyrme_history=trajectory.kinetic_skyrme_history,
                total_energy_history=trajectory.total_energy_history,
                dissipated_energy_history=trajectory.dissipated_energy_history,
                energy_balance_residual_history=(
                    trajectory.energy_balance_residual_history
                ),
                approximate_charge_history=trajectory.approximate_charge_history,
                time_kinetic_min_eigenvalue_history=(
                    trajectory.time_kinetic_min_eigenvalue_history
                ),
                time_kinetic_max_condition_history=(
                    trajectory.time_kinetic_max_condition_history
                ),
                max_unit_norm_error=trajectory.max_unit_norm_error,
                max_tangency_error=trajectory.max_tangency_error,
                initial_field_checksum_sha256=field_checksum,
                initial_velocity_checksum_sha256=velocity_checksum,
                final_field_checksum_sha256=final_field_checksum,
                hyperbolicity_status=trajectory.hyperbolicity_status,
                termination=trajectory.termination,
            )
        )
        del trajectory

    return LorentzianSweepResult(
        sweep_id=_sweep_id(field_checksum, velocity_checksum, spec),
        initial_field_checksum_sha256=field_checksum,
        initial_velocity_checksum_sha256=velocity_checksum,
        input_shape=tuple(int(value) for value in initial.components.shape),
        spacing=tuple(float(value) for value in initial.spacing),
        boundary=initial.boundary,
        length_unit=initial.length_unit,
        spec=spec,
        points=tuple(points),
        python_version=platform.python_version(),
        numpy_version=np.__version__,
    )
