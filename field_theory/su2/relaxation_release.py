"""Bounded constrained-relaxation to cold Lorentzian release composition.

The optimizer's final field is handed directly to the Lorentzian solver.
Optimizer descent is not interpreted as physical velocity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Literal

import numpy as np

from .field import SU2GridField
from .lorentzian import evolve_lorentzian_skyrme
from .nearest_neighbor import (
    NearestNeighborRelaxationResult,
    compute_nearest_neighbor_diagnostics,
    relax_skyrme_field_nearest_neighbor,
)

AnchorPolicy = Literal["cold_release", "retain"]
_MAX_GRID_NODES = 32_768
_MAX_STEPS = 100_000
_MAX_SNAPSHOTS = 512
_MAX_RK_WORK = 40_000_000
_MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
_MAX_RELAX_ITERATIONS = 100
_MAX_BACKTRACKS = 12
_MAX_RELAX_NODE_VISITS = 75_000_000


@dataclass(frozen=True)
class RelaxationReleaseResult:
    """Compact finite-grid engineering record; trajectory snapshots are omitted."""

    schema_version: str
    status: str
    evidence_class: str
    data_mode: str
    scientific_pass: bool
    anchor_policy: AnchorPolicy
    fixed_site_count: int
    released_anchor_count: int
    outer_boundary_policy: str
    optimizer_velocity_handoff: str
    initial_velocity_max_abs: float
    relaxation_termination: str
    relaxation_stationarity_status: str
    relaxation_minimum_certified: bool
    relaxation_iterations: int
    relaxation_energy_history: tuple[float, ...]
    initial_static_potential_energy: float | None
    initial_lorentzian_total_energy: float | None
    initial_energy_difference: float | None
    time_history: tuple[float, ...]
    potential_energy_history: tuple[float, ...]
    kinetic_energy_history: tuple[float, ...]
    total_energy_history: tuple[float, ...]
    dissipated_energy_history: tuple[float, ...]
    energy_balance_residual_history: tuple[float, ...]
    approximate_charge_history: tuple[float, ...]
    approximate_charge_interpretation: str
    trajectory_termination: str
    input_field_sha256: str
    relaxed_field_sha256: str
    final_field_sha256: str | None
    dt: float
    steps: int
    save_every: int
    f_pi: float
    e: float
    damping: float
    spacing: tuple[float, float, float]
    boundary: str
    length_unit: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        _assert_finite_json(payload)
        return payload

    def to_json(self) -> str:
        """Serialize deterministically and reject NaN/Infinity."""
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def _strict_int(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return result


def _numeric_scalar(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a real numeric scalar")
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric scalar")
    result = float(raw)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_float(value: object, name: str) -> float:
    result = _numeric_scalar(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _nonnegative_float(value: object, name: str) -> float:
    result = _numeric_scalar(value, name)
    if result < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _outer_boundary_mask(shape: tuple[int, int, int]) -> np.ndarray:
    result = np.zeros(shape, dtype=bool)
    result[[0, -1], :, :] = True
    result[:, [0, -1], :] = True
    result[:, :, [0, -1]] = True
    return result


def _validate_anchor_mask(field: SU2GridField, fixed_mask: object | None) -> np.ndarray:
    shape = field.components.shape[:3]
    if fixed_mask is None:
        return np.zeros(shape, dtype=bool)
    raw = np.asarray(fixed_mask)
    if raw.dtype.kind != "b" or raw.shape != shape:
        raise ValueError("fixed_mask must be a boolean array matching the field grid")
    mask = np.array(raw, dtype=bool, copy=True)
    if field.boundary == "fixed_vacuum" and np.any(mask & _outer_boundary_mask(shape)):
        raise ValueError("fixed_mask may identify interior anchors only; outer faces are boundary-fixed")
    return mask


def _field_sha256(field: SU2GridField) -> str:
    metadata = {
        "shape": list(field.components.shape),
        "spacing": list(field.spacing),
        "boundary": field.boundary,
        "length_unit": field.length_unit,
        "dtype": "<f8",
    }
    digest = hashlib.sha256()
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\0")
    digest.update(np.ascontiguousarray(field.components, dtype="<f8").tobytes())
    return digest.hexdigest()


def _assert_finite_json(value: object) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, np.integer)):
        return
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            raise ValueError("result contains a non-finite numeric value")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _assert_finite_json(item)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _assert_finite_json(item)
        return
    raise ValueError(f"unsupported finite-JSON value: {type(value).__name__}")


def _preflight(
    field: SU2GridField,
    *,
    max_iterations: int,
    max_backtracks: int,
    steps: int,
    save_every: int,
    max_relaxation_node_visits: int,
    max_rk_stage_site_evaluations: int,
    max_snapshot_bytes: int,
) -> None:
    # Use Python integers for all products so overflow cannot weaken a budget.
    node_count = math.prod(int(size) for size in field.components.shape[:3])
    if node_count > _MAX_GRID_NODES:
        raise ValueError("field grid exceeds the bounded relaxation-release node limit")
    relax_visits = node_count * (1 + max_iterations * (max_backtracks + 2) + 40)
    if relax_visits > max_relaxation_node_visits:
        raise ValueError("relaxation exceeds max_relaxation_node_visits")
    rk_work = 4 * node_count * steps
    if rk_work > max_rk_stage_site_evaluations:
        raise ValueError("evolution exceeds max_rk_stage_site_evaluations")
    snapshots = 1 + steps // save_every + (1 if steps % save_every else 0)
    snapshot_bytes = snapshots * node_count * 4 * 8 * 2
    if snapshots > _MAX_SNAPSHOTS or snapshot_bytes > max_snapshot_bytes:
        raise ValueError("evolution exceeds the aggregate snapshot budget")


def _limitations() -> tuple[str, ...]:
    return (
        "synthetic dimensionless finite-grid engineering evidence only",
        "constrained first-order stationarity is not a minimum or stability certificate",
        "cold release starts at zero velocity; optimizer descent is not physical velocity",
        "finite fixed-vacuum boxes can reflect waves; analyze only before boundary returns",
        "trajectory diagnostics do not establish a stable soliton or physical binding energy",
        "no biological, consciousness, enlightenment, psi, or rebirth inference",
    )


def _withheld_result(
    *,
    status: str,
    anchor_policy: AnchorPolicy,
    fixed_site_count: int,
    released_anchor_count: int,
    input_checksum: str,
    relaxed_checksum: str,
    relaxation: NearestNeighborRelaxationResult,
    dt: float,
    steps: int,
    save_every: int,
    f_pi: float,
    e: float,
    damping: float,
    field: SU2GridField,
) -> RelaxationReleaseResult:
    return RelaxationReleaseResult(
        schema_version="su2_relaxation_release_v1",
        status=status,
        evidence_class="engineering_synthetic_solver_composition",
        data_mode="synthetic_dimensionless",
        scientific_pass=False,
        anchor_policy=anchor_policy,
        fixed_site_count=fixed_site_count,
        released_anchor_count=released_anchor_count,
        outer_boundary_policy="fixed_vacuum_outer_faces_remain_clamped",
        optimizer_velocity_handoff="none_optimizer_descent_is_not_velocity",
        initial_velocity_max_abs=0.0,
        relaxation_termination=relaxation.termination,
        relaxation_stationarity_status=relaxation.stationarity_status,
        relaxation_minimum_certified=bool(relaxation.minimum_certified),
        relaxation_iterations=int(relaxation.iterations),
        relaxation_energy_history=tuple(float(x) for x in relaxation.energy_history),
        initial_static_potential_energy=None,
        initial_lorentzian_total_energy=None,
        initial_energy_difference=None,
        time_history=(),
        potential_energy_history=(),
        kinetic_energy_history=(),
        total_energy_history=(),
        dissipated_energy_history=(),
        energy_balance_residual_history=(),
        approximate_charge_history=(),
        approximate_charge_interpretation=(
            "approximate lattice degree diagnostic; not rounded to an integer; "
            "no conservation is asserted"
        ),
        trajectory_termination="not_run",
        input_field_sha256=input_checksum,
        relaxed_field_sha256=relaxed_checksum,
        final_field_sha256=None,
        dt=dt,
        steps=steps,
        save_every=save_every,
        f_pi=f_pi,
        e=e,
        damping=damping,
        spacing=tuple(float(x) for x in field.spacing),
        boundary=field.boundary,
        length_unit=field.length_unit,
        limitations=_limitations(),
    )


def run_relaxation_then_cold_release(
    initial_field: SU2GridField,
    *,
    fixed_mask: object | None = None,
    anchor_policy: AnchorPolicy = "cold_release",
    f_pi: object = 1.0,
    e: object = 1.0,
    max_iterations: object = 2,
    initial_step: object = 1.0e-3,
    gradient_tolerance: object = 1.0e-7,
    max_backtracks: object = 4,
    stationarity_metric: str = "euclidean",
    descent_metric: str = "euclidean",
    dt: object = 1.0e-3,
    steps: object = 2,
    save_every: object = 1,
    damping: object = 0.0,
    allow_nonconverged: bool = False,
    max_relaxation_node_visits: object = _MAX_RELAX_NODE_VISITS,
    max_rk_stage_site_evaluations: object = _MAX_RK_WORK,
    max_snapshot_bytes: object = _MAX_SNAPSHOT_BYTES,
) -> RelaxationReleaseResult:
    """Relax one field, then explicitly release or retain interior anchors.

    The final in-memory optimizer field is handed directly to Lorentzian
    evolution; relaxation is never repeated. Cold release removes only the
    supplied interior mask. Fixed-vacuum outer faces remain clamped. A zero
    velocity starts dynamics independently of the optimizer's descent path.
    """
    if not isinstance(initial_field, SU2GridField):
        raise ValueError("initial_field must be an SU2GridField")
    if initial_field.boundary != "fixed_vacuum":
        raise ValueError("this composition requires fixed_vacuum outer boundaries")
    if initial_field.length_unit != "dimensionless":
        raise ValueError("this engineering runner accepts dimensionless fields only")
    if not isinstance(allow_nonconverged, bool):
        raise ValueError("allow_nonconverged must be boolean")
    if anchor_policy not in ("cold_release", "retain"):
        raise ValueError("anchor_policy must be 'cold_release' or 'retain'")

    f_value = _positive_float(f_pi, "f_pi")
    e_value = _positive_float(e, "e")
    step = _positive_float(dt, "dt")
    optimizer_step = _positive_float(initial_step, "initial_step")
    tolerance = _positive_float(gradient_tolerance, "gradient_tolerance")
    gamma = _nonnegative_float(damping, "damping")
    n_steps = _strict_int(steps, "steps", minimum=1, maximum=_MAX_STEPS)
    stride = _strict_int(save_every, "save_every", minimum=1, maximum=n_steps)
    iterations = _strict_int(max_iterations, "max_iterations", minimum=1, maximum=_MAX_RELAX_ITERATIONS)
    backtracks = _strict_int(max_backtracks, "max_backtracks", minimum=0, maximum=_MAX_BACKTRACKS)
    relax_budget = _strict_int(
        max_relaxation_node_visits, "max_relaxation_node_visits",
        minimum=1, maximum=_MAX_RELAX_NODE_VISITS,
    )
    rk_budget = _strict_int(
        max_rk_stage_site_evaluations, "max_rk_stage_site_evaluations",
        minimum=1, maximum=_MAX_RK_WORK,
    )
    snapshot_budget = _strict_int(
        max_snapshot_bytes, "max_snapshot_bytes",
        minimum=1, maximum=_MAX_SNAPSHOT_BYTES,
    )
    if stationarity_metric not in ("euclidean", "continuum_l2"):
        raise ValueError("unsupported stationarity_metric")
    if descent_metric not in ("euclidean", "continuum_l2"):
        raise ValueError("unsupported descent_metric")

    mask = _validate_anchor_mask(initial_field, fixed_mask)
    _preflight(
        initial_field,
        max_iterations=iterations,
        max_backtracks=backtracks,
        steps=n_steps,
        save_every=stride,
        max_relaxation_node_visits=relax_budget,
        max_rk_stage_site_evaluations=rk_budget,
        max_snapshot_bytes=snapshot_budget,
    )
    input_checksum = _field_sha256(initial_field)

    # One optimization call; use its returned field directly below.
    relaxed = relax_skyrme_field_nearest_neighbor(
        initial_field,
        f_pi=f_value,
        e=e_value,
        max_iterations=iterations,
        initial_step=optimizer_step,
        gradient_tolerance=tolerance,
        max_backtracks=backtracks,
        fixed_mask=mask,
        stationarity_metric=stationarity_metric,
        descent_metric=descent_metric,
    )
    converged = (
        relaxed.termination == "gradient_tolerance"
        and relaxed.stationarity_status == "first_order_stationary"
    )
    released = int(np.count_nonzero(mask)) if anchor_policy == "cold_release" else 0
    if not converged and not allow_nonconverged:
        result = _withheld_result(
            status="NOT_CONVERGED",
            anchor_policy=anchor_policy,
            fixed_site_count=int(np.count_nonzero(mask)),
            released_anchor_count=0,
            input_checksum=input_checksum,
            relaxed_checksum=_field_sha256(relaxed.field),
            relaxation=relaxed,
            dt=step,
            steps=n_steps,
            save_every=stride,
            f_pi=f_value,
            e=e_value,
            damping=gamma,
            field=initial_field,
        )
        result.to_json()
        return result

    dynamics_mask = mask if anchor_policy == "retain" else None
    zero_velocity = np.zeros_like(relaxed.field.components, dtype=np.float64)
    trajectory = evolve_lorentzian_skyrme(
        relaxed.field,
        zero_velocity,
        dt=step,
        steps=n_steps,
        save_every=stride,
        f_pi=f_value,
        e=e_value,
        damping=gamma,
        fixed_mask=dynamics_mask,
        max_grid_nodes=_MAX_GRID_NODES,
        max_steps=_MAX_STEPS,
        max_rk_stage_site_evaluations=rk_budget,
        max_snapshots=_MAX_SNAPSHOTS,
        max_snapshot_bytes=snapshot_budget,
    )
    static = compute_nearest_neighbor_diagnostics(trajectory.fields[0], f_pi=f_value, e=e_value)
    initial_lorentzian = float(trajectory.total_energy_history[0])
    difference = initial_lorentzian - float(static.energy_total)
    if initial_lorentzian != float(static.energy_total):
        raise FloatingPointError("zero-velocity Lorentzian energy must equal matched static energy")
    histories = (
        trajectory.time_history,
        trajectory.energy_sigma_history,
        trajectory.energy_skyrme_history,
        trajectory.kinetic_sigma_history,
        trajectory.kinetic_skyrme_history,
        trajectory.total_energy_history,
        trajectory.dissipated_energy_history,
        trajectory.energy_balance_residual_history,
        trajectory.approximate_charge_history,
    )
    if any(not all(math.isfinite(float(value)) for value in series) for series in histories):
        raise FloatingPointError("solver returned a non-finite trajectory diagnostic")
    potential = tuple(float(a + b) for a, b in zip(
        trajectory.energy_sigma_history, trajectory.energy_skyrme_history
    ))
    kinetic = tuple(float(a + b) for a, b in zip(
        trajectory.kinetic_sigma_history, trajectory.kinetic_skyrme_history
    ))
    status = "COMPLETED" if converged else "NOT_CONVERGED_EXPLORATORY_CONTINUATION"
    result = RelaxationReleaseResult(
        schema_version="su2_relaxation_release_v1",
        status=status,
        evidence_class="engineering_synthetic_solver_composition",
        data_mode="synthetic_dimensionless",
        scientific_pass=False,
        anchor_policy=anchor_policy,
        fixed_site_count=int(np.count_nonzero(mask)),
        released_anchor_count=released,
        outer_boundary_policy="fixed_vacuum_outer_faces_remain_clamped",
        optimizer_velocity_handoff="none_optimizer_descent_is_not_velocity",
        initial_velocity_max_abs=0.0,
        relaxation_termination=relaxed.termination,
        relaxation_stationarity_status=relaxed.stationarity_status,
        relaxation_minimum_certified=bool(relaxed.minimum_certified),
        relaxation_iterations=int(relaxed.iterations),
        relaxation_energy_history=tuple(float(x) for x in relaxed.energy_history),
        initial_static_potential_energy=float(static.energy_total),
        initial_lorentzian_total_energy=initial_lorentzian,
        initial_energy_difference=float(difference),
        time_history=tuple(float(x) for x in trajectory.time_history),
        potential_energy_history=potential,
        kinetic_energy_history=kinetic,
        total_energy_history=tuple(float(x) for x in trajectory.total_energy_history),
        dissipated_energy_history=tuple(float(x) for x in trajectory.dissipated_energy_history),
        energy_balance_residual_history=tuple(float(x) for x in trajectory.energy_balance_residual_history),
        approximate_charge_history=tuple(float(x) for x in trajectory.approximate_charge_history),
        approximate_charge_interpretation=(
            "approximate lattice degree diagnostic; not rounded to an integer; "
            "no conservation is asserted"
        ),
        trajectory_termination=trajectory.termination,
        input_field_sha256=input_checksum,
        relaxed_field_sha256=_field_sha256(relaxed.field),
        final_field_sha256=_field_sha256(trajectory.fields[-1]),
        dt=step,
        steps=n_steps,
        save_every=stride,
        f_pi=f_value,
        e=e_value,
        damping=gamma,
        spacing=tuple(float(x) for x in relaxed.field.spacing),
        boundary=relaxed.field.boundary,
        length_unit=relaxed.field.length_unit,
        limitations=_limitations(),
    )
    result.to_json()
    return result
