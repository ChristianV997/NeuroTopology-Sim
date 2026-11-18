"""Full Lorentzian SU(2) Skyrme evolution on a finite S3 lattice.

The field is represented by unit four-vectors ``n=(sigma, pi_1, pi_2, pi_3)``
with ``U=sigma I+i pi.sigma``.  The semidiscrete action keeps both parts of
the quartic Skyrme term: the static spatial ``E4`` potential and the
velocity-dependent time-space term.  It is therefore distinct from the
sigma-kinetic / Skyrme-potential toy evolution in the earlier dynamics
prototype.

With metric (+---), forward-link derivatives ``g_i=D_i n`` and tangent
velocity ``v=dn/dt``, the discrete Lagrangian density is

    L = F_pi^2/8 (|v|^2 - sum_i |g_i|^2)
        +1/(2 e^2) [sum_i (|v|^2 |g_i|^2 - (v.g_i)^2)
                    - sum_{i<j} (|g_i|^2 |g_j|^2 - (g_i.g_j)^2)].

Its local velocity Hessian is

    M = F_pi^2/4 I + 1/e^2 sum_i (|g_i|^2 I - g_i g_i^T),

so ``T=1/2 v^T M v``.  The constrained Euler-Lagrange update includes the
spatial-neighbor derivative of this metric, ``dot(M) v``, the derivative of
the kinetic energy with respect to neighboring field values, and the
holonomic S3 multiplier.  The implementation uses projected classical RK4;
it is a bounded exploratory integrator, not an exact symplectic scheme.

Coordinates and couplings are dimensionless unless a caller supplies a
separately validated conversion.  The local time-kinetic Hessian is checked,
but this does not prove strong hyperbolicity or causal propagation for the
full nonlinear Skyrme equations.  No biological or consciousness inference
follows from a numerical trajectory.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np

from .field import SU2GridField, validate_spacing
from .nearest_neighbor import (
    compute_nearest_neighbor_diagnostics,
    nearest_neighbor_energy_gradient,
)


_MODEL = "full_lorentzian_skyrme_forward_link_v1"
_MAX_GRID_NODES = 32_768
_MAX_STEPS = 100_000
_MAX_SNAPSHOTS = 512
_MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
_TANGENCY_TOLERANCE = 1.0e-9


@dataclass(frozen=True)
class LorentzianSkyrmeDiagnostics:
    """Finite-grid Hamiltonian terms for one field/velocity pair."""

    energy_sigma: float
    energy_skyrme: float
    kinetic_sigma: float
    kinetic_skyrme: float
    potential_energy: float
    kinetic_energy: float
    total_energy: float
    approximate_topological_charge: float
    time_kinetic_min_eigenvalue: float
    time_kinetic_max_condition: float


@dataclass(frozen=True)
class LorentzianSkyrmeTrajectory:
    """Bounded trajectory snapshots and finite-grid conservation diagnostics."""

    model: str
    fields: tuple[SU2GridField, ...]
    velocities: tuple[np.ndarray, ...]
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
    dt: float
    steps: int
    save_every: int
    f_pi: float
    e: float
    damping: float
    cell_volume: float
    linearized_cfl_indicator: float
    hyperbolicity_status: Literal["not_certified"]
    termination: Literal["completed"]


def _real_scalar(
    value: object,
    name: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric scalar")
    number = float(raw)
    valid = np.isfinite(number)
    if positive:
        valid = valid and number > 0.0
    if nonnegative:
        valid = valid and number >= 0.0
    if not valid:
        qualifier = (
            "finite and positive" if positive
            else "finite and nonnegative" if nonnegative
            else "finite"
        )
        raise ValueError(f"{name} must be {qualifier}")
    return number


def _integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def _cell_volume(spacing: tuple[float, float, float]) -> float:
    mantissa = 1.0
    exponent = 0
    for side in spacing:
        part, part_exponent = math.frexp(float(side))
        mantissa *= part
        exponent += part_exponent
        mantissa, adjust = math.frexp(mantissa)
        exponent += adjust
    try:
        value = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError(
            "grid spacing must produce a finite positive cell volume"
        ) from exc
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("grid spacing must produce a finite positive cell volume")
    return value


def _fixed_sites(
    field: SU2GridField, fixed_mask: object | None
) -> tuple[np.ndarray, np.ndarray]:
    shape = field.components.shape[:3]
    fixed = np.zeros(shape, dtype=bool)
    if field.boundary == "fixed_vacuum":
        fixed[[0, -1], :, :] = True
        fixed[:, [0, -1], :] = True
        fixed[:, :, [0, -1]] = True
    elif field.boundary != "periodic":
        raise ValueError("unsupported SU2 boundary condition")
    if fixed_mask is not None:
        supplied = np.asarray(fixed_mask)
        if supplied.dtype.kind != "b" or supplied.shape != shape:
            raise ValueError("fixed_mask must be boolean and match the field grid")
        fixed |= supplied
    if np.all(fixed):
        raise ValueError("the field has no active dynamical sites")
    return fixed, ~fixed


def _project_state(
    values: np.ndarray,
    velocity: np.ndarray,
    *,
    fixed: np.ndarray,
    fixed_values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    q = np.asarray(values, dtype=np.float64).copy()
    v = np.asarray(velocity, dtype=np.float64).copy()
    if not np.all(np.isfinite(q)) or not np.all(np.isfinite(v)):
        raise FloatingPointError("non-finite field or velocity during evolution")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        scale = np.max(np.abs(q), axis=-1, keepdims=True)
        if np.any(scale <= 0.0) or not np.all(np.isfinite(scale)):
            raise FloatingPointError("cannot project a zero or invalid field vector onto S3")
        scaled = q / scale
        norm = scale * np.sqrt(np.sum(scaled * scaled, axis=-1, keepdims=True))
        if np.any(norm <= 0.0) or not np.all(np.isfinite(norm)):
            raise FloatingPointError("field-vector norm is not representable")
        q /= norm
        q[fixed] = fixed_values[fixed]
        v -= q * np.sum(q * v, axis=-1, keepdims=True)
        v[fixed] = 0.0
    if not np.all(np.isfinite(q)) or not np.all(np.isfinite(v)):
        raise FloatingPointError("S3 projection produced a non-finite state")
    return q, v


def _validate_initial_velocity(
    field: SU2GridField,
    initial_velocity: object,
    *,
    fixed: np.ndarray,
    active: np.ndarray,
    tolerance: float = _TANGENCY_TOLERANCE,
) -> np.ndarray:
    raw = np.asarray(initial_velocity)
    if raw.dtype.kind not in "fiu" or raw.shape != field.components.shape:
        raise ValueError("initial_velocity must be a real array matching field.components")
    velocity = np.asarray(raw, dtype=np.float64).copy()
    if not np.all(np.isfinite(velocity)):
        raise ValueError("initial_velocity must be finite")
    try:
        with np.errstate(over="raise", invalid="raise"):
            speed = np.hypot.reduce(np.abs(velocity), axis=-1)
            tangent_error = np.abs(
                np.sum(field.components * velocity, axis=-1)
            )
    except FloatingPointError as exc:
        raise ValueError("initial_velocity magnitude is not representable") from exc
    if not np.all(np.isfinite(speed)) or not np.all(np.isfinite(tangent_error)):
        raise ValueError("initial_velocity magnitude must be representable")
    scale = max(1.0, float(np.max(speed)))
    if float(np.max(tangent_error)) > tolerance * scale:
        raise ValueError("initial_velocity must be tangent to S3 at every site")
    if np.any(speed[fixed] > tolerance * scale):
        raise ValueError("initial_velocity must be zero at frozen sites")
    velocity -= field.components * np.sum(
        field.components * velocity, axis=-1, keepdims=True
    )
    velocity[~active] = 0.0
    return velocity


def _forward_derivatives(
    values: np.ndarray,
    spacing: tuple[float, float, float],
    boundary: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    result = []
    for axis, step in enumerate(spacing):
        difference = np.roll(values, -1, axis=axis) - values
        if boundary == "fixed_vacuum":
            selector = [slice(None)] * 4
            selector[axis] = -1
            difference[tuple(selector)] = 0.0
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            derivative = difference / step
        if not np.all(np.isfinite(derivative)):
            raise FloatingPointError("non-finite forward-link derivative")
        result.append(derivative)
    return tuple(result)  # type: ignore[return-value]


def _time_kinetic_matrix(
    gradients: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    f_pi: float,
    e: float,
) -> np.ndarray:
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        identity = np.eye(4, dtype=np.float64)
        matrix = np.broadcast_to(
            (f_pi * f_pi / 4.0) * identity,
            gradients[0].shape[:-1] + (4, 4),
        ).copy()
        inverse_e2 = 1.0 / (e * e)
        for gradient in gradients:
            norm2 = np.sum(gradient * gradient, axis=-1)
            outer = np.einsum("...a,...b->...ab", gradient, gradient)
            matrix += inverse_e2 * (
                norm2[..., None, None] * identity - outer
            )
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError("non-finite Lorentzian time-kinetic matrix")
    return matrix


def _kinetic_terms(
    velocity: np.ndarray,
    gradients: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    f_pi: float,
    e: float,
    cell_volume: float,
) -> tuple[float, float]:
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        kinetic_sigma = (f_pi * f_pi / 8.0) * cell_volume * float(
            np.sum(velocity * velocity)
        )
        kinetic_skyrme = 0.0
        v2 = np.sum(velocity * velocity, axis=-1)
        for gradient in gradients:
            g2 = np.sum(gradient * gradient, axis=-1)
            vg = np.sum(velocity * gradient, axis=-1)
            wedge2 = v2 * g2 - vg * vg
            # Tiny negative values can only arise from cancellation in the
            # Gram determinant; tolerate roundoff but reject substantive loss
            # of positive semidefiniteness.
            tolerance = 64.0 * np.finfo(np.float64).eps * np.maximum(v2 * g2, 1.0)
            if np.any(wedge2 < -tolerance):
                raise FloatingPointError("time-space Skyrme Gram determinant became negative")
            wedge2 = np.maximum(wedge2, 0.0)
            kinetic_skyrme += (cell_volume / (2.0 * e * e)) * float(np.sum(wedge2))
    if not np.isfinite(kinetic_sigma) or not np.isfinite(kinetic_skyrme):
        raise FloatingPointError("non-finite Lorentzian kinetic energy")
    return kinetic_sigma, kinetic_skyrme


def _mass_action(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    return np.einsum("...ij,...j->...i", matrix, vector)


def compute_lorentzian_diagnostics(
    field: SU2GridField,
    velocity: object,
    *,
    f_pi: float = 1.0,
    e: float = 1.0,
    fixed_mask: np.ndarray | None = None,
) -> LorentzianSkyrmeDiagnostics:
    """Compute the full finite-grid Hamiltonian, including quartic time terms."""
    f_value = _real_scalar(f_pi, "f_pi", positive=True)
    e_value = _real_scalar(e, "e", positive=True)
    spacing = validate_spacing(field.spacing)
    fixed, active = _fixed_sites(field, fixed_mask)
    v = _validate_initial_velocity(field, velocity, fixed=fixed, active=active)
    gradients = _forward_derivatives(field.components, spacing, field.boundary)
    volume = _cell_volume(spacing)
    potential = compute_nearest_neighbor_diagnostics(
        field, f_pi=f_value, e=e_value
    )
    kinetic_sigma, kinetic_skyrme = _kinetic_terms(
        v, gradients, f_pi=f_value, e=e_value, cell_volume=volume
    )
    matrix = _time_kinetic_matrix(gradients, f_pi=f_value, e=e_value)
    eigenvalues = np.linalg.eigvalsh(matrix[active])
    minimum = float(np.min(eigenvalues))
    maximum_condition = float(np.max(eigenvalues[:, -1] / eigenvalues[:, 0]))
    kinetic_total = kinetic_sigma + kinetic_skyrme
    potential_total = potential.energy_sigma + potential.energy_skyrme
    total = kinetic_total + potential_total
    all_values = (
        kinetic_sigma,
        kinetic_skyrme,
        potential_total,
        kinetic_total,
        total,
        minimum,
        maximum_condition,
        potential.topological_charge,
    )
    if not np.all(np.isfinite(all_values)) or minimum <= 0.0:
        raise FloatingPointError("Lorentzian energy or time-kinetic metric is invalid")
    return LorentzianSkyrmeDiagnostics(
        energy_sigma=float(potential.energy_sigma),
        energy_skyrme=float(potential.energy_skyrme),
        kinetic_sigma=float(kinetic_sigma),
        kinetic_skyrme=float(kinetic_skyrme),
        potential_energy=float(potential_total),
        kinetic_energy=float(kinetic_total),
        total_energy=float(total),
        approximate_topological_charge=float(potential.topological_charge),
        time_kinetic_min_eigenvalue=minimum,
        time_kinetic_max_condition=maximum_condition,
    )


def linearized_lattice_frequency(
    *,
    spacing: tuple[float, float, float],
    wave_number: tuple[float, float, float],
) -> float:
    """Vacuum dispersion for the matched forward-link E2/full sigma kinetic.

    ``omega^2 = 4 sum_i sin(k_i h_i/2)^2 / h_i^2``.  The quartic Skyrme term
    is fourth order in small pion amplitude and does not enter this limit.
    """
    h = validate_spacing(spacing)
    raw = np.asarray(wave_number)
    if raw.shape != (3,) or raw.dtype.kind not in "fiu" or not np.all(np.isfinite(raw)):
        raise ValueError("wave_number must be a finite real triple")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        omega2 = sum(
            4.0 * np.sin(float(k_i) * h_i / 2.0) ** 2 / (h_i * h_i)
            for k_i, h_i in zip(raw, h)
        )
        omega = math.sqrt(float(omega2))
    if not np.isfinite(omega):
        raise FloatingPointError("linearized lattice frequency is non-finite")
    return omega


def _acceleration_and_dissipation(
    field: SU2GridField,
    velocity: np.ndarray,
    *,
    f_pi: float,
    e: float,
    damping: float,
    fixed_mask: np.ndarray | None,
    active: np.ndarray,
    cell_volume: float,
) -> tuple[np.ndarray, float, float, float]:
    q = field.components
    spacing = validate_spacing(field.spacing)
    gradients = _forward_derivatives(q, spacing, field.boundary)
    gradient_velocities = _forward_derivatives(velocity, spacing, field.boundary)
    matrix = _time_kinetic_matrix(gradients, f_pi=f_pi, e=e)
    inverse_e2 = 1.0 / (e * e)

    # dM/dt acting on v, including the quartic time-space contribution.
    with np.errstate(over="raise", invalid="raise"):
        matrix_rate_v = np.zeros_like(velocity)
        kinetic_field_gradient = np.zeros_like(velocity)
        v2 = np.sum(velocity * velocity, axis=-1, keepdims=True)
        for gradient, gradient_rate, axis, step in zip(
            gradients, gradient_velocities, range(3), spacing
        ):
            gv = np.sum(gradient * velocity, axis=-1, keepdims=True)
            gdot_v = np.sum(gradient_rate * velocity, axis=-1, keepdims=True)
            g_gdot = np.sum(gradient * gradient_rate, axis=-1, keepdims=True)
            matrix_rate_v += inverse_e2 * (
                2.0 * g_gdot * velocity
                - gradient_rate * gv
                - gradient * gdot_v
            )

            local_derivative = inverse_e2 * (
                v2 * gradient - gv * velocity
            )
            if field.boundary == "fixed_vacuum":
                selector = [slice(None)] * 4
                selector[axis] = -1
                local_derivative[tuple(selector)] = 0.0
            kinetic_field_gradient += (
                np.roll(local_derivative, 1, axis=axis) - local_derivative
            ) / step

    if not np.all(np.isfinite(matrix_rate_v)) or not np.all(
        np.isfinite(kinetic_field_gradient)
    ):
        raise FloatingPointError("non-finite quartic kinetic force")

    potential_gradient = nearest_neighbor_energy_gradient(
        field,
        f_pi=f_pi,
        e=e,
        fixed_mask=fixed_mask,
    ) / cell_volume
    mass_velocity = _mass_action(matrix, velocity)
    force = (
        kinetic_field_gradient
        - matrix_rate_v
        - potential_gradient
        - damping * mass_velocity
    )

    try:
        inverse_mass_force = np.linalg.solve(matrix, force[..., None])[..., 0]
        inverse_mass_normal = np.linalg.solve(matrix, q[..., None])[..., 0]
    except np.linalg.LinAlgError as exc:
        raise FloatingPointError("singular local Lorentzian kinetic metric") from exc
    denominator = np.sum(q * inverse_mass_normal, axis=-1)
    if np.any(denominator[active] <= 0.0) or not np.all(np.isfinite(denominator[active])):
        raise FloatingPointError("invalid S3 constraint multiplier denominator")
    multiplier = (
        -np.sum(velocity * velocity, axis=-1)
        - np.sum(q * inverse_mass_force, axis=-1)
    ) / denominator
    acceleration = inverse_mass_force + multiplier[..., None] * inverse_mass_normal
    acceleration[~active] = 0.0

    eigenvalues = np.linalg.eigvalsh(matrix[active])
    min_eigenvalue = float(np.min(eigenvalues))
    max_condition = float(np.max(eigenvalues[:, -1] / eigenvalues[:, 0]))
    dissipation_rate = damping * cell_volume * float(
        np.sum(velocity[active] * mass_velocity[active])
    )
    if (
        not np.all(np.isfinite(acceleration))
        or not np.isfinite(dissipation_rate)
        or dissipation_rate < -1.0e-12
        or min_eigenvalue <= 0.0
        or not np.isfinite(max_condition)
    ):
        raise FloatingPointError("invalid Lorentzian acceleration or dissipation rate")
    return acceleration, max(0.0, dissipation_rate), min_eigenvalue, max_condition


def evolve_lorentzian_skyrme(
    field: SU2GridField,
    initial_velocity: object,
    *,
    dt: float,
    steps: int,
    save_every: int = 1,
    f_pi: float = 1.0,
    e: float = 1.0,
    damping: float = 0.0,
    fixed_mask: np.ndarray | None = None,
    max_grid_nodes: int = _MAX_GRID_NODES,
    max_steps: int = _MAX_STEPS,
    max_snapshots: int = _MAX_SNAPSHOTS,
    max_snapshot_bytes: int = _MAX_SNAPSHOT_BYTES,
    max_linearized_cfl: float = 2.5,
) -> LorentzianSkyrmeTrajectory:
    """Evolve the full finite-grid Lorentzian Skyrme equations with RK4.

    The explicit RK4 method is bounded by preflight node/step/snapshot caps and
    a vacuum-linearized CFL indicator.  The CFL check is not a nonlinear
    hyperbolicity or stability certificate.  Numerical breakdown fails
    closed with ``FloatingPointError`` rather than returning a partial
    trajectory as if it completed.
    """
    step = _real_scalar(dt, "dt", positive=True)
    f_value = _real_scalar(f_pi, "f_pi", positive=True)
    e_value = _real_scalar(e, "e", positive=True)
    gamma = _real_scalar(damping, "damping", nonnegative=True)
    node_cap = _integer(max_grid_nodes, "max_grid_nodes", minimum=1, maximum=_MAX_GRID_NODES)
    step_cap = _integer(max_steps, "max_steps", minimum=1, maximum=_MAX_STEPS)
    snapshot_cap = _integer(max_snapshots, "max_snapshots", minimum=1, maximum=_MAX_SNAPSHOTS)
    byte_cap = _integer(
        max_snapshot_bytes,
        "max_snapshot_bytes",
        minimum=1,
        maximum=2**31,
    )
    n_steps = _integer(steps, "steps", minimum=1, maximum=step_cap)
    stride = _integer(save_every, "save_every", minimum=1, maximum=n_steps)
    cfl_cap = _real_scalar(max_linearized_cfl, "max_linearized_cfl", positive=True)
    spacing = validate_spacing(field.spacing)
    volume = _cell_volume(spacing)
    n_sites = int(np.prod(field.components.shape[:3], dtype=np.int64))
    if n_sites > node_cap:
        raise ValueError("field grid exceeds max_grid_nodes")
    fixed, active = _fixed_sites(field, fixed_mask)
    velocity = _validate_initial_velocity(
        field, initial_velocity, fixed=fixed, active=active
    )
    number_saved = 1 + n_steps // stride + (1 if n_steps % stride else 0)
    snapshot_bytes = number_saved * n_sites * 4 * np.dtype(np.float64).itemsize * 2
    if number_saved > snapshot_cap:
        raise ValueError("requested trajectory exceeds max_snapshots")
    if snapshot_bytes > byte_cap:
        raise ValueError("requested trajectory exceeds max_snapshot_bytes")

    try:
        omega_max = 2.0 * math.hypot(*(1.0 / h for h in spacing))
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("spacing gives an unrepresentable vacuum frequency bound") from exc
    cfl_indicator = step * omega_max
    if not np.isfinite(cfl_indicator) or cfl_indicator > cfl_cap:
        raise ValueError(
            "dt exceeds the declared vacuum-linearized RK4 CFL indicator; "
            "reduce dt or explicitly raise max_linearized_cfl"
        )

    values = np.asarray(field.components, dtype=np.float64).copy()
    fixed_values = values.copy()
    values, velocity = _project_state(
        values, velocity, fixed=fixed, fixed_values=fixed_values
    )
    times: list[float] = []
    fields: list[SU2GridField] = []
    velocities: list[np.ndarray] = []
    energy_sigma: list[float] = []
    energy_skyrme: list[float] = []
    kinetic_sigma: list[float] = []
    kinetic_skyrme: list[float] = []
    total_energy: list[float] = []
    dissipated: list[float] = []
    energy_balance: list[float] = []
    charge: list[float] = []
    min_eigenvalue: list[float] = []
    max_condition: list[float] = []
    max_unit_error = 0.0
    max_tangent_error = 0.0
    dissipated_energy = 0.0
    initial_energy: float | None = None

    def project(q: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return _project_state(q, v, fixed=fixed, fixed_values=fixed_values)

    def evaluate(q: np.ndarray, v: np.ndarray):
        q_eval, v_eval = project(q, v)
        current = SU2GridField(
            q_eval,
            spacing=spacing,
            boundary=field.boundary,
            length_unit=field.length_unit,
        )
        acceleration, diss_rate, min_mass, max_cond = _acceleration_and_dissipation(
            current,
            v_eval,
            f_pi=f_value,
            e=e_value,
            damping=gamma,
            fixed_mask=fixed_mask,
            active=active,
            cell_volume=volume,
        )
        return v_eval, acceleration, diss_rate, min_mass, max_cond

    def record(time_value: float, q: np.ndarray, v: np.ndarray, d_value: float) -> None:
        nonlocal initial_energy, max_unit_error, max_tangent_error
        q, v = project(q, v)
        current = SU2GridField(
            q,
            spacing=spacing,
            boundary=field.boundary,
            length_unit=field.length_unit,
        )
        diagnostics = compute_lorentzian_diagnostics(
            current, v, f_pi=f_value, e=e_value, fixed_mask=fixed_mask
        )
        if initial_energy is None:
            initial_energy = diagnostics.total_energy
        residual = diagnostics.total_energy + d_value - initial_energy
        norm_error = float(np.max(np.abs(np.sum(q * q, axis=-1) - 1.0)))
        tangent_error = float(np.max(np.abs(np.sum(q * v, axis=-1))))
        if not np.all(np.isfinite((time_value, d_value, residual, norm_error, tangent_error))):
            raise FloatingPointError("non-finite trajectory snapshot diagnostic")
        times.append(float(time_value))
        fields.append(current)
        velocities.append(np.frombuffer(v.tobytes(), dtype=np.float64).reshape(v.shape))
        energy_sigma.append(diagnostics.energy_sigma)
        energy_skyrme.append(diagnostics.energy_skyrme)
        kinetic_sigma.append(diagnostics.kinetic_sigma)
        kinetic_skyrme.append(diagnostics.kinetic_skyrme)
        total_energy.append(diagnostics.total_energy)
        dissipated.append(float(d_value))
        energy_balance.append(float(residual))
        charge.append(diagnostics.approximate_topological_charge)
        min_eigenvalue.append(diagnostics.time_kinetic_min_eigenvalue)
        max_condition.append(diagnostics.time_kinetic_max_condition)
        max_unit_error = max(max_unit_error, norm_error)
        max_tangent_error = max(max_tangent_error, tangent_error)

    record(0.0, values, velocity, dissipated_energy)
    try:
        for index in range(1, n_steps + 1):
            k1q, k1v, k1d, _, _ = evaluate(values, velocity)
            q2, v2 = project(values + 0.5 * step * k1q, velocity + 0.5 * step * k1v)
            k2q, k2v, k2d, _, _ = evaluate(q2, v2)
            q3, v3 = project(values + 0.5 * step * k2q, velocity + 0.5 * step * k2v)
            k3q, k3v, k3d, _, _ = evaluate(q3, v3)
            q4, v4 = project(values + step * k3q, velocity + step * k3v)
            k4q, k4v, k4d, _, _ = evaluate(q4, v4)
            values, velocity = project(
                values + (step / 6.0) * (k1q + 2.0 * k2q + 2.0 * k3q + k4q),
                velocity + (step / 6.0) * (k1v + 2.0 * k2v + 2.0 * k3v + k4v),
            )
            dissipated_energy += (step / 6.0) * (
                k1d + 2.0 * k2d + 2.0 * k3d + k4d
            )
            if not np.isfinite(dissipated_energy) or dissipated_energy < -1e-12:
                raise FloatingPointError("invalid cumulative dissipated energy")
            dissipated_energy = max(0.0, dissipated_energy)
            if index % stride == 0 or index == n_steps:
                record(index * step, values, velocity, dissipated_energy)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError, ValueError) as exc:
        raise FloatingPointError(
            f"full Lorentzian Skyrme evolution failed at step {len(times)}: {exc}"
        ) from exc

    return LorentzianSkyrmeTrajectory(
        model=_MODEL,
        fields=tuple(fields),
        velocities=tuple(velocities),
        time_history=tuple(times),
        energy_sigma_history=tuple(energy_sigma),
        energy_skyrme_history=tuple(energy_skyrme),
        kinetic_sigma_history=tuple(kinetic_sigma),
        kinetic_skyrme_history=tuple(kinetic_skyrme),
        total_energy_history=tuple(total_energy),
        dissipated_energy_history=tuple(dissipated),
        energy_balance_residual_history=tuple(energy_balance),
        approximate_charge_history=tuple(charge),
        time_kinetic_min_eigenvalue_history=tuple(min_eigenvalue),
        time_kinetic_max_condition_history=tuple(max_condition),
        max_unit_norm_error=max_unit_error,
        max_tangency_error=max_tangent_error,
        dt=step,
        steps=n_steps,
        save_every=stride,
        f_pi=f_value,
        e=e_value,
        damping=gamma,
        cell_volume=volume,
        linearized_cfl_indicator=float(cfl_indicator),
        hyperbolicity_status="not_certified",
        termination="completed",
    )

