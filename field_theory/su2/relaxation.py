"""Small-grid Riemannian relaxation for the discrete SU(2) Skyrme energy.

This is an optimization prototype, not a time-dependent Skyrme equation of
motion. It minimizes the exact discrete objective exposed by
``compute_skyrme_diagnostics``. A centered finite-difference estimate of the
Riemannian gradient is used so that the gradient matches that objective,
including its boundary rule and tangent-projected lattice derivatives.

For a unit field n at one site, the tangent directions
``v_a = e_a - n_a n`` span the tangent space and satisfy
``D E[v_a] = (grad_S3 E)_a``. The solver estimates each directional
derivative with a centered geodesic perturbation, projects roundoff back onto
the tangent space, then applies an exponential-map step with backtracking.
This costs eight energy evaluations per active site per gradient estimate;
it is intended only for small synthetic grids.

The reported ``gradient_tolerance`` termination means stationarity of this
finite-grid objective at the selected finite-difference scale. In particular,
the inherited periodic centered stencil has a Nyquist/checkerboard blind
spot, so this status is not a claim of continuum stability or a physical
Skyrmion solution. The algorithmic step size is not physical time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np

from field_theory.skyrme_diagnostics import compute_skyrme_diagnostics
from .field import SU2GridField

Termination = Literal["gradient_tolerance", "line_search_stalled", "iteration_limit"]


@dataclass(frozen=True)
class RelaxationResult:
    """Immutable summary of an optimization run.

    ``energy_history`` and ``topological_charge_history`` contain the initial
    state followed by each accepted step. Charge remains a finite-grid
    approximation and is never rounded to an integer.
    """

    field: SU2GridField
    energy_history: tuple[float, ...]
    topological_charge_history: tuple[float, ...]
    iterations: int
    termination: Termination


def _positive_real(value: object, name: str) -> float:
    raw = np.asarray(value)
    if raw.ndim != 0 or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric scalar")
    result = float(raw)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be finite and strictly positive")
    return result


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _active_mask(shape: tuple[int, int, int], boundary: str) -> np.ndarray:
    active = np.ones(shape, dtype=bool)
    if boundary == "fixed_vacuum":
        active[0, :, :] = False
        active[-1, :, :] = False
        active[:, 0, :] = False
        active[:, -1, :] = False
        active[:, :, 0] = False
        active[:, :, -1] = False
    return active


def _energy_and_charge(
    values: np.ndarray,
    initial: SU2GridField,
    *,
    f_pi: float,
    e: float,
    vacuum: Sequence[float],
) -> tuple[float, float]:
    diagnostics = compute_skyrme_diagnostics(
        values,
        initial.spacing,
        boundary=initial.boundary,
        f_pi=f_pi,
        e=e,
        vacuum=vacuum,
    )
    return diagnostics.energy_total, diagnostics.topological_charge


def _geodesic_perturbation(
    values: np.ndarray,
    site: tuple[int, int, int],
    tangent: np.ndarray,
    step: float,
    sign: float,
) -> np.ndarray:
    length = float(np.linalg.norm(tangent))
    if length == 0.0:
        return values
    angle = sign * step * length
    result = values.copy()
    result[site] = values[site] * np.cos(angle) + tangent * (np.sin(angle) / length)
    return result


def _riemannian_gradient(
    values: np.ndarray,
    active: np.ndarray,
    initial: SU2GridField,
    *,
    f_pi: float,
    e: float,
    vacuum: Sequence[float],
    finite_difference_step: float,
) -> np.ndarray:
    gradient = np.zeros_like(values)
    for raw_site in np.argwhere(active):
        site = tuple(int(index) for index in raw_site)
        base = values[site]
        for component in range(4):
            tangent = -base[component] * base
            tangent = tangent.copy()
            tangent[component] += 1.0
            if float(np.linalg.norm(tangent)) <= np.finfo(np.float64).eps:
                continue
            plus = _geodesic_perturbation(values, site, tangent, finite_difference_step, 1.0)
            minus = _geodesic_perturbation(values, site, tangent, finite_difference_step, -1.0)
            e_plus, _ = _energy_and_charge(plus, initial, f_pi=f_pi, e=e, vacuum=vacuum)
            e_minus, _ = _energy_and_charge(minus, initial, f_pi=f_pi, e=e, vacuum=vacuum)
            gradient[site + (component,)] = (e_plus - e_minus) / (2.0 * finite_difference_step)

    gradient -= values * np.sum(values * gradient, axis=-1, keepdims=True)
    gradient[~active] = 0.0
    if not np.all(np.isfinite(gradient)):
        raise FloatingPointError("non-finite discrete Skyrme gradient")
    return gradient


def _descending_step(
    values: np.ndarray, gradient: np.ndarray, active: np.ndarray, step: float
) -> np.ndarray:
    lengths = np.linalg.norm(gradient, axis=-1)
    angles = step * lengths
    with np.errstate(over="raise", invalid="raise"):
        cosine = np.cos(angles)
        factors = np.full_like(lengths, step)
        np.divide(np.sin(angles), lengths, out=factors, where=lengths > 0.0)
        candidate = values * cosine[..., None] - gradient * factors[..., None]
    candidate[~active] = values[~active]
    norms = np.linalg.norm(candidate, axis=-1)
    if not np.all(np.isfinite(candidate)) or np.any(norms[active] <= 0.0):
        raise FloatingPointError("non-finite field produced by discrete relaxation step")
    candidate[active] /= norms[active, None]
    return candidate


def relax_skyrme_field(
    initial: SU2GridField,
    *,
    f_pi: float = 1.0,
    e: float = 1.0,
    vacuum: Sequence[float] = (1.0, 0.0, 0.0, 0.0),
    max_iterations: int = 10,
    initial_step: float = 1.0e-3,
    finite_difference_step: float = 1.0e-5,
    gradient_tolerance: float = 1.0e-7,
    max_backtracks: int = 12,
) -> RelaxationResult:
    """Minimize the discrete Skyrme energy from ``initial`` by backtracking.

    Fixed-vacuum faces are held exactly fixed; periodic grids update every
    site. Each accepted exponential-map step is renormalized to counter
    floating-point drift, and is accepted only when the discrete energy
    decreases by more than roundoff. There is no stochasticity or physical
    time variable.

    The finite-difference gradient is intentionally transparent but expensive:
    each active site uses four tangent directions and two energy evaluations
    per direction. Use small synthetic grids. ``gradient_tolerance`` refers
    to the Euclidean norm of the assembled discrete Riemannian gradient.
    """
    if not isinstance(initial, SU2GridField):
        raise ValueError("initial must be an SU2GridField")
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    step0 = _positive_real(initial_step, "initial_step")
    fd_step = _positive_real(finite_difference_step, "finite_difference_step")
    tolerance = _positive_real(gradient_tolerance, "gradient_tolerance")
    iterations_limit = _integer(max_iterations, "max_iterations", minimum=1)
    backtrack_limit = _integer(max_backtracks, "max_backtracks", minimum=0)

    values = np.array(initial.components, dtype=np.float64, copy=True)
    active = _active_mask(values.shape[:3], initial.boundary)
    current_energy, current_charge = _energy_and_charge(
        values, initial, f_pi=f_value, e=e_value, vacuum=vacuum
    )
    energies = [current_energy]
    charges = [current_charge]
    termination: Termination = "iteration_limit"
    accepted_iterations = 0

    for _ in range(iterations_limit):
        gradient = _riemannian_gradient(
            values,
            active,
            initial,
            f_pi=f_value,
            e=e_value,
            vacuum=vacuum,
            finite_difference_step=fd_step,
        )
        gradient_norm = float(np.linalg.norm(gradient[active]))
        if not np.isfinite(gradient_norm):
            raise FloatingPointError("non-finite discrete Skyrme gradient norm")
        if gradient_norm <= tolerance:
            termination = "gradient_tolerance"
            break

        step = step0
        accepted = False
        roundoff_floor = 8.0 * np.finfo(np.float64).eps * max(1.0, abs(current_energy))
        for _ in range(backtrack_limit + 1):
            try:
                candidate = _descending_step(values, gradient, active, step)
                candidate_energy, candidate_charge = _energy_and_charge(
                    candidate, initial, f_pi=f_value, e=e_value, vacuum=vacuum
                )
            except FloatingPointError:
                candidate_energy = np.inf
                candidate_charge = np.nan
                candidate = values
            if candidate_energy < current_energy - roundoff_floor:
                values = candidate
                current_energy = candidate_energy
                current_charge = candidate_charge
                energies.append(current_energy)
                charges.append(current_charge)
                accepted_iterations += 1
                accepted = True
                break
            step *= 0.5

        if not accepted:
            termination = "line_search_stalled"
            break

    result_field = SU2GridField(
        values,
        spacing=initial.spacing,
        boundary=initial.boundary,
        length_unit=initial.length_unit,
    )
    return RelaxationResult(
        field=result_field,
        energy_history=tuple(float(value) for value in energies),
        topological_charge_history=tuple(float(value) for value in charges),
        iterations=accepted_iterations,
        termination=termination,
    )
