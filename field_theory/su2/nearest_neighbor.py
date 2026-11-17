"""Checkerboard-safe nearest-neighbor SU(2) Skyrme objective and relaxation.

This module is deliberately separate from the legacy
``field_theory.skyrme_diagnostics`` centered-stencil diagnostic, which remains
available with its known periodic Nyquist/checkerboard null. Here spatial
derivatives are replaced by forward link chords

    D_i n(x) = (n(x + h_i e_i) - n(x)) / h_i,

and the objective is

    E2 = F_pi^2/8 * dV * sum_{x,i} w_perp_i(x) |D_i n(x)|^2,
    E4 = 1/(2 e^2) * dV * sum_{x,i<j} w_perp_ij(x)
         sum_{a<b} (D_i n_a D_j n_b - D_i n_b D_j n_a)^2.

Here ``dV=h_x h_y h_z``.  For fixed-vacuum grids, a link sum includes only
anchors with an in-grid forward neighbor along its link direction; a quartic
sum includes only anchors with forward neighbors in both directions. The
``w_perp`` factors are tensor-product trapezoid weights on the remaining
transverse grid axes. For periodic grids all anchors are included and weights
are one.

The sigma term is the sum of squared link chords.  The quartic term is the sum
of squared 2x2 minors of pairs of forward link chords.  No tangent projection
is applied to each chord: projecting the difference between antipodal
checkerboard neighbors would erase precisely the signal this objective is
designed to retain.  The resulting energy is a distinct lattice objective;
it approaches the continuum expression for smooth, resolved fields but is
not claimed to be identical at finite spacing.

For fixed-vacuum grids, the field includes boundary nodes and every outer face
must equal ``vacuum``.  A forward link is included only if its endpoint lies
inside the grid.  Link-energy quadrature uses trapezoidal weights only in
directions transverse to the link; plaquette-like quartic terms use them only
in the remaining transverse direction.  Periodic grids are half-open and use
all forward links/cells once. The approximate degree uses
``B=dV/(2 pi^2) sum_x det[n,D_x n,D_y n,D_z n]`` over periodic anchors or
in-grid fixed-vacuum cells, and is never rounded.

The production gradient is assembled analytically from the transpose of the
forward-difference operators and projected onto the S^3 tangent spaces. A
slow sitewise geodesic finite-difference gradient remains available as a
small-grid verification reference. Relaxation steps use the exponential map
and backtracking, and therefore decrease this same discrete objective when
accepted. This is an optimization algorithm, not physical time evolution, and
it does not remove every possible discrete stationary point. In particular,
an exactly alternating antipodal periodic field has
nonzero link energy but can have zero tangent gradient by symmetry; the
gradient-only solver will stop there. At such a stop, a bounded deterministic
set of 16 constant/axis-parity tangent probes checks finite-difference
directional curvature. A detected negative curvature identifies a saddle
direction; no negative direction in this finite probe set is inconclusive,
not a local-minimum certificate. ``gradient_tolerance`` is first-order
stationarity only and never certifies a minimum or continuum stability.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence

import numpy as np

from .field import SU2GridField

Boundary = Literal["periodic", "fixed_vacuum"]
Termination = Literal["gradient_tolerance", "line_search_stalled", "iteration_limit"]
StationarityStatus = Literal["not_established", "first_order_stationary"]
CurvatureAssessment = Literal[
    "negative_curvature_detected",
    "no_negative_curvature_in_probe_set",
    "no_active_probe_directions",
]


@dataclass(frozen=True)
class NearestNeighborDiagnostics:
    """Nearest-neighbor lattice energies and approximate degree."""

    energy_sigma: float
    energy_skyrme: float
    energy_total: float
    topological_charge: float
    spacing: tuple[float, float, float]
    boundary: Boundary
    f_pi: float
    e: float


@dataclass(frozen=True)
class CurvatureProbeDiagnostics:
    """Bounded directional-curvature screen, not a Hessian/minimum certificate."""

    probe_count: int
    probe_step: float
    negative_curvature_tolerance: float
    most_negative_directional_curvature: float | None
    assessment: CurvatureAssessment


@dataclass(frozen=True)
class NearestNeighborRelaxationResult:
    """Result of optimization; first-order stationarity is not a minimum proof."""

    field: SU2GridField
    energy_history: tuple[float, ...]
    topological_charge_history: tuple[float, ...]
    iterations: int
    termination: Termination
    stationarity_status: StationarityStatus
    curvature_diagnostics: CurvatureProbeDiagnostics | None
    minimum_certified: bool


def _stable_norm(values: np.ndarray, axis: int | None = None) -> float | np.ndarray:
    """Compute an L2 norm without squaring tiny or huge components directly."""
    magnitudes = np.abs(np.asarray(values, dtype=np.float64))
    if axis is None:
        flattened = magnitudes.ravel()
        if flattened.size == 0:
            return 0.0
        return float(np.hypot.reduce(flattened))
    return np.hypot.reduce(magnitudes, axis=axis)


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


def _validate_field_and_vacuum(
    field: SU2GridField, vacuum: Sequence[float]
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(field, SU2GridField):
        raise ValueError("field must be an SU2GridField")
    raw_vacuum = np.asarray(vacuum)
    if raw_vacuum.shape != (4,) or raw_vacuum.dtype.kind not in "fiu":
        raise ValueError("vacuum must be a real four-vector")
    vacuum_values = raw_vacuum.astype(np.float64)
    if not np.all(np.isfinite(vacuum_values)):
        raise ValueError("vacuum must be finite")
    if abs(float(np.linalg.norm(vacuum_values)) - 1.0) > 1.0e-8:
        raise ValueError("vacuum must have unit norm")
    values = np.array(field.components, dtype=np.float64, copy=True)
    if field.boundary == "fixed_vacuum":
        for axis in range(3):
            for index in (0, -1):
                face = np.take(values, index, axis=axis)
                if np.any(np.abs(face - vacuum_values) > 1.0e-8):
                    raise ValueError(
                        "fixed_vacuum boundary requires every outer face to equal vacuum"
                    )
    return values, vacuum_values


def _link_mask(
    shape: tuple[int, int, int], axes: tuple[int, ...], boundary: Boundary
) -> np.ndarray:
    mask = np.ones(shape, dtype=bool)
    if boundary == "fixed_vacuum":
        for axis in axes:
            selector = [slice(None)] * 3
            selector[axis] = -1
            mask[tuple(selector)] = False
    return mask


def _transverse_weights(
    shape: tuple[int, int, int], excluded_axes: tuple[int, ...], boundary: Boundary
) -> np.ndarray:
    weights = np.ones(shape, dtype=np.float64)
    if boundary == "fixed_vacuum":
        for axis in range(3):
            if axis in excluded_axes:
                continue
            line = np.ones(shape[axis], dtype=np.float64)
            line[[0, -1]] = 0.5
            reshape = [1, 1, 1]
            reshape[axis] = shape[axis]
            weights *= line.reshape(reshape)
    return weights


def _cell_volume(spacing: tuple[float, float, float]) -> float:
    """Return a representable positive binary64 grid-cell volume."""
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        volume = float(
            np.float64(spacing[0])
            * np.float64(spacing[1])
            * np.float64(spacing[2])
        )
    if not np.isfinite(volume) or volume <= 0.0:
        raise ValueError(
            "grid spacings must produce a finite positive binary64 cell volume"
        )
    return volume


def _forward_differences(
    values: np.ndarray, spacing: tuple[float, float, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return tuple(
        (np.roll(values, -1, axis=axis) - values) / spacing[axis]
        for axis in range(3)
    )  # type: ignore[return-value]



def _energy_coefficients(f_pi: float, e: float) -> tuple[float, float]:
    """Return finite, nonzero binary64 coefficients for the two Skyrme terms.

    Inputs are checked by the public callers. Log-domain preflight avoids an
    overflowing intermediate when the final coefficient is representable;
    the final checks reject overflow or underflow-to-zero rather than silently
    changing the objective.
    """
    f_value = float(f_pi)
    e_value = float(e)
    if not np.isfinite(f_value) or f_value <= 0.0 or not np.isfinite(e_value) or e_value <= 0.0:
        raise ValueError("f_pi and e must be finite and positive")

    log_max = math.log(np.finfo(np.float64).max)
    sigma_log = 2.0 * math.log(f_value) - math.log(8.0)
    skyrme_log = -math.log(2.0) - 2.0 * math.log(e_value)
    if sigma_log > log_max or skyrme_log > log_max:
        raise ValueError("couplings produce an unrepresentable binary64 energy coefficient")

    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        sigma_coefficient = float(np.square(np.float64(f_value) / np.sqrt(np.float64(8.0))))
        skyrme_coefficient = float(
            np.square(np.float64(1.0) / (np.sqrt(np.float64(2.0)) * np.float64(e_value)))
        )
    if (
        not np.isfinite(sigma_coefficient)
        or sigma_coefficient <= 0.0
        or not np.isfinite(skyrme_coefficient)
        or skyrme_coefficient <= 0.0
    ):
        raise ValueError("couplings produce an unrepresentable binary64 energy coefficient")
    return sigma_coefficient, skyrme_coefficient


def _gradient_coefficients(f_pi: float, e: float) -> tuple[float, float]:
    """Return finite, nonzero coefficients used by the analytic energy gradient.

    The gradient weights are twice the corresponding energy coefficients.
    Reuse the scaled energy preflight instead of squaring raw couplings, then
    reject a gradient coefficient that cannot be represented in binary64.
    """
    sigma_energy, skyrme_energy = _energy_coefficients(f_pi, e)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        sigma_gradient = float(np.float64(2.0) * np.float64(sigma_energy))
        skyrme_gradient = float(np.float64(2.0) * np.float64(skyrme_energy))
    if (
        not np.isfinite(sigma_gradient)
        or sigma_gradient <= 0.0
        or not np.isfinite(skyrme_gradient)
        or skyrme_gradient <= 0.0
    ):
        raise ValueError("couplings produce an unrepresentable binary64 gradient coefficient")
    return sigma_gradient, skyrme_gradient


def _energy_components(
    values: np.ndarray,
    differences: tuple[np.ndarray, np.ndarray, np.ndarray],
    spacing: tuple[float, float, float],
    boundary: Boundary,
    f_pi: float,
    e: float,
) -> tuple[float, float]:
    shape = values.shape[:3]
    cell_volume = _cell_volume(spacing)
    sigma_sum = 0.0
    for axis in range(3):
        valid = _link_mask(shape, (axis,), boundary)
        transverse = _transverse_weights(shape, (axis,), boundary)
        norm_squared = np.sum(differences[axis] ** 2, axis=-1)
        sigma_sum += float(np.sum(norm_squared[valid] * transverse[valid])) * cell_volume
    sigma_coefficient, skyrme_coefficient = _energy_coefficients(f_pi, e)
    energy_sigma = sigma_coefficient * sigma_sum

    quartic_sum = 0.0
    for i in range(3):
        for j in range(i + 1, 3):
            valid = _link_mask(shape, (i, j), boundary)
            transverse = _transverse_weights(shape, (i, j), boundary)
            wedge_squared = np.zeros(shape, dtype=np.float64)
            for a in range(4):
                for b in range(a + 1, 4):
                    minor = (
                        differences[i][..., a] * differences[j][..., b]
                        - differences[i][..., b] * differences[j][..., a]
                    )
                    wedge_squared += minor * minor
            quartic_sum += float(np.sum(wedge_squared[valid] * transverse[valid])) * cell_volume
    energy_skyrme = skyrme_coefficient * quartic_sum
    return energy_sigma, energy_skyrme


def _topological_charge(
    values: np.ndarray,
    differences: tuple[np.ndarray, np.ndarray, np.ndarray],
    spacing: tuple[float, float, float],
    boundary: Boundary,
) -> float:
    columns = np.stack((values, *differences), axis=-1)
    determinant = np.linalg.det(columns)
    cell_volume = _cell_volume(spacing)
    valid = _link_mask(values.shape[:3], (0, 1, 2), boundary)
    return float(np.sum(determinant[valid]) * cell_volume / (2.0 * np.pi**2))


def _diagnostics_from_values(
    values: np.ndarray,
    field: SU2GridField,
    *,
    f_pi: float,
    e: float,
) -> NearestNeighborDiagnostics:
    differences = _forward_differences(values, field.spacing)
    energy_sigma, energy_skyrme = _energy_components(
        values, differences, field.spacing, field.boundary, f_pi, e
    )
    charge = _topological_charge(values, differences, field.spacing, field.boundary)
    result = np.asarray((energy_sigma, energy_skyrme, energy_sigma + energy_skyrme, charge))
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("non-finite nearest-neighbor Skyrme diagnostic")
    if energy_sigma < 0.0 or energy_skyrme < 0.0:
        raise FloatingPointError("nearest-neighbor energy positivity invariant failed")
    return NearestNeighborDiagnostics(
        energy_sigma=energy_sigma,
        energy_skyrme=energy_skyrme,
        energy_total=energy_sigma + energy_skyrme,
        topological_charge=charge,
        spacing=field.spacing,
        boundary=field.boundary,  # type: ignore[arg-type]
        f_pi=f_pi,
        e=e,
    )


def compute_nearest_neighbor_diagnostics(
    field: SU2GridField,
    *,
    f_pi: float = 1.0,
    e: float = 1.0,
    vacuum: Sequence[float] = (1.0, 0.0, 0.0, 0.0),
) -> NearestNeighborDiagnostics:
    """Evaluate the forward-link Skyrme lattice objective and approximate degree.

    The energy uses the same continuum coefficients as the legacy diagnostic,
    but forward chord differences and link/cell quadrature. Therefore its
    finite-grid values are not numerically interchangeable with
    ``compute_skyrme_diagnostics``.
    """
    values, _ = _validate_field_and_vacuum(field, vacuum)
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _diagnostics_from_values(
                values, field, f_pi=f_value, e=e_value
            )
    except FloatingPointError:
        raise FloatingPointError("non-finite nearest-neighbor Skyrme diagnostic") from None


def _validate_fixed_mask(
    field: SU2GridField, fixed_mask: np.ndarray | None
) -> np.ndarray:
    """Return a copy of an exact-shape boolean fixed-site mask."""
    shape = field.components.shape[:3]
    if fixed_mask is None:
        return np.zeros(shape, dtype=bool)
    raw = np.asarray(fixed_mask)
    if raw.shape != shape or raw.dtype.kind != "b":
        raise ValueError("fixed_mask must be a boolean array matching the grid shape")
    return np.array(raw, dtype=bool, copy=True)


def _active_mask(
    field: SU2GridField, fixed_mask: np.ndarray | None = None
) -> np.ndarray:
    active = np.ones(field.components.shape[:3], dtype=bool)
    if field.boundary == "fixed_vacuum":
        active[0, :, :] = False
        active[-1, :, :] = False
        active[:, 0, :] = False
        active[:, -1, :] = False
        active[:, :, 0] = False
        active[:, :, -1] = False
    active &= ~_validate_fixed_mask(field, fixed_mask)
    return active


def _total_energy_for_values(
    values: np.ndarray, field: SU2GridField, f_pi: float, e: float
) -> float:
    differences = _forward_differences(values, field.spacing)
    sigma, quartic = _energy_components(
        values, differences, field.spacing, field.boundary, f_pi, e
    )
    result = float(sigma + quartic)
    if not np.isfinite(result):
        raise FloatingPointError("non-finite energy during curvature probe")
    return result


def _geodesic_perturbation(
    values: np.ndarray, direction: np.ndarray, step: float, sign: float
) -> np.ndarray:
    lengths = np.linalg.norm(direction, axis=-1)
    angles = sign * step * lengths
    factors = np.full_like(lengths, sign * step)
    np.divide(np.sin(angles), lengths, out=factors, where=lengths > 0.0)
    candidate = values * np.cos(angles)[..., None] + direction * factors[..., None]
    if not np.all(np.isfinite(candidate)):
        raise FloatingPointError("non-finite field during curvature probe")
    return candidate


def probe_nearest_neighbor_curvature(
    field: SU2GridField,
    *,
    f_pi: float = 1.0,
    e: float = 1.0,
    vacuum: Sequence[float] = (1.0, 0.0, 0.0, 0.0),
    probe_step: float = 5.0e-3,
    negative_curvature_tolerance: float = 1.0e-6,
    fixed_mask: np.ndarray | None = None,
) -> CurvatureProbeDiagnostics:
    """Probe at most 16 normalized tangent directions for negative curvature.

    Probe directions are deterministic products of the four ambient component
    axes with four spatial patterns: constant and parity-alternating along
    each coordinate axis. A negative value of the central geodesic second
    difference reveals a descent-curvature direction. Absence of a detected
    direction says only that this bounded set found none; it cannot certify a
    local minimum.
    """
    values, _ = _validate_field_and_vacuum(field, vacuum)
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    step = _positive_real(probe_step, "probe_step")
    curvature_tolerance = _positive_real(
        negative_curvature_tolerance, "negative_curvature_tolerance"
    )
    if step > 0.1:
        raise ValueError("probe_step must not exceed 0.1")

    active = _active_mask(field, fixed_mask)
    shape = values.shape[:3]
    patterns = [np.ones(shape, dtype=np.float64)]
    for axis, size in enumerate(shape):
        parity = np.where(np.arange(size) % 2 == 0, 1.0, -1.0)
        reshape = [1, 1, 1]
        reshape[axis] = size
        patterns.append(np.broadcast_to(parity.reshape(reshape), shape))

    base_energy = _total_energy_for_values(values, field, f_value, e_value)
    curvatures: list[float] = []
    for component in range(4):
        tangent = -values * values[..., component, None]
        tangent[..., component] += 1.0
        for pattern in patterns:
            direction = tangent * pattern[..., None]
            direction[~active] = 0.0
            norm = float(np.linalg.norm(direction[active]))
            if norm <= np.finfo(np.float64).eps:
                continue
            direction /= norm
            plus = _geodesic_perturbation(values, direction, step, 1.0)
            minus = _geodesic_perturbation(values, direction, step, -1.0)
            curvature = (
                _total_energy_for_values(plus, field, f_value, e_value)
                + _total_energy_for_values(minus, field, f_value, e_value)
                - 2.0 * base_energy
            ) / (step * step)
            if not np.isfinite(curvature):
                raise FloatingPointError("non-finite directional curvature")
            curvatures.append(float(curvature))

    if not curvatures:
        return CurvatureProbeDiagnostics(
            probe_count=0,
            probe_step=step,
            negative_curvature_tolerance=curvature_tolerance,
            most_negative_directional_curvature=None,
            assessment="no_active_probe_directions",
        )
    most_negative = min(curvatures)
    found = most_negative < -curvature_tolerance
    return CurvatureProbeDiagnostics(
        probe_count=len(curvatures),
        probe_step=step,
        negative_curvature_tolerance=curvature_tolerance,
        most_negative_directional_curvature=most_negative,
        assessment=(
            "negative_curvature_detected"
            if found
            else "no_negative_curvature_in_probe_set"
        ),
    )


def _unit_geodesic_perturbation(
    values: np.ndarray, site: tuple[int, int, int], tangent: np.ndarray, step: float, sign: float
) -> np.ndarray:
    length = float(np.linalg.norm(tangent))
    if length == 0.0:
        return values
    angle = sign * step * length
    changed = values.copy()
    changed[site] = values[site] * np.cos(angle) + tangent * (np.sin(angle) / length)
    return changed


def _accumulate_forward_derivative_gradient(
    gradient: np.ndarray,
    derivative_gradient: np.ndarray,
    axis: int,
    spacing: float,
    coefficient: float = 1.0,
) -> None:
    """Apply the scaled transpose of the forward-difference operator in-place."""
    # Apply the transpose's 1/h factor before a potentially subnormal coupling
    # coefficient; otherwise a contribution can underflow before this scaling.
    scaled = (derivative_gradient / spacing) * coefficient
    gradient -= scaled
    gradient += np.roll(scaled, 1, axis=axis)


def nearest_neighbor_energy_gradient(
    field: SU2GridField,
    *,
    f_pi: float = 1.0,
    e: float = 1.0,
    vacuum: Sequence[float] = (1.0, 0.0, 0.0, 0.0),
    finite_difference_step: float | None = None,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Return the analytic tangent gradient of the nearest-link objective.

    The Euclidean derivative is assembled from the transpose of each forward
    difference operator, including the exact masks and quadrature weights used
    by the energy. It is then projected onto the tangent space of S^3 at every
    node. Optional ``fixed_mask`` sites are excluded from the active tangent
    space and receive an exactly zero gradient. ``finite_difference_step`` is accepted for compatibility with the
    earlier implementation but does not affect this analytic result; use
    :func:`nearest_neighbor_energy_gradient_finite_difference` when a numeric
    reference gradient is needed.
    """
    values, vacuum_values = _validate_field_and_vacuum(field, vacuum)
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    if finite_difference_step is not None:
        _positive_real(finite_difference_step, "finite_difference_step")
    active = _active_mask(field, fixed_mask)
    gradient = np.zeros_like(values)
    differences = _forward_differences(values, field.spacing)
    sigma_gradient_coefficient, skyrme_gradient_coefficient = _gradient_coefficients(
        f_value, e_value
    )
    cell_volume = _cell_volume(field.spacing)

    for axis in range(3):
        valid = _link_mask(values.shape[:3], (axis,), field.boundary)
        transverse = _transverse_weights(values.shape[:3], (axis,), field.boundary)
        # Keep the coupling coefficient out until the transpose stencil has
        # applied its spacing factor; this preserves representable subnormal terms.
        derivative_gradient = (
            cell_volume * differences[axis] * transverse[..., None]
        )
        derivative_gradient[~valid] = 0.0
        _accumulate_forward_derivative_gradient(
            gradient,
            derivative_gradient,
            axis,
            field.spacing[axis],
            sigma_gradient_coefficient,
        )

    for i in range(3):
        for j in range(i + 1, 3):
            valid = _link_mask(values.shape[:3], (i, j), field.boundary)
            transverse = _transverse_weights(values.shape[:3], (i, j), field.boundary)
            a = differences[i]
            b = differences[j]
            dot = np.sum(a * b, axis=-1)
            norm_a_squared = np.sum(a * a, axis=-1)
            norm_b_squared = np.sum(b * b, axis=-1)
            # Keep the coupling coefficient out until the transpose stencil
            # has divided by spacing, avoiding premature subnormal underflow.
            grad_a = (
                cell_volume
                * (norm_b_squared[..., None] * a - dot[..., None] * b)
                * transverse[..., None]
            )
            grad_b = (
                cell_volume
                * (norm_a_squared[..., None] * b - dot[..., None] * a)
                * transverse[..., None]
            )
            grad_a[~valid] = 0.0
            grad_b[~valid] = 0.0
            _accumulate_forward_derivative_gradient(
                gradient, grad_a, i, field.spacing[i], skyrme_gradient_coefficient
            )
            _accumulate_forward_derivative_gradient(
                gradient, grad_b, j, field.spacing[j], skyrme_gradient_coefficient
            )

    gradient -= values * np.sum(values * gradient, axis=-1, keepdims=True)
    gradient[~active] = 0.0
    if not np.all(np.isfinite(gradient)):
        raise FloatingPointError("non-finite nearest-neighbor energy gradient")
    return gradient


def nearest_neighbor_energy_gradient_finite_difference(
    field: SU2GridField,
    *,
    f_pi: float = 1.0,
    e: float = 1.0,
    vacuum: Sequence[float] = (1.0, 0.0, 0.0, 0.0),
    finite_difference_step: float = 1.0e-5,
    fixed_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Return a slow sitewise finite-difference reference gradient.

    Each component is the central directional derivative along
    ``e_a - n_a*n`` using geodesic perturbations. This reference is intended
    for small-grid verification; the production gradient uses a vectorized
    analytic transpose-difference calculation.
    """
    values, vacuum_values = _validate_field_and_vacuum(field, vacuum)
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    step = _positive_real(finite_difference_step, "finite_difference_step")
    active = _active_mask(field, fixed_mask)
    gradient = np.zeros_like(values)

    def energy(candidate: np.ndarray) -> float:
        return _total_energy_for_values(candidate, field, f_value, e_value)

    for raw_site in np.argwhere(active):
        site = tuple(int(index) for index in raw_site)
        base = values[site]
        for component in range(4):
            tangent = -base[component] * base
            tangent = tangent.copy()
            tangent[component] += 1.0
            if float(np.linalg.norm(tangent)) <= np.finfo(np.float64).eps:
                continue
            plus = _unit_geodesic_perturbation(values, site, tangent, step, 1.0)
            minus = _unit_geodesic_perturbation(values, site, tangent, step, -1.0)
            gradient[site + (component,)] = (energy(plus) - energy(minus)) / (2.0 * step)

    gradient -= values * np.sum(values * gradient, axis=-1, keepdims=True)
    gradient[~active] = 0.0
    if not np.all(np.isfinite(gradient)):
        raise FloatingPointError("non-finite nearest-neighbor energy gradient")
    return gradient


def _descending_step(
    values: np.ndarray, gradient: np.ndarray, active: np.ndarray, step: float
) -> np.ndarray:
    lengths = _stable_norm(gradient, axis=-1)
    angles = step * lengths
    with np.errstate(over="raise", invalid="raise"):
        factors = np.full_like(lengths, step)
        np.divide(np.sin(angles), lengths, out=factors, where=lengths > 0.0)
        candidate = values * np.cos(angles)[..., None] - gradient * factors[..., None]
    candidate[~active] = values[~active]
    norms = _stable_norm(candidate, axis=-1)
    if not np.all(np.isfinite(candidate)) or np.any(norms[active] <= 0.0):
        raise FloatingPointError("non-finite field produced by nearest-neighbor step")
    candidate[active] /= norms[active, None]
    return candidate


def relax_skyrme_field_nearest_neighbor(
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
    fixed_mask: np.ndarray | None = None,
) -> NearestNeighborRelaxationResult:
    """Minimize the forward-link objective by monotone backtracking steps.

    ``finite_difference_step`` is retained for compatibility with the
    previous reference-gradient implementation; the optimizer now uses the
    analytic gradient and does not depend on that step size. Optional
    ``fixed_mask`` sites remain exactly equal to their initial values.
    """
    values, vacuum_values = _validate_field_and_vacuum(initial, vacuum)
    f_value = _positive_real(f_pi, "f_pi")
    e_value = _positive_real(e, "e")
    step0 = _positive_real(initial_step, "initial_step")
    fd_step = _positive_real(finite_difference_step, "finite_difference_step")
    tolerance = _positive_real(gradient_tolerance, "gradient_tolerance")
    iteration_limit = _integer(max_iterations, "max_iterations", minimum=1)
    backtrack_limit = _integer(max_backtracks, "max_backtracks", minimum=0)
    fixed_sites = _validate_fixed_mask(initial, fixed_mask)
    active = _active_mask(initial, fixed_sites)
    initial_diagnostics = _diagnostics_from_values(values, initial, f_pi=f_value, e=e_value)
    energies = [initial_diagnostics.energy_total]
    charges = [initial_diagnostics.topological_charge]
    termination: Termination = "iteration_limit"
    stationarity_status: StationarityStatus = "not_established"
    curvature_diagnostics: CurvatureProbeDiagnostics | None = None
    accepted_iterations = 0

    for _ in range(iteration_limit):
        gradient = nearest_neighbor_energy_gradient(
            SU2GridField(values, initial.spacing, initial.boundary, initial.length_unit),
            f_pi=f_value,
            e=e_value,
            vacuum=vacuum_values,
            finite_difference_step=fd_step,
            fixed_mask=fixed_sites,
        )
        gradient_norm = float(_stable_norm(gradient[active]))
        if not np.isfinite(gradient_norm):
            raise FloatingPointError("non-finite nearest-neighbor gradient norm")
        if gradient_norm <= tolerance:
            termination = "gradient_tolerance"
            stationarity_status = "first_order_stationary"
            stationary_field = SU2GridField(
                values,
                spacing=initial.spacing,
                boundary=initial.boundary,
                length_unit=initial.length_unit,
            )
            curvature_diagnostics = probe_nearest_neighbor_curvature(
                stationary_field,
                f_pi=f_value,
                e=e_value,
                vacuum=vacuum_values,
                fixed_mask=fixed_sites,
            )
            break

        accepted = False
        step = step0
        floor = 8.0 * np.finfo(np.float64).eps * max(1.0, abs(energies[-1]))
        for _ in range(backtrack_limit + 1):
            try:
                candidate = _descending_step(values, gradient, active, step)
                candidate_diagnostics = _diagnostics_from_values(
                    candidate,
                    initial,
                    f_pi=f_value,
                    e=e_value,
                )
            except FloatingPointError:
                candidate_diagnostics = None
                candidate = values
            if (
                candidate_diagnostics is not None
                and candidate_diagnostics.energy_total < energies[-1] - floor
            ):
                values = candidate
                energies.append(candidate_diagnostics.energy_total)
                charges.append(candidate_diagnostics.topological_charge)
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
    return NearestNeighborRelaxationResult(
        field=result_field,
        energy_history=tuple(float(value) for value in energies),
        topological_charge_history=tuple(float(value) for value in charges),
        iterations=accepted_iterations,
        termination=termination,
        stationarity_status=stationarity_status,
        curvature_diagnostics=curvature_diagnostics,
        minimum_certified=False,
    )


