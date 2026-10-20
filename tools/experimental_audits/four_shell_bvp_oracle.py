"""Independent numerical oracle for Næss et al.'s four-sphere BVP.

This synthetic-only artifact independently assembles the paper's seven boundary
equations from its shell-scaled radial basis, and compares the resulting dipole
projection with a closed-form homogeneous-sphere reference. It does not implement
or test a production/Gemini candidate and never imports the associated GPL code.

Coordinates are metres, conductivities S/m, dipole moments A*m, and potentials V.
NumPy is used only when already installed; otherwise the small systems use a
standard-library partial-pivot solver. No dependency installation is attempted.
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

NAESS_2017_RADII_M = (0.079, 0.080, 0.085, 0.090)
NAESS_2017_SOURCE_RADIUS_M = 0.078  # 1 mm inside the 7.9 cm brain/CSF boundary.
NAESS_2017_SKULL_FACTORS = (20, 40, 80)
NAESS_2017_SIGMAS_SM_BY_K = {
    factor: (0.33, 1.65, 0.33 / factor, 0.33)
    for factor in NAESS_2017_SKULL_FACTORS
}
PROMPT_PROPOSAL_RADII_M = (0.078, 0.080, 0.086, 0.095)
PROMPT_PROPOSAL_SIGMAS_SM = (0.33, 1.79, 0.0042, 0.33)
DEFAULT_RADII_M = NAESS_2017_RADII_M
DEFAULT_SIGMAS_SM = NAESS_2017_SIGMAS_SM_BY_K[80]
MAX_HARMONIC_DEGREE = 2048
_RESIDUAL_FLOOR = 1.0e-300

_A_INDEX = (0, 1, 3, 5)
_B_INDEX = {1: 2, 2: 4, 3: 6}
_UNKNOWN_ORDER = ("a1", "a2", "b2", "a3", "b3", "a4", "b4")
_NAESS_UNKNOWN_ORDER = ("A1", "A2", "B2", "A3", "B3", "A4", "B4")

__all__ = [
    "BoundaryResiduals", "DipoleProjection", "NAESS_2017_RADII_M",
    "NAESS_2017_SIGMAS_SM_BY_K", "NAESS_2017_SOURCE_RADIUS_M",
    "NAESS_2017_SKULL_FACTORS", "OracleInputError", "PaperModeSolution",
    "PROMPT_PROPOSAL_RADII_M", "PROMPT_PROPOSAL_SIGMAS_SM",
    "ShellModeSolution", "SurfaceComparison", "compare_surface_potentials",
    "homogeneous_neumann_dipole_reference", "homogeneous_surface_factors",
    "naess_2017_conductivities", "project_dipole_oracle", "run_default_audit",
    "solve_four_shell_mode", "solve_naess_basis_mode", "solver_backend",
]


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
    row_scaled_condition_inf: float

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
    basis_name: str


@dataclass(frozen=True)
class PaperModeSolution:
    """One degree-l mode in the coefficient normalization of Næss et al. (2017)."""

    degree: int
    source_radius_m: float
    coefficients: tuple[float, ...]
    unknown_order: tuple[str, ...]
    matrix_shape: tuple[int, int]
    singular_surface_value: float
    layered_surface_value: float
    surface_transfer_ratio: float
    transfer_consistency_scaled: float
    source_surface_normalization_underflow: bool
    residuals: BoundaryResiduals
    row_scaled_condition_inf: float

    def coefficient_map(self) -> dict[str, float]:
        return {name: self.coefficients[index] for index, name in enumerate(self.unknown_order)}


@dataclass(frozen=True)
class SurfaceComparison:
    """Dimension-checked comparison result for an independent candidate caller."""

    sample_count: int
    scale_v: float
    max_absolute_error_v: float
    rms_absolute_error_v: float
    max_scaled_error: float
    rms_scaled_error: float


def naess_2017_conductivities(skull_factor: int) -> tuple[float, float, float, float]:
    """Return the paper's Table 1 conductivities for K in {20, 40, 80}.

    The four entries are brain, CSF, skull, and scalp in S/m. This documents
    the paper's parameter variants; it is not a recommendation for real heads.
    """
    if isinstance(skull_factor, bool) or not isinstance(skull_factor, Integral) or int(skull_factor) not in NAESS_2017_SIGMAS_SM_BY_K:
        raise OracleInputError("Næss 2017 skull_factor must be an integer 20, 40, or 80")
    return NAESS_2017_SIGMAS_SM_BY_K[int(skull_factor)]


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
    surface_scale = radii[-1] * radii[-1]
    if surface_scale == 0.0 or not math.isfinite(1.0 / surface_scale):
        raise OracleInputError("r4 is too small for a finite surface dipole normalization")
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


def _condition_inf_row_equilibrated(matrix: Sequence[Sequence[float]]) -> float:
    """Estimate ||A||_inf*||A^-1||_inf after per-equation row scaling."""
    row_scales = [max((abs(value) for value in row), default=0.0) for row in matrix]
    if any(scale == 0.0 for scale in row_scales):
        raise OracleInputError("boundary matrix has a zero equation row")
    equilibrated = [[value / row_scales[index] for value in row]
                    for index, row in enumerate(matrix)]
    size = len(equilibrated)
    if any(len(row) != size for row in equilibrated):
        raise OracleInputError("boundary matrix must be square for conditioning estimate")
    inverse_columns = []
    for column in range(size):
        unit = [0.0] * size
        unit[column] = 1.0
        inverse_columns.append(_solve_linear(equilibrated, unit))
    norm_a = max(sum(abs(value) for value in row) for row in equilibrated)
    norm_inverse = max(
        sum(abs(inverse_columns[column][row]) for column in range(size))
        for row in range(size)
    )
    estimate = norm_a * norm_inverse
    if not math.isfinite(estimate):
        raise OracleInputError("row-equilibrated matrix condition estimate is non-finite")
    return estimate


@lru_cache(maxsize=8192)
def _normalized_condition_cached(
    degree: int, radii: tuple[float, ...], sigmas: tuple[float, ...]
) -> float:
    matrix, _, _ = _build_system(degree, radii, sigmas)
    return _condition_inf_row_equilibrated(matrix)


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
    row_condition = _normalized_condition_cached(degree, radii, sigmas)
    values = (*coefficients, free_surface, layered_surface,
              residuals.max_potential_continuity_abs,
              residuals.max_potential_continuity_scaled,
              residuals.max_current_continuity_abs_sm2,
              residuals.max_current_continuity_scaled,
              residuals.outer_current_abs_sm2,
              residuals.outer_current_scaled,
              residuals.max_linear_row_backward_error, transfer_ratio, row_condition)
    if not all(math.isfinite(value) for value in values):
        raise OracleInputError("the solved boundary system produced non-finite values")
    return ShellModeSolution(
        degree=degree, coefficients=tuple(coefficients), unknown_order=order, b1_fixed=1.0,
        matrix_shape=(len(matrix), len(matrix[0])), free_surface_value=free_surface,
        layered_surface_value=layered_surface,
        surface_transfer_ratio=transfer_ratio, residuals=residuals,
        row_scaled_condition_inf=row_condition,
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


def _paper_basis_terms(
    degree: int, radius: float, shell: int, radii: tuple[float, ...], source_radius: float
) -> tuple[float, float, float, float]:
    if shell == 0:
        plus = (radius / radii[0]) ** degree
        minus = (source_radius / radius) ** (degree + 1)
    else:
        shell_radius = radii[shell]
        plus = (radius / shell_radius) ** degree
        minus = (shell_radius / radius) ** (degree + 1)
    return plus, minus, degree * plus / radius, -(degree + 1) * minus / radius


def _build_naess_system(
    degree: int, radii: tuple[float, ...], sigmas: tuple[float, ...], source_radius: float
) -> tuple[list[list[float]], list[float], tuple[str, ...]]:
    """Assemble Eq. 5–6's shell-scaled basis and Eqs. 2–4's seven conditions."""
    matrix: list[list[float]] = []
    rhs: list[float] = []

    def append_side(row: list[float], right: list[float], shell: int, radius: float,
                    sign: float, current: bool) -> None:
        plus, minus, d_plus, d_minus = _paper_basis_terms(
            degree, radius, shell, radii, source_radius
        )
        if current:
            plus *= sigmas[shell]
            minus *= sigmas[shell]
            d_plus *= sigmas[shell]
            d_minus *= sigmas[shell]
            plus, minus = d_plus, d_minus
        row[_A_INDEX[shell]] += sign * plus
        if shell == 0:
            # Eq. 5 fixes the inner singular source term to (rz/r)^(l+1).
            right[0] -= sign * minus
        else:
            row[_B_INDEX[shell]] += sign * minus

    for boundary_radius, inner_shell in ((radii[0], 0), (radii[1], 1), (radii[2], 2)):
        for current in (False, True):
            row = [0.0] * 7
            right = [0.0]
            append_side(row, right, inner_shell, boundary_radius, +1.0, current)
            append_side(row, right, inner_shell + 1, boundary_radius, -1.0, current)
            matrix.append(row)
            rhs.append(right[0])

    # Eq. 4 is dPhi4/dr=0; multiplying by positive sigma4 is equivalent.
    _, _, d_plus, d_minus = _paper_basis_terms(degree, radii[3], 3, radii, source_radius)
    matrix.append([0.0, 0.0, 0.0, 0.0, 0.0,
                   sigmas[3] * d_plus, sigmas[3] * d_minus])
    rhs.append(0.0)
    return matrix, rhs, _NAESS_UNKNOWN_ORDER


def _paper_phi_and_derivative(
    degree: int, shell: int, radius: float, source_radius: float,
    coefficients: Sequence[float], radii: tuple[float, ...]
) -> tuple[float, float]:
    plus, minus, d_plus, d_minus = _paper_basis_terms(
        degree, radius, shell, radii, source_radius
    )
    a = coefficients[_A_INDEX[shell]]
    b = 1.0 if shell == 0 else coefficients[_B_INDEX[shell]]
    return a * plus + b * minus, a * d_plus + b * d_minus


@lru_cache(maxsize=8192)
def _naess_condition_cached(
    degree: int, radii: tuple[float, ...], sigmas: tuple[float, ...]
) -> float:
    # The matrix is independent of source depth; only the fixed-source RHS changes.
    matrix, _, _ = _build_naess_system(degree, radii, sigmas, radii[0] / 2.0)
    return _condition_inf_row_equilibrated(matrix)


@lru_cache(maxsize=8192)
def _solve_naess_cached(
    degree: int, radii: tuple[float, ...], sigmas: tuple[float, ...], source_radius: float
) -> PaperModeSolution:
    matrix, rhs, order = _build_naess_system(degree, radii, sigmas, source_radius)
    if not all(math.isfinite(value) for row in matrix for value in row) or not all(
        math.isfinite(value) for value in rhs
    ):
        raise OracleInputError("Næss-basis boundary matrix contains non-finite values")
    coefficients = _solve_linear(matrix, rhs)
    potential_abs: list[float] = []
    potential_scaled: list[float] = []
    current_abs: list[float] = []
    current_scaled: list[float] = []
    for boundary_radius, inner_shell in ((radii[0], 0), (radii[1], 1), (radii[2], 2)):
        p_inner, d_inner = _paper_phi_and_derivative(
            degree, inner_shell, boundary_radius, source_radius, coefficients, radii
        )
        p_outer, d_outer = _paper_phi_and_derivative(
            degree, inner_shell + 1, boundary_radius, source_radius, coefficients, radii
        )
        j_inner = sigmas[inner_shell] * d_inner
        j_outer = sigmas[inner_shell + 1] * d_outer
        p_res, j_res = abs(p_inner - p_outer), abs(j_inner - j_outer)
        potential_abs.append(p_res)
        potential_scaled.append(p_res / max(abs(p_inner) + abs(p_outer), _RESIDUAL_FLOOR))
        current_abs.append(j_res)
        current_scaled.append(j_res / max(abs(j_inner) + abs(j_outer), _RESIDUAL_FLOOR))

    _, outer_derivative = _paper_phi_and_derivative(
        degree, 3, radii[3], source_radius, coefficients, radii
    )
    outer_current = sigmas[3] * outer_derivative
    _, _, outer_d_plus, outer_d_minus = _paper_basis_terms(
        degree, radii[3], 3, radii, source_radius
    )
    outer_scale = sigmas[3] * (
        abs(coefficients[_A_INDEX[3]] * outer_d_plus)
        + abs(coefficients[_B_INDEX[3]] * outer_d_minus)
    )
    surface_value = coefficients[_A_INDEX[3]] + coefficients[_B_INDEX[3]]
    singular_surface = (source_radius / radii[3]) ** (degree + 1)
    normalization_underflow = singular_surface == 0.0
    normalized_solution = solve_four_shell_mode(degree, radii, sigmas)
    expected_surface = normalized_solution.surface_transfer_ratio * singular_surface
    transfer_scale = max(abs(surface_value) + abs(expected_surface), _RESIDUAL_FLOOR)
    transfer_consistency = abs(surface_value - expected_surface) / transfer_scale
    transfer_ratio = (normalized_solution.surface_transfer_ratio if normalization_underflow
                      else surface_value / singular_surface)
    residuals = BoundaryResiduals(
        max_potential_continuity_abs=max(potential_abs),
        max_potential_continuity_scaled=max(potential_scaled),
        max_current_continuity_abs_sm2=max(current_abs),
        max_current_continuity_scaled=max(current_scaled),
        outer_current_abs_sm2=abs(outer_current),
        outer_current_scaled=abs(outer_current) / max(outer_scale, _RESIDUAL_FLOOR),
        max_linear_row_backward_error=_row_backward_error(matrix, rhs, coefficients),
    )
    condition = _naess_condition_cached(degree, radii, sigmas)
    values = (*coefficients, surface_value, singular_surface, transfer_ratio,
              transfer_consistency, condition, residuals.max_potential_continuity_abs,
              residuals.max_potential_continuity_scaled,
              residuals.max_current_continuity_abs_sm2,
              residuals.max_current_continuity_scaled,
              residuals.outer_current_abs_sm2, residuals.outer_current_scaled,
              residuals.max_linear_row_backward_error)
    if not all(math.isfinite(value) for value in values):
        raise OracleInputError("Næss-basis solve produced non-finite values")
    return PaperModeSolution(
        degree=degree, source_radius_m=source_radius, coefficients=tuple(coefficients),
        unknown_order=order, matrix_shape=(len(matrix), len(matrix[0])),
        singular_surface_value=singular_surface, layered_surface_value=surface_value,
        surface_transfer_ratio=transfer_ratio,
        transfer_consistency_scaled=transfer_consistency,
        source_surface_normalization_underflow=normalization_underflow,
        residuals=residuals, row_scaled_condition_inf=condition,
    )


def solve_naess_basis_mode(
    degree: int, source_radius_m: float,
    radii_m: Iterable[object] = DEFAULT_RADII_M,
    sigmas_sm: Iterable[object] = DEFAULT_SIGMAS_SM,
) -> PaperModeSolution:
    """Solve one radial harmonic in the source/radius normalization of Næss Eqs. 5–6.

    The seven unknowns are (A1,A2,B2,A3,B3,A4,B4); the source singular mode
    (rz/r)^(l+1) in shell 1 is fixed. This independently assembles the seven
    interface/outer-boundary equations rather than using the paper's recurrences
    or the GPL-3.0-associated implementation.
    """
    degree = _degree(degree)
    if degree > MAX_HARMONIC_DEGREE:
        raise OracleInputError(f"degree must not exceed {MAX_HARMONIC_DEGREE}")
    radii, sigmas = _geometry(radii_m, sigmas_sm)
    source_radius = _finite_real(source_radius_m, "source_radius_m")
    if not 0.0 < source_radius < radii[0]:
        raise OracleInputError("Næss basis requires 0 < source_radius_m < r1")
    return _solve_naess_cached(degree, radii, sigmas, source_radius)


def compare_surface_potentials(
    reference_v: Iterable[object], candidate_v: Iterable[object], *, scale_v: float
) -> SurfaceComparison:
    """Compare two caller-supplied surface vectors without importing either engine.

    This public adapter is suitable for future production-engine tests: pass its
    surface vector and the oracle reference vector, plus a predeclared physical
    scale in volts. It performs no candidate discovery or execution.
    """
    try:
        reference = tuple(_finite_real(value, f"reference_v[{index}]")
                          for index, value in enumerate(reference_v))
        candidate = tuple(_finite_real(value, f"candidate_v[{index}]")
                          for index, value in enumerate(candidate_v))
    except TypeError as exc:
        raise OracleInputError("reference_v and candidate_v must be iterable vectors") from exc
    if not reference or len(reference) != len(candidate):
        raise OracleInputError("reference_v and candidate_v must be non-empty vectors of equal length")
    scale = _finite_real(scale_v, "scale_v")
    if scale <= 0.0:
        raise OracleInputError("scale_v must be positive volts")
    errors = tuple(abs(left - right) for left, right in zip(reference, candidate))
    if not all(math.isfinite(value) for value in errors):
        raise OracleInputError("surface comparison produced non-finite errors")
    max_error = max(errors)
    rms = (max_error * math.sqrt(math.fsum((value / max_error) ** 2 for value in errors)
                                 / len(errors)) if max_error else 0.0)
    max_scaled = max_error / scale
    rms_scaled = rms / scale
    if not all(math.isfinite(value) for value in (rms, max_scaled, rms_scaled)):
        raise OracleInputError("surface comparison scale produces non-finite error metrics")
    return SurfaceComparison(
        sample_count=len(errors), scale_v=scale,
        max_absolute_error_v=max_error, rms_absolute_error_v=rms,
        max_scaled_error=max_scaled, rms_scaled_error=rms_scaled,
    )


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(left[index] * right[index] for index in range(3))


def _norm(vector: Sequence[float]) -> float:
    return math.hypot(*vector)


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
    max_degree: int = 512,
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
        modes = tuple(solve_four_shell_mode(degree, radii, sigmas)
                      for degree in range(1, degree_limit + 1))
        basis_name = "center_limit_normalized_transfer"
    else:
        source_direction = tuple(component / source_radius for component in source)
        modes = tuple(solve_naess_basis_mode(degree, source_radius, radii, sigmas)
                      for degree in range(1, degree_limit + 1))
        basis_name = "naess_2017_equations_5_6"
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
            if source_radius == 0.0:
                source_radial_scale = (
                    mode.surface_transfer_ratio / radii[3] ** 2 if degree == 1 else 0.0
                )
            else:
                source_radial_scale = (
                    mode.surface_transfer_ratio * (source_radius / radii[3]) ** (degree - 1)
                    / radii[3] ** 2
                )
            contribution = factor * source_radial_scale * source_angular
            total += contribution
            if degree == degree_limit:
                last = contribution
        potentials.append(total)
        last_degree_max = max(last_degree_max, abs(last))
    if not all(math.isfinite(value) for value in (*potentials, last_degree_max)):
        raise OracleInputError("dipole projection produced non-finite values")
    return DipoleProjection(tuple(potentials), degree_limit, source_radius,
                            last_degree_max, basis_name)


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
    """Run paper-parameter and prompt-parameter mathematical fixtures as finite JSON."""
    radius_sets = (
        (0.061, 0.066, 0.074, 0.089),
        (0.070, 0.078, 0.085, 0.100),
        NAESS_2017_RADII_M,
        PROMPT_PROPOSAL_RADII_M,
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
                "row_scaled_condition_inf": solution.row_scaled_condition_inf,
            })

    layered_degrees = (1, 2, 4, 8, 16)
    paper_mode_cases = []
    for skull_factor in NAESS_2017_SKULL_FACTORS:
        sigmas = naess_2017_conductivities(skull_factor)
        for degree in layered_degrees:
            solution = solve_naess_basis_mode(
                degree, NAESS_2017_SOURCE_RADIUS_M, NAESS_2017_RADII_M, sigmas
            )
            paper_mode_cases.append({
                "skull_factor_K": skull_factor,
                "degree": degree,
                "source_radius_m": NAESS_2017_SOURCE_RADIUS_M,
                "surface_transfer_ratio": solution.surface_transfer_ratio,
                "paper_surface_coefficient": solution.layered_surface_value,
                "transfer_consistency_scaled": solution.transfer_consistency_scaled,
                "row_scaled_condition_inf": solution.row_scaled_condition_inf,
                "coefficients": solution.coefficient_map(),
                "residuals": asdict(solution.residuals),
            })

    # The paper's source coefficient gives source-depth dependence r_z^(l-1).
    scaling_degrees = (1, 2, 4, 8, 16)
    scaling_depths = (0.020, 0.050, NAESS_2017_SOURCE_RADIUS_M)
    scaling_cases = []
    for degree in scaling_degrees:
        sigma = naess_2017_conductivities(80)
        modes = [solve_naess_basis_mode(degree, depth, NAESS_2017_RADII_M, sigma)
                 for depth in scaling_depths]
        observed = (modes[-1].layered_surface_value / scaling_depths[-1] ** 2) / (
            modes[0].layered_surface_value / scaling_depths[0] ** 2
        )
        expected = (scaling_depths[-1] / scaling_depths[0]) ** (degree - 1)
        scaling_cases.append({
            "degree": degree,
            "shallow_source_m": scaling_depths[0],
            "deep_source_m": scaling_depths[-1],
            "observed_scaled_mode_ratio": observed,
            "expected_source_depth_ratio": expected,
            "relative_scaling_error": abs(observed - expected) / max(abs(expected), _RESIDUAL_FLOOR),
        })

    radii = NAESS_2017_RADII_M
    homogeneous_sigmas = (0.33, 0.33, 0.33, 0.33)
    direction_vectors = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
                         (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
                         (0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
    direction_vectors += tuple((sx, sy, sz) for sx in (-1.0, 1.0)
                               for sy in (-1.0, 1.0) for sz in (-1.0, 1.0))
    sensors = tuple(tuple(radii[3] * value for value in _unit(direction))
                    for direction in direction_vectors)
    source_direction = (0.0, 0.0, 1.0)
    tangent_direction = (0.0, 1.0, 0.0)
    moment_size = 1.0e-7
    projector_cases: list[dict[str, float | int | str]] = []
    source_radii = (0.0, 0.020, 0.050, NAESS_2017_SOURCE_RADIUS_M)
    projector_max_degree = 512
    for source_radius in source_radii:
        source = tuple(source_radius * value for value in source_direction)
        orientations = (("center_xyz", (moment_size, 0.0, 0.0)),) if source_radius == 0.0 else (
            ("radial_z", tuple(moment_size * value for value in source_direction)),
            ("tangential_y", tuple(moment_size * value for value in tangent_direction)),
            ("tilted_45deg", tuple(moment_size * value for value in _unit((0.0, 1.0, 1.0)))),
        )
        for orientation_name, moment in orientations:
            projection = project_dipole_oracle(
                source, moment, sensors, radii, homogeneous_sigmas, max_degree=projector_max_degree
            )
            reference = homogeneous_neumann_dipole_reference(
                source, moment, sensors, radii[3], homogeneous_sigmas[0])
            scale = _norm(moment) / (4.0 * math.pi * homogeneous_sigmas[0] * radii[3] ** 2)
            comparison = compare_surface_potentials(reference, projection.surface_potentials_v,
                                                    scale_v=scale)
            projector_cases.append({
                "source_radius_m": source_radius,
                "orientation": orientation_name,
                "sensor_count": len(sensors),
                "max_absolute_error_v": comparison.max_absolute_error_v,
                "max_scaled_error": comparison.max_scaled_error,
                "last_degree_max_abs_v": projection.last_degree_max_abs_v,
                "basis_name": projection.basis_name,
            })

    # A symmetry-axis radial series has positive terms; its tail must decrease as L grows.
    convergence_source = (0.0, 0.0, NAESS_2017_SOURCE_RADIUS_M)
    convergence_moment = (0.0, 0.0, moment_size)
    convergence_sensor = ((0.0, 0.0, radii[3]),)
    convergence_reference = homogeneous_neumann_dipole_reference(
        convergence_source, convergence_moment, convergence_sensor, radii[3], homogeneous_sigmas[0]
    )
    convergence_scale = moment_size / (4.0 * math.pi * homogeneous_sigmas[0] * radii[3] ** 2)
    convergence_cases = []
    for limit in (8, 16, 32, 64, 128, 256, 512):
        projection = project_dipole_oracle(
            convergence_source, convergence_moment, convergence_sensor, radii,
            homogeneous_sigmas, max_degree=limit,
        )
        comparison = compare_surface_potentials(
            convergence_reference, projection.surface_potentials_v, scale_v=convergence_scale
        )
        convergence_cases.append({
            "max_degree": limit,
            "max_absolute_error_v": comparison.max_absolute_error_v,
            "max_scaled_error": comparison.max_scaled_error,
            "last_degree_max_abs_v": projection.last_degree_max_abs_v,
        })

    max_hom_abs = max(row["absolute_ratio_error"] for row in homogeneous_cases)
    max_hom_rel = max(row["relative_ratio_error"] for row in homogeneous_cases)
    max_hom_scaled_residual = max(row["scaled_boundary_residual"] for row in homogeneous_cases)
    paper_residual_keys = (
        "max_potential_continuity_scaled", "max_current_continuity_scaled", "outer_current_scaled"
    )
    max_paper_scaled_residual = max(
        row["residuals"][key] for row in paper_mode_cases for key in paper_residual_keys
    )
    max_paper_condition = max(row["row_scaled_condition_inf"] for row in paper_mode_cases)
    return {
        "status": "HOLD / SYNTHETIC_ONLY",
        "candidate_implementation_tested": False,
        "solver_backend": solver_backend(),
        "source_provenance": {
            "citation": "Næss et al. (2017), Corrected Four-Sphere Head Model for EEG Signals, Front. Hum. Neurosci. 11:490",
            "doi": "10.3389/fnhum.2017.00490",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC5651266/",
            "article_license": "Creative Commons Attribution (CC BY); attribute authors and DOI",
            "implementation_license_boundary": "associated Neuroinflab/fourspheremodel GPL-3.0 code not used, copied, imported, or executed",
        },
        "paper_conventions": {
            "layers": ["brain", "CSF", "skull", "scalp"],
            "radii_m": list(NAESS_2017_RADII_M),
            "conductivity_order_sm": list(naess_2017_conductivities(80)),
            "skull_factor_variants_K": list(NAESS_2017_SKULL_FACTORS),
            "source_radius_m": NAESS_2017_SOURCE_RADIUS_M,
            "source_depth_below_brain_csf_boundary_m": NAESS_2017_RADII_M[0] - NAESS_2017_SOURCE_RADIUS_M,
            "figure_dipole_moment_am": 1.0e-7,
            "figure_orientations": ["radial +z", "tangential +y", "45 degrees in x=0 plane"],
            "potential_sign_convention": "V_inf=q dot (r-rs)/(4*pi*sigma*|r-rs|^3)",
            "associated_legendre_convention": "Condon-Shortley P_l^1(mu)=-sqrt(1-mu^2)*dP_l/dmu",
            "tangential_mapping": "-p*sin(phi)*P_l^1(mu) = (q_t dot e)*P_l'(mu) for q_t=+y and source +z",
            "boundary_conditions": ["potential continuity at r1-r3", "sigma*dPhi/dr continuity at r1-r3", "dPhi4/dr(r4)=0"],
        },
        "prompt_proposal_parameters_not_paper_table": {
            "radii_m": list(PROMPT_PROPOSAL_RADII_M),
            "sigmas_sm": list(PROMPT_PROPOSAL_SIGMAS_SM),
            "matches_naess_2017_table_1": False,
        },
        "paper_system": {
            "unknown_order": list(_NAESS_UNKNOWN_ORDER),
            "fixed_source_term": "(rz/r)^(l+1) in brain shell",
            "boundary_equations": 7,
            "matrix_shape": [7, 7],
            "eight_by_eight_reconciliation": "An 8x8 form requires promoting the fixed source amplitude to an unknown and adding its normalization equation.",
        },
        "normalized_prompt_basis_system": {
            "unknown_order": list(_UNKNOWN_ORDER),
            "fixed_normalization": "b1=1",
            "matrix_shape": [7, 7],
            "basis_relation": "a rescaling of the paper's fixed singular source mode; transfer ratios agree across source depth",
        },
        "homogeneous_limit": {
            "case_count": len(homogeneous_cases),
            "degrees": list(degrees),
            "radius_sets_m": [list(values) for values in radius_sets],
            "expected_transfer_ratio": "(2*l+1)/l",
            "max_absolute_ratio_error": max_hom_abs,
            "max_relative_ratio_error": max_hom_rel,
            "max_scaled_boundary_residual": max_hom_scaled_residual,
        },
        "paper_layered_boundary_audit": {
            "mode_case_count": len(paper_mode_cases),
            "degrees": list(layered_degrees),
            "skull_factors_K": list(NAESS_2017_SKULL_FACTORS),
            "max_scaled_boundary_residual": max_paper_scaled_residual,
            "max_row_scaled_condition_inf": max_paper_condition,
            "max_transfer_basis_consistency_scaled": max(row["transfer_consistency_scaled"] for row in paper_mode_cases),
            "mode_results": paper_mode_cases,
        },
        "paper_source_depth_scaling": {
            "depths_m": list(scaling_depths),
            "max_relative_error": max(row["relative_scaling_error"] for row in scaling_cases),
            "mode_results": scaling_cases,
        },
        "homogeneous_projector_vs_independent_reference": {
            "reference": "homogeneous Neumann-sphere closed form; radial branch is Næss Eq. 19",
            "conductivities_sm": list(homogeneous_sigmas),
            "max_degree_projector": projector_max_degree,
            "case_count": len(projector_cases),
            "sensor_comparisons": sum(int(row["sensor_count"]) for row in projector_cases),
            "max_absolute_error_v": max(float(row["max_absolute_error_v"]) for row in projector_cases),
            "max_scaled_error": max(float(row["max_scaled_error"]) for row in projector_cases),
            "cases": projector_cases,
        },
        "symmetry_axis_convergence": {
            "source_radius_m": NAESS_2017_SOURCE_RADIUS_M,
            "orientation": "radial +z",
            "sensor": "+z scalp axis",
            "cases": convergence_cases,
        },
        "candidate_comparison_interface": "compare_surface_potentials(reference_v, candidate_v, scale_v=...) ; no engine import required",
        "input_contract": {
            "degree": "positive integer l>=1; bool and l=0 rejected",
            "radii": "four finite positive strictly increasing metre values; r4<=1 m",
            "conductivities": "four finite positive S/m values; no conversion/inference",
            "paper_source": "0<rz<r1 for Næss basis; central source uses l=1 limit in projector",
            "dipole_moment": "finite 3-vector in A*m",
            "sensors": "non-empty finite Nx3 metre coordinates on r4",
            "orientation": "dipole moment decomposed into radial and tangent-to-rz components; all share origin/axes",
            "series": f"finite truncation 1<=L<={MAX_HARMONIC_DEGREE}; last-term value is not a tail bound",
        },
        "limitations": [
            "The separate four-shell candidate is open in PR #418 at physics/eeg_forward/four_sphere.py; this oracle intentionally did not import, run, or validate that implementation, and Round 6/Gemini claims remain unverified.",
            "The oracle uses the paper equations and synthetic inputs only; it is not empirical or biological validation.",
            "No GPL-3.0 code, LFPy runtime, or third-party implementation was used.",
            "The NumPy path is optional and remains untested in this no-NumPy local environment; pure-Python checks are reported separately.",
            "The outer boundary is the paper's zero-normal-current condition; no independent FEM, MNE, or air-shell comparator was used.",
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
