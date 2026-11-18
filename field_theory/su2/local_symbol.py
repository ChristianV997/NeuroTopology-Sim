"""One-point, one-direction characteristic screen for the continuum SU(2) Skyrme model.

This is a diagnostic for a validated local 1-jet, not a solver certificate.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import sys
from typing import Literal

import numpy as np


_CONSTRAINT_TOLERANCE = 1.0e-10
_ROOT_SIGN_TOLERANCE = 256.0 * sys.float_info.epsilon
_EIGENVECTOR_CONDITION_LIMIT = 1.0 / math.sqrt(sys.float_info.epsilon)
_MODEL = "local_skyrme_principal_symbol_v1"
_SCOPE = "continuum_local_tangent_symbol_one_point_one_direction_only"


@dataclass(frozen=True)
class LocalSkyrmePrincipalSymbolDiagnostic:
    """Directional characteristic roots for one continuum local field jet."""

    model: Literal["local_skyrme_principal_symbol_v1"]
    scope: Literal["continuum_local_tangent_symbol_one_point_one_direction_only"]
    status: Literal[
        "real_roots_at_sampled_direction",
        "nonreal_roots_detected",
        "numerically_unresolved",
    ]
    characteristic_speeds: tuple[complex, ...]
    normalized_spatial_covector: tuple[float, float, float]
    root_classification_tolerance: float
    eigenvector_condition_number: float | None
    eigenvector_condition_warning: bool
    eigenvector_condition_limit: float
    time_kinetic_min_eigenvalue: float
    time_kinetic_condition_number: float
    field_norm_residual: float
    max_derivative_tangency_residual: float
    general_system_hyperbolicity_status: Literal["not_certified"]


def _real_array(value: object, name: str, shape: tuple[int, ...]) -> np.ndarray:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real array with shape {shape}") from exc
    if array.shape != shape or array.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite real array with shape {shape}")
    try:
        result = np.array(array, dtype=np.float64, copy=True)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be representable as finite float64 values") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _positive_scalar(value: object, name: str) -> float:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive real scalar") from exc
    if array.ndim != 0 or array.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite positive real scalar")
    try:
        result = float(array)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive real scalar") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a finite positive real scalar")
    return result


def _stable_norm(vector: np.ndarray) -> float:
    return math.hypot(*(float(component) for component in vector))


def _stable_dot(left: np.ndarray, right: np.ndarray, name: str) -> float:
    try:
        result = math.fsum(
            float(left_component) * float(right_component)
            for left_component, right_component in zip(left, right)
        )
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} is outside the finite diagnostic range") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} is outside the finite diagnostic range")
    return result


def _tangent_basis(unit_field: np.ndarray) -> np.ndarray:
    """Return three deterministic orthonormal columns perpendicular to n."""
    sign = 1.0 if unit_field[0] >= 0.0 else -1.0
    reflector = unit_field.copy()
    reflector[0] += sign
    reflector_norm = _stable_norm(reflector)
    if not math.isfinite(reflector_norm) or reflector_norm == 0.0:
        raise ValueError("field does not define a numerically stable tangent basis")
    reflector /= reflector_norm
    householder = np.eye(4, dtype=np.float64) - 2.0 * np.outer(reflector, reflector)
    basis = householder[:, 1:]
    if not np.all(np.isfinite(basis)):
        raise ValueError("field does not define a finite tangent basis")
    return basis


def _wedge_metric(vector: np.ndarray, identity: np.ndarray) -> np.ndarray:
    """Matrix W(q) satisfying a.T W(q) a = |a wedge q|^2."""
    norm_squared = float(np.dot(vector, vector))
    if not math.isfinite(norm_squared):
        raise ValueError("local symbol is outside the finite diagnostic range")
    result = norm_squared * identity - np.outer(vector, vector)
    if not np.all(np.isfinite(result)):
        raise ValueError("local symbol is outside the finite diagnostic range")
    return result


def _sorted_roots(roots: np.ndarray) -> tuple[complex, ...]:
    result = tuple(complex(float(root.real), float(root.imag)) for root in roots)
    return tuple(sorted(result, key=lambda root: (root.real, root.imag)))


def analyze_local_skyrme_principal_symbol(
    field: object,
    velocity: object,
    spatial_gradients: object,
    spatial_covector: object,
    *,
    f_pi: object,
    e: object,
) -> LocalSkyrmePrincipalSymbolDiagnostic:
    """Analyze continuum characteristic speeds for one local tangent 1-jet.

    Inputs use the repository's dimensionless field normalization:
    field has shape (4,); velocity has shape (4,); spatial_gradients has shape
    (3, 4) with rows x, y, z; and spatial_covector has shape (3,). Derivative
    vectors must be tangent to S3 at field. Residuals within the stated
    relative tolerance are explicitly projected onto the tangent space before
    the symbol is formed; their maximum unprojected size is returned.

    For one nonzero spatial covector, the returned six roots are omega / norm(xi)
    of the projected 3-by-3 quadratic matrix pencil. A non-real root detects a
    failure of real characteristics at this sampled local state and direction.
    Real roots, even with a well-conditioned eigensolver result, do not certify
    strong hyperbolicity of the PDE.
    """
    n = _real_array(field, "field", (4,))
    v_ambient = _real_array(velocity, "velocity", (4,))
    g_ambient = _real_array(spatial_gradients, "spatial_gradients", (3, 4))
    covector = _real_array(spatial_covector, "spatial_covector", (3,))
    f_value = _positive_scalar(f_pi, "f_pi")
    e_value = _positive_scalar(e, "e")

    field_norm = _stable_norm(n)
    if (
        not math.isfinite(field_norm)
        or not math.isclose(field_norm, 1.0, rel_tol=0.0, abs_tol=_CONSTRAINT_TOLERANCE)
    ):
        raise ValueError("field must have unit norm on S3")
    unit_n = n / field_norm
    field_norm_residual = field_norm - 1.0

    covector_norm = _stable_norm(covector)
    if not math.isfinite(covector_norm):
        raise ValueError("spatial_covector must have a finite norm")
    if covector_norm == 0.0:
        raise ValueError("spatial_covector must be nonzero")
    direction = covector / covector_norm

    derivatives = [v_ambient, *g_ambient]
    tangent_derivatives: list[np.ndarray] = []
    maximum_tangent_residual = 0.0
    for derivative in derivatives:
        residual = _stable_dot(unit_n, derivative, "derivative tangency residual")
        derivative_norm = _stable_norm(derivative)
        tolerance = _CONSTRAINT_TOLERANCE * max(1.0, derivative_norm)
        if abs(residual) > tolerance:
            raise ValueError("velocity and spatial_gradients must be tangent to the field")
        maximum_tangent_residual = max(maximum_tangent_residual, abs(residual))
        # Remove accepted roundoff-scale normal components explicitly and report them.
        tangent_derivatives.append(derivative - residual * unit_n)

    basis = _tangent_basis(unit_n)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            v = basis.T @ tangent_derivatives[0]
            g = np.stack([basis.T @ item for item in tangent_derivatives[1:]])
            alpha = (f_value * f_value) / 4.0
            beta = 1.0 / (e_value * e_value)
    except FloatingPointError as exc:
        raise ValueError("couplings or derivative data exceed finite diagnostic range") from exc
    if (
        not np.all(np.isfinite(v))
        or not np.all(np.isfinite(g))
        or not math.isfinite(alpha)
        or alpha <= 0.0
        or not math.isfinite(beta)
        or beta <= 0.0
    ):
        raise ValueError("couplings or derivative data exceed finite diagnostic range")

    identity = np.eye(3, dtype=np.float64)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            time_block = alpha * identity
            for gradient in g:
                time_block += beta * _wedge_metric(gradient, identity)

            mixed_block = np.zeros((3, 3), dtype=np.float64)
            for axis, component in enumerate(direction):
                gradient = g[axis]
                gradient_velocity_dot = float(np.dot(gradient, v))
                mixed_form = (
                    np.outer(gradient, v)
                    + np.outer(v, gradient)
                    - 2.0 * gradient_velocity_dot * identity
                )
                mixed_block += beta * component * mixed_form

            spatial_block = -alpha * identity
            velocity_metric = _wedge_metric(v, identity)
            for axis, component in enumerate(direction):
                spatial_block += beta * component * component * velocity_metric
            for first in range(3):
                for second in range(first + 1, 3):
                    area_gradient = (
                        direction[first] * g[second] - direction[second] * g[first]
                    )
                    spatial_block -= beta * _wedge_metric(area_gradient, identity)
    except FloatingPointError as exc:
        raise ValueError("local symbol is outside the finite diagnostic range") from exc

    # These coefficients are symmetric analytically; remove only roundoff skew.
    time_block = 0.5 * (time_block + time_block.T)
    mixed_block = 0.5 * (mixed_block + mixed_block.T)
    spatial_block = 0.5 * (spatial_block + spatial_block.T)
    if not all(np.all(np.isfinite(matrix)) for matrix in (time_block, mixed_block, spatial_block)):
        raise ValueError("local symbol is outside the finite diagnostic range")

    try:
        time_eigenvalues = np.linalg.eigvalsh(time_block)
        time_condition = float(np.linalg.cond(time_block))
        cholesky = np.linalg.cholesky(time_block)
        inverse_cholesky = np.linalg.solve(cholesky, identity)
        normalized_mixed = inverse_cholesky @ mixed_block @ inverse_cholesky.T
        normalized_spatial = inverse_cholesky @ spatial_block @ inverse_cholesky.T
        companion = np.block(
            [
                [np.zeros((3, 3), dtype=np.float64), identity],
                [-normalized_spatial, normalized_mixed],
            ]
        )
        roots, eigenvectors = np.linalg.eig(companion)
        eigenvector_condition = float(np.linalg.cond(eigenvectors))
    except (np.linalg.LinAlgError, FloatingPointError, OverflowError) as exc:
        raise ValueError("local characteristic pencil is numerically unresolved") from exc

    if (
        not np.all(np.isfinite(time_eigenvalues))
        or not math.isfinite(time_condition)
        or not np.all(np.isfinite(normalized_mixed))
        or not np.all(np.isfinite(normalized_spatial))
        or not np.all(np.isfinite(roots))
    ):
        raise ValueError("local characteristic pencil is outside the finite diagnostic range")
    if time_eigenvalues[0] <= 0.0:
        raise ValueError("local time-kinetic block is not numerically positive definite")

    maximum_root_magnitude = max(
        (math.hypot(float(root.real), float(root.imag)) for root in roots),
        default=0.0,
    )
    root_tolerance = _ROOT_SIGN_TOLERANCE * max(1.0, maximum_root_magnitude)
    nonreal = any(abs(float(root.imag)) > root_tolerance for root in roots)
    condition_warning = (
        not math.isfinite(eigenvector_condition)
        or eigenvector_condition > _EIGENVECTOR_CONDITION_LIMIT
    )
    if nonreal:
        status = "nonreal_roots_detected"
    elif condition_warning:
        status = "numerically_unresolved"
    else:
        status = "real_roots_at_sampled_direction"

    finite_eigenvector_condition = (
        eigenvector_condition if math.isfinite(eigenvector_condition) else None
    )
    return LocalSkyrmePrincipalSymbolDiagnostic(
        model=_MODEL,
        scope=_SCOPE,
        status=status,
        characteristic_speeds=_sorted_roots(roots),
        normalized_spatial_covector=tuple(float(x) for x in direction),
        root_classification_tolerance=root_tolerance,
        eigenvector_condition_number=finite_eigenvector_condition,
        eigenvector_condition_warning=condition_warning,
        eigenvector_condition_limit=_EIGENVECTOR_CONDITION_LIMIT,
        time_kinetic_min_eigenvalue=float(time_eigenvalues[0]),
        time_kinetic_condition_number=time_condition,
        field_norm_residual=field_norm_residual,
        max_derivative_tangency_residual=maximum_tangent_residual,
        general_system_hyperbolicity_status="not_certified",
    )
