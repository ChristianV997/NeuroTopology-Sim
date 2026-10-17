"""Independent equation-level oracle for the proposed four-shell BVP.

This is a synthetic-only audit artifact, not an implementation of or test against
any unavailable Gemini/Round 6 module. It assembles the seven stated boundary
equations and independently derives a dipole-to-surface harmonic projector.

Coordinates are metres, conductivities are S/m, and dipole moments are A*m.
The shell basis is dimensionless, so its current-continuity residuals use
conductivity times radial derivative (S/m^2) before a physical amplitude is
applied. NumPy is used for the 7x7 solve when already installed; a standard
library partial-pivot solver keeps the audit executable without installing it.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from functools import lru_cache
import json
import math
from numbers import Integral, Real
from typing import Iterable, Sequence

try:  # NumPy is a project base dependency, but installs are not required here.
    import numpy as _np
except ImportError:  # pragma: no cover - exercised in the minimal audit environment
    _np = None

DEFAULT_RADII_M = (0.078, 0.080, 0.086, 0.095)
DEFAULT_SIGMAS_SM = (0.33, 1.79, 0.0042, 0.33)
MAX_HARMONIC_DEGREE = 2048
_RESIDUAL_FLOOR = 1.0e-300

_A_INDEX = (0, 1, 3, 5)
_B_INDEX = {1: 2, 2: 4, 3: 6}
_UNKNOWN_ORDER = ("a1", "a2", "b2", "a3", "b3", "a4", "b4")


class OracleInputError(ValueError):
    """Raised when an equation-oracle input violates its declared contract."""


@dataclass(frozen=True)
class BoundaryResiduals:
    """Absolute and row-scaled residuals for the stated boundary conditions."""

    max_potential_continuity_abs: float
    max_potential_continuity_scaled: float
    max_current_continuity_abs_sm2: float
    max_current_continuity_scaled: float
    outer_current_abs_sm2: float
    outer_current_scaled: float
    max_linear_row_backward_error: float


@dataclass(frozen=True)
class ShellModeSolution:
    """One degree-l shell solution normalized to b1=1."""

    degree: int
    coefficients: tuple[float, ...]
    unknown_order: tuple[str, ...]
    b1_fixed: float
    matrix_shape: tuple[int, int]
    free_surface_value: float
    layered_surface_value: float
    surface_transfer_ratio: float
    residuals: BoundaryResiduals

    def coefficient_map(self) -> dict[str, float]:
        return {"a1": self.coefficients[0], "b1": self.b1_fixed,
                "a2": self.coefficients[1], "b2": self.coefficients[2],
                "a3": self.coefficients[3], "b3": self.coefficients[4],
                "a4": self.coefficients[5], "b4": self.coefficients[6]}


@dataclass(frozen=True)
class DipoleProjection:
    """Truncated synthetic four-shell potential on the outer spherical surface."""

    surface_potentials_v: tuple[float, ...]
    max_degree: int
    source_radius_m: float
    last_degree_max_abs_v: float


def solver_backend() -> str:
    """Return the actual linear-solver backend without importing optional tools."""
    return "numpy.linalg.solve" if _np is not None else "python_partial_pivot"


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise OracleInputError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise OracleInputError(f"{name} must be finite")
    return result


def _as_tuple(values: Iterable[object], length: int, name: str) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise OracleInputError(f"{name} must contain {length} numeric values")
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise OracleInputError(f"{name} must contain {length} numeric values") from exc
    if len(raw) != length:
        raise OracleInputError(f"{name} must contain exactly {length} values")
    return tuple(_finite_real(item, f"{name}[{index}]") for index, item in enumerate(raw))


def _vector3(values: Iterable[object], name: str) -> tuple[float, float, float]:
    result = _as_tuple(values, 3, name)
    return (result[0], result[1], result[2])


def _geometry(radii_m: Iterable[object], sigmas_sm: Iterable[object]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    radii = _as_tuple(radii_m, 4, "radii_m")
    sigmas = _as_tuple(sigmas_sm, 4, "sigmas_sm")
    if any(radius <= 0.0 for radius in radii):
        raise OracleInputError("all radii_m must be positive metres")
    if not all(radii[index] < radii[index + 1] for index in range(3)):
        raise OracleInputError("radii_m must be strictly increasing: r1 < r2 < r3 < r4")
    if radii[-1] > 1.0:
        raise OracleInputError("r4 must be at most 1 metre for this spherical head-model contract")
    if any(sigma <= 0.0 for sigma in sigmas):
        raise OracleInputError("all sigmas_sm must be positive S/m values")
    return radii, sigmas


def _degree(value: object, name: str = "degree") -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) < 1:
        raise OracleInputError(f"{name} must be a positive integer (dipole harmonics start at l=1)")
    return int(value)


def _basis_terms(degree: int, radius_m: float, r1_m: float, r4_m: float) -> tuple[float, float, float, float]:
    plus = (radius_m / r4_m) ** degree
    minus = (r1_m / radius_m) ** (degree + 1)
    d_plus = degree * plus / radius_m
    d_minus = -(degree + 1) * minus / radius_m
    return plus, minus, d_plus, d_minus


def _build_system(
    degree: int, radii: tuple[float, ...], sigmas: tuple[float, ...]
) -> tuple[list[list[float]], list[float], tuple[str, ...]]:
    """Build 6 interface equations and one outer zero-current equation."""
    r1, r2, r3, r4 = radii
    matrix: list[list[float]] = []
    rhs: list[float] = []

    def append_side(row: list[float], right: list[float], shell: int, radius: float,
                    sign: float, current: bool) -> None:
        plus, minus, d_plus, d_minus = _basis_terms(degree, radius, r1, r4)
        if current:
            plus *= sigmas[shell]
            minus *= sigmas[shell]
            d_plus *= sigmas[shell]
            d_minus *= sigmas[shell]
            plus, minus = d_plus, d_minus
        row[_A_INDEX[shell]] += sign * plus
        if shell == 0:
            # b1 is fixed to 1 and moved to the right-hand side.
            right[0] -= sign * minus
        else:
            row[_B_INDEX[shell]] += sign * minus

    for boundary_radius, inner_shell in ((r1, 0), (r2, 1), (r3, 2)):
        for current in (False, True):
            row = [0.0] * 7
            right = [0.0]
            append_side(row, right, inner_shell, boundary_radius, +1.0, current)
            append_side(row, right, inner_shell + 1, boundary_radius, -1.0, current)
            matrix.append(row)
            rhs.append(right[0])

    # sigma4 * d/dr (a4 (r/r4)^l + b4 (r1/r)^(l+1)) at r4 = 0.
    _, _, d_plus, d_minus = _basis_terms(degree, r4, r1, r4)
    matrix.append([0.0, 0.0, 0.0, 0.0, 0.0,
                   sigmas[3] * d_plus, sigmas[3] * d_minus])
    rhs.append(0.0)
    return matrix, rhs, _UNKNOWN_ORDER


def _solve_linear(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    if _np is not None:
        try:
            answer = _np.linalg.solve(_np.asarray(matrix, dtype=float), _np.asarray(rhs, dtype=float))
        except _np.linalg.LinAlgError as exc:
            raise OracleInputError("four-shell boundary matrix is singular") from exc
        return [float(value) for value in answer]

    # Small, dependency-free Gaussian elimination with partial pivoting.
    size = len(rhs)
    augmented = [list(map(float, matrix[row])) + [float(rhs[row])] for row in range(size)]
    if any(len(row) != size + 1 for row in augmented):
        raise OracleInputError("boundary matrix must be square")
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if augmented[pivot][column] == 0.0:
            raise OracleInputError("four-shell boundary matrix is singular")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= pivot_value
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [augmented[row][-1] for row in range(size)]


def _phi_and_derivative(
    degree: int, shell: int, radius: float, coefficients: Sequence[float],
    b1: float, radii: tuple[float, ...]
) -> tuple[float, float]:
    plus, minus, d_plus, d_minus = _basis_terms(degree, radius, radii[0], radii[3])
    a = coefficients[_A_INDEX[shell]]
    b = b1 if shell == 0 else coefficients[_B_INDEX[shell]]
    return a * plus + b * minus, a * d_plus + b * d_minus


def _row_backward_error(matrix: Sequence[Sequence[float]], rhs: Sequence[float], solution: Sequence[float]) -> float:
    errors = []
    for row, target in zip(matrix, rhs):
        residual = sum(row[index] * solution[index] for index in range(len(solution))) - target
        scale = sum(abs(row[index] * solution[index]) for index in range(len(solution))) + abs(target)
        errors.append(abs(residual) / max(scale, _RESIDUAL_FLOOR))
    return max(errors, default=0.0)


@lru_cache(maxsize=8192)
def _solve_cached(degree: int, radii: tuple[float, ...], sigmas: tuple[float, ...]) -> ShellModeSolution:
    matrix, rhs, order = _build_system(degree, radii, sigmas)
    if not all(math.isfinite(value) for row in matrix for value in row) or not all(
        math.isfinite(value) for value in rhs
    ):
        raise OracleInputError("boundary matrix contains non-finite values for this geometry/degree")
    coefficients = _solve_linear(matrix, rhs)
    potential_abs: list[float] = []
    potential_scaled: list[float] = []
    current_abs: list[float] = []
    current_scaled: list[float] = []
    for boundary_radius, inner_shell in ((radii[0], 0), (radii[1], 1), (radii[2], 2)):
        p_inner, d_inner = _phi_and_derivative(degree, inner_shell, boundary_radius, coefficients, 1.0, radii)
        p_outer, d_outer = _phi_and_derivative(degree, inner_shell + 1, boundary_radius, coefficients, 1.0, radii)
        j_inner = sigmas[inner_shell] * d_inner
        j_outer = sigmas[inner_shell + 1] * d_outer
        p_res = abs(p_inner - p_outer)
        j_res = abs(j_inner - j_outer)
        potential_abs.append(p_res)
        potential_scaled.append(p_res / max(abs(p_inner) + abs(p_outer), _RESIDUAL_FLOOR))
        current_abs.append(j_res)
        current_scaled.append(j_res / max(abs(j_inner) + abs(j_outer), _RESIDUAL_FLOOR))

    p_outer, d_outer = _phi_and_derivative(degree, 3, radii[3], coefficients, 1.0, radii)
    del p_outer
    outer_current = sigmas[3] * d_outer
    _, _, d_plus, d_minus = _basis_terms(degree, radii[3], radii[0], radii[3])
    outer_scale = sigmas[3] * (abs(coefficients[_A_INDEX[3]] * d_plus)
                               + abs(coefficients[_B_INDEX[3]] * d_minus))
    free_surface = (radii[0] / radii[3]) ** (degree + 1)
    if free_surface == 0.0:
        raise OracleInputError("free-space surface normalization underflowed for this geometry/degree")
    layered_surface = coefficients[_A_INDEX[3]] + coefficients[_B_INDEX[3]] * free_surface
    transfer_ratio = layered_surface / free_surface
    residuals = BoundaryResiduals(
        max_potential_continuity_abs=max(potential_abs),
        max_potential_continuity_scaled=max(potential_scaled),
        max_current_continuity_abs_sm2=max(current_abs),
        max_current_continuity_scaled=max(current_scaled),
        outer_current_abs_sm2=abs(outer_current),
        outer_current_scaled=abs(outer_current) / max(outer_scale, _RESIDUAL_FLOOR),
        max_linear_row_backward_error=_row_backward_error(matrix, rhs, coefficients),
    )
    values = (*coefficients, free_surface, layered_surface,
              residuals.max_potential_continuity_abs,
              residuals.max_potential_continuity_scaled,
              residuals.max_current_continuity_abs_sm2,
              residuals.max_current_continuity_scaled,
              residuals.outer_current_abs_sm2,
              residuals.outer_current_scaled,
              residuals.max_linear_row_backward_error, transfer_ratio)
    if not all(math.isfinite(value) for value in values):
        raise OracleInputError("the solved boundary system produced non-finite values")
    return ShellModeSolution(
        degree=degree, coefficients=tuple(coefficients), unknown_order=order, b1_fixed=1.0,
        matrix_shape=(len(matrix), len(matrix[0])), free_surface_value=free_surface,
        layered_surface_value=layered_surface,
        surface_transfer_ratio=transfer_ratio, residuals=residuals,
    )


def solve_four_shell_mode(
    degree: int, radii_m: Iterable[object] = DEFAULT_RADII_M,
    sigmas_sm: Iterable[object] = DEFAULT_SIGMAS_SM,
) -> ShellModeSolution:
    """Solve the seven-equation four-shell mode with b1 fixed at one."""
    degree = _degree(degree)
    if degree > MAX_HARMONIC_DEGREE:
        raise OracleInputError(f"degree must not exceed {MAX_HARMONIC_DEGREE}")
    radii, sigmas = _geometry(radii_m, sigmas_sm)
    return _solve_cached(degree, radii, sigmas)


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(left[index] * right[index] for index in range(3))


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(_dot(vector, vector))


def _legendre_and_derivative(mu: float, max_degree: int) -> list[tuple[float, float]]:
    """Return P_l(mu), dP_l/dmu using the differentiated three-term recurrence."""
    output = [(1.0, 0.0)]
    if max_degree == 0:
        return output
    output.append((mu, 1.0))
    p_previous, d_previous = 1.0, 0.0
    p_current, d_current = mu, 1.0
    for degree in range(1, max_degree):
        p_next = ((2 * degree + 1) * mu * p_current - degree * p_previous) / (degree + 1)
        d_next = ((2 * degree + 1) * (p_current + mu * d_current)
                  - degree * d_previous) / (degree + 1)
        output.append((p_next, d_next))
        p_previous, p_current = p_current, p_next
        d_previous, d_current = d_current, d_next
    return output


def homogeneous_surface_factors(source_radius_over_surface: float, cosine: float) -> tuple[float, float]:
    """Closed-form homogeneous Neumann-sphere sums for radial and tangent dipoles.

    A = sum_{l>=1} (2l+1) t^(l-1) P_l(mu)
    B = sum_{l>=1} ((2l+1)/l) t^(l-1) P'_l(mu)

    The expressions follow from the Legendre generating function and its mu
    derivative; they do not call the shell BVP solver or the projector.
    """
    t = _finite_real(source_radius_over_surface, "source_radius_over_surface")
    mu = _finite_real(cosine, "cosine")
    if not 0.0 <= t < 1.0:
        raise OracleInputError("source_radius_over_surface must satisfy 0 <= t < 1")
    if not -1.0 <= mu <= 1.0:
        raise OracleInputError("cosine must lie in [-1, 1]")
    if t == 0.0:
        return 3.0 * mu, 3.0
    if t < 1.0e-4:
        pairs = _legendre_and_derivative(mu, 24)
        a_value = math.fsum((2 * degree + 1) * t ** (degree - 1) * pairs[degree][0]
                            for degree in range(1, len(pairs)))
        b_value = math.fsum((2 * degree + 1) / degree * t ** (degree - 1) * pairs[degree][1]
                            for degree in range(1, len(pairs)))
        return a_value, b_value
    if mu == 1.0:
        return (3.0 - t) / (1.0 - t) ** 2, (6.0 - 3.0 * t + t * t) / (2.0 * (1.0 - t) ** 3)
    if mu == -1.0:
        return -(3.0 + t) / (1.0 + t) ** 2, (6.0 + 3.0 * t + t * t) / (2.0 * (1.0 + t) ** 3)

    # Decimal arithmetic avoids cancellation as mu approaches either endpoint.
    with localcontext() as context:
        context.prec = 70
        td, md = Decimal(str(t)), Decimal(str(mu))
        one = Decimal(1)
        discriminant = one - 2 * md * td + td * td
        root = discriminant.sqrt()
        inverse_d_three_halves = one / (discriminant * root)
        a_value = (2 * td * (md - td) * inverse_d_three_halves + one / root - one) / td
        integral = ((td - md) / root + md) / (one - md * md)
        b_value = 2 * inverse_d_three_halves + integral / td
    return float(a_value), float(b_value)


def _sensor_points(surface_radius_m: float, sensor_positions_m: Iterable[Iterable[object]]) -> tuple[tuple[float, float, float], ...]:
    try:
        rows = tuple(sensor_positions_m)
    except TypeError as exc:
        raise OracleInputError("sensor_positions_m must be a non-empty sequence of 3D points") from exc
    if not rows:
        raise OracleInputError("sensor_positions_m must contain at least one point")
    sensors = tuple(_vector3(row, f"sensor_positions_m[{index}]") for index, row in enumerate(rows))
    tolerance = max(1.0e-12, surface_radius_m * 1.0e-9)
    for index, sensor in enumerate(sensors):
        radius = _norm(sensor)
        if radius == 0.0 or abs(radius - surface_radius_m) > tolerance:
            raise OracleInputError(f"sensor_positions_m[{index}] must lie on the r4 surface in metres")
    return sensors


def project_dipole_oracle(
    source_position_m: Iterable[object], dipole_moment_am: Iterable[object],
    sensor_positions_m: Iterable[Iterable[object]],
    radii_m: Iterable[object] = DEFAULT_RADII_M,
    sigmas_sm: Iterable[object] = DEFAULT_SIGMAS_SM,
    max_degree: int = 192,
) -> DipoleProjection:
    """Project one point dipole using the independently derived shell transfer.

    This function implements the source-multipole mapping derived in the audit;
    it is not the unavailable proposed ``forward_project_dipoles_four_shell``.
    The returned series is truncated at max_degree. The last-degree contribution
    is exposed as a truncation diagnostic, not as a certified error bound.
    """
    radii, sigmas = _geometry(radii_m, sigmas_sm)
    degree_limit = _degree(max_degree, "max_degree")
    if degree_limit > MAX_HARMONIC_DEGREE:
        raise OracleInputError(f"max_degree must not exceed {MAX_HARMONIC_DEGREE}")
    source = _vector3(source_position_m, "source_position_m")
    moment = _vector3(dipole_moment_am, "dipole_moment_am")
    source_radius = _norm(source)
    if source_radius >= radii[0]:
        raise OracleInputError("source_position_m must be strictly inside r1")
    sensors = _sensor_points(radii[3], sensor_positions_m)
    if source_radius == 0.0:
        source_direction = (0.0, 0.0, 1.0)  # l=1 limit is independent of this choice.
    else:
        source_direction = tuple(component / source_radius for component in source)
    modes = tuple(solve_four_shell_mode(degree, radii, sigmas) for degree in range(1, degree_limit + 1))
    potentials: list[float] = []
    last_degree_max = 0.0
    factor = 1.0 / (4.0 * math.pi * sigmas[0])
    for sensor in sensors:
        sensor_radius = _norm(sensor)
        sensor_direction = tuple(component / sensor_radius for component in sensor)
        cosine = min(1.0, max(-1.0, _dot(source_direction, sensor_direction)))
        radial_moment = _dot(moment, source_direction)
        tangent_moment_projection = _dot(moment, sensor_direction) - cosine * radial_moment
        legendre = _legendre_and_derivative(cosine, degree_limit)
        total = 0.0
        last = 0.0
        for degree, mode in enumerate(modes, start=1):
            source_angular = (degree * radial_moment * legendre[degree][0]
                              + legendre[degree][1] * tangent_moment_projection)
            contribution = (factor * mode.surface_transfer_ratio * source_radius ** (degree - 1)
                            * source_angular / radii[3] ** (degree + 1))
            total += contribution
            if degree == degree_limit:
                last = contribution
        potentials.append(total)
        last_degree_max = max(last_degree_max, abs(last))
    if not all(math.isfinite(value) for value in (*potentials, last_degree_max)):
        raise OracleInputError("dipole projection produced non-finite values")
    return DipoleProjection(tuple(potentials), degree_limit, source_radius, last_degree_max)


def homogeneous_neumann_dipole_reference(
    source_position_m: Iterable[object], dipole_moment_am: Iterable[object],
    sensor_positions_m: Iterable[Iterable[object]], outer_radius_m: float,
    conductivity_sm: float,
) -> tuple[float, ...]:
    """Independent closed-form homogeneous-sphere reference on r=R.

    Starting from V_inf = q.(r-rs)/(4*pi*sigma*|r-rs|^3), expand the source
    derivative of the Laplace Green function into Legendre modes. A zero-normal-
    current boundary multiplies each degree-l surface mode by (2l+1)/l. Summing
    those modes with the Legendre generating function gives the closed factors A
    and B in homogeneous_surface_factors; no shell matrix or project function is
    used here.
    """
    radius = _finite_real(outer_radius_m, "outer_radius_m")
    sigma = _finite_real(conductivity_sm, "conductivity_sm")
    if radius <= 0.0 or radius > 1.0:
        raise OracleInputError("outer_radius_m must be in (0, 1] metres")
    if sigma <= 0.0:
        raise OracleInputError("conductivity_sm must be positive S/m")
    source = _vector3(source_position_m, "source_position_m")
    moment = _vector3(dipole_moment_am, "dipole_moment_am")
    source_radius = _norm(source)
    if source_radius >= radius:
        raise OracleInputError("source_position_m must be strictly inside the homogeneous sphere")
    sensors = _sensor_points(radius, sensor_positions_m)
    if source_radius == 0.0:
        return tuple(3.0 * _dot(moment, tuple(component / _norm(sensor) for component in sensor))
                     / (4.0 * math.pi * sigma * radius * radius) for sensor in sensors)
    source_direction = tuple(component / source_radius for component in source)
    t = source_radius / radius
    values = []
    scale = 1.0 / (4.0 * math.pi * sigma * radius * radius)
    for sensor in sensors:
        sensor_direction = tuple(component / _norm(sensor) for component in sensor)
        cosine = min(1.0, max(-1.0, _dot(source_direction, sensor_direction)))
        radial_moment = _dot(moment, source_direction)
        tangent_projection = _dot(moment, sensor_direction) - cosine * radial_moment
        radial_factor, tangent_factor = homogeneous_surface_factors(t, cosine)
        values.append(scale * (radial_moment * radial_factor + tangent_projection * tangent_factor))
    if not all(math.isfinite(value) for value in values):
        raise OracleInputError("homogeneous reference produced non-finite values")
    return tuple(values)


def _unit(vector: Sequence[float]) -> tuple[float, float, float]:
    norm = _norm(vector)
    if norm == 0.0:
        raise OracleInputError("cannot normalize a zero vector")
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def run_default_audit() -> dict[str, object]:
    """Run deterministic mathematical fixtures and return finite JSON data."""
    radius_sets = (
        (0.061, 0.066, 0.074, 0.089),
        (0.070, 0.078, 0.085, 0.100),
        DEFAULT_RADII_M,
    )
    degrees = (1, 2, 3, 7, 16, 32)
    homogeneous_cases: list[dict[str, float | int]] = []
    for radii in radius_sets:
        equal_sigmas = (0.33, 0.33, 0.33, 0.33)
        for degree in degrees:
            solution = solve_four_shell_mode(degree, radii, equal_sigmas)
            expected = (2.0 * degree + 1.0) / degree
            homogeneous_cases.append({
                "degree": degree,
                "absolute_ratio_error": abs(solution.surface_transfer_ratio - expected),
                "relative_ratio_error": abs(solution.surface_transfer_ratio - expected) / expected,
                "scaled_boundary_residual": max(
                    solution.residuals.max_potential_continuity_scaled,
                    solution.residuals.max_current_continuity_scaled,
                    solution.residuals.outer_current_scaled,
                ),
            })

    layered_degrees = (1, 2, 4, 8, 16)
    layered_cases = []
    for degree in layered_degrees:
        solution = solve_four_shell_mode(degree)
        layered_cases.append({
            "degree": degree,
            "surface_transfer_ratio": solution.surface_transfer_ratio,
            "coefficients": solution.coefficient_map(),
            "residuals": asdict(solution.residuals),
        })

    radii = DEFAULT_RADII_M
    homogeneous_sigmas = (0.33, 0.33, 0.33, 0.33)
    direction_vectors = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
                         (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
                         (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
    direction_vectors += tuple((sx, sy, sz) for sx in (-1.0, 1.0)
                               for sy in (-1.0, 1.0) for sz in (-1.0, 1.0))
    sensors = tuple(tuple(radii[3] * value for value in _unit(direction))
                    for direction in direction_vectors)
    source_direction = _unit((0.3, -0.4, math.sqrt(0.75)))
    tangent_direction = _unit((-source_direction[1], source_direction[0], 0.0))
    moment_size = 1.0e-9
    projector_cases: list[dict[str, float | int | str]] = []
    source_radii = (0.0, 0.020, 0.050, 0.070)
    for source_radius in source_radii:
        source = tuple(source_radius * value for value in source_direction)
        orientations = (("center_xyz", (moment_size, 0.0, 0.0)),) if source_radius == 0.0 else (
            ("radial", tuple(moment_size * value for value in source_direction)),
            ("tangential", tuple(moment_size * value for value in tangent_direction)),
        )
        for orientation_name, moment in orientations:
            projection = project_dipole_oracle(source, moment, sensors, radii,
                                               homogeneous_sigmas, max_degree=192)
            reference = homogeneous_neumann_dipole_reference(
                source, moment, sensors, radii[3], homogeneous_sigmas[0])
            max_abs_error = max(abs(left - right)
                                for left, right in zip(projection.surface_potentials_v, reference))
            scale = _norm(moment) / (4.0 * math.pi * homogeneous_sigmas[0] * radii[3] ** 2)
            projector_cases.append({
                "source_radius_m": source_radius,
                "orientation": orientation_name,
                "sensor_count": len(sensors),
                "max_absolute_error_v": max_abs_error,
                "max_scaled_error": max_abs_error / max(scale, _RESIDUAL_FLOOR),
                "last_degree_max_abs_v": projection.last_degree_max_abs_v,
            })

    max_hom_abs = max(row["absolute_ratio_error"] for row in homogeneous_cases)
    max_hom_rel = max(row["relative_ratio_error"] for row in homogeneous_cases)
    max_hom_scaled_residual = max(row["scaled_boundary_residual"] for row in homogeneous_cases)
    max_layered_scaled = max(
        max(row["residuals"][key] for key in (
            "max_potential_continuity_scaled", "max_current_continuity_scaled", "outer_current_scaled"))
        for row in layered_cases
    )
    return {
        "status": "HOLD / SYNTHETIC_ONLY",
        "candidate_implementation_tested": False,
        "solver_backend": solver_backend(),
        "system": {
            "stated_unknowns": list(_UNKNOWN_ORDER),
            "fixed_normalization": "b1=1",
            "boundary_equation_count": 7,
            "matrix_shape": [7, 7],
            "eight_by_eight_reconciliation": (
                "The stated seven unknowns plus seven boundary equations form 7x7. "
                "An 8x8 form requires b1 as an eighth unknown and b1=1 as an eighth equation."
            ),
        },
        "homogeneous_limit": {
            "case_count": len(homogeneous_cases),
            "degrees": list(degrees),
            "radius_sets_m": [list(values) for values in radius_sets],
            "expected_ratio": "(2*l+1)/l",
            "max_absolute_ratio_error": max_hom_abs,
            "max_relative_ratio_error": max_hom_rel,
            "max_scaled_boundary_residual": max_hom_scaled_residual,
        },
        "layered_case": {
            "radii_m": list(DEFAULT_RADII_M),
            "sigmas_sm": list(DEFAULT_SIGMAS_SM),
            "degrees": list(layered_degrees),
            "max_scaled_boundary_residual": max_layered_scaled,
            "mode_results": layered_cases,
        },
        "homogeneous_dipole_reference_comparison": {
            "reference": "independent closed-form Legendre-generating-function sum",
            "conductivities_sm": list(homogeneous_sigmas),
            "max_degree_projector": 192,
            "case_count": len(projector_cases),
            "sensor_comparisons": sum(int(row["sensor_count"]) for row in projector_cases),
            "max_absolute_error_v": max(float(row["max_absolute_error_v"]) for row in projector_cases),
            "max_scaled_error": max(float(row["max_scaled_error"]) for row in projector_cases),
            "cases": projector_cases,
        },
        "input_contract": {
            "degree": "positive integer l>=1; booleans and l=0 rejected",
            "radii": "four finite, positive, strictly increasing metre values; r4<=1 m",
            "conductivities": "four finite positive S/m values; no unit conversion or inference",
            "source": "finite 3-vector in metres, strictly inside r1; center uses its l=1 limit",
            "dipole_moment": "finite 3-vector in A*m",
            "sensors": "non-empty finite Nx3 metre coordinates on the r4 sphere",
            "series": f"finite harmonic truncation, 1<=max_degree<={MAX_HARMONIC_DEGREE}; last term is diagnostic only",
        },
        "limitations": [
            "No Round 6/Gemini implementation was found in the checked repository, open PR patches, or claim-audit branch.",
            "The oracle tests the equations and its independently derived projector, not the missing candidate module.",
            "The outer boundary is the stated zero-normal-current condition; this is not a complete comparison to an air-shell solver or MNE implementation.",
            "Finite l truncation is not a certified error bound, especially for sources close to r1.",
            "All results are synthetic mathematical checks; no empirical data or biological validity is addressed.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON instead of indented JSON")
    args = parser.parse_args(argv)
    print(json.dumps(run_default_audit(), sort_keys=True,
                     indent=None if args.compact else 2, allow_nan=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the module CLI
    raise SystemExit(main())
