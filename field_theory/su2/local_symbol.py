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
_ILL_CONDITIONED_ROOT_RELATIVE_TOLERANCE = 16.0 * math.sqrt(sys.float_info.epsilon)
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


def _contains_boolean(value: object) -> bool:
    """Reject boolean elements before NumPy can coerce mixed sequences to numbers."""
    if isinstance(value, (bool, np.bool_)):
        return True
    if isinstance(value, np.ndarray):
        if value.dtype.kind == "b":
            return True
        if value.dtype.kind == "O":
            return any(_contains_boolean(item) for item in value.flat)
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_boolean(item) for item in value)
    return False


def _real_array(value: object, name: str, shape: tuple[int, ...]) -> np.ndarray:
    if _contains_boolean(value):
        raise ValueError(f"{name} must be a finite real array with shape {shape}, not booleans")
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


def _scaled_product_over_square(
    left: float,
    right: float,
    denominator: float,
    *,
    extra_factors: tuple[float, ...] = (),
    name: str,
) -> float:
    """Evaluate left*right*prod(extra_factors)/denominator**2 by binary scaling."""
    factors = (left, right, *extra_factors)
    if any(not math.isfinite(factor) or factor < 0.0 for factor in factors):
        raise ValueError(f"{name} is outside the finite diagnostic range")
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError(f"{name} is outside the finite diagnostic range")
    if any(factor == 0.0 for factor in factors):
        return 0.0

    mantissa = 1.0
    exponent = 0
    for factor in factors:
        factor_mantissa, factor_exponent = math.frexp(factor)
        mantissa *= factor_mantissa
        exponent += factor_exponent
    denominator_mantissa, denominator_exponent = math.frexp(denominator)
    mantissa /= denominator_mantissa * denominator_mantissa
    exponent -= 2 * denominator_exponent
    try:
        result = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError(f"{name} exceeds the finite diagnostic range") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} exceeds the finite diagnostic range")
    if result == 0.0:
        raise ValueError(f"{name} underflows the finite diagnostic range")
    return result


def _weighted_signed_product(
    left: float,
    right: float,
    denominator: float,
    *,
    extra_factors: tuple[float, ...],
    coefficient_sign: float,
    name: str,
) -> float:
    """Return a signed scaled product without raw products or cancellation."""
    if left == 0.0 or right == 0.0 or any(factor == 0.0 for factor in extra_factors):
        return 0.0
    magnitude = _scaled_product_over_square(
        abs(left),
        abs(right),
        denominator,
        extra_factors=extra_factors,
        name=name,
    )
    sign = math.copysign(1.0, left) * math.copysign(1.0, right)
    sign *= math.copysign(1.0, coefficient_sign)
    return math.copysign(magnitude, sign)


def _finite_sum(terms: list[float], name: str) -> float:
    try:
        result = math.fsum(terms)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} is outside the finite diagnostic range") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} is outside the finite diagnostic range")
    return result


def _weighted_wedge_metric(
    vector: np.ndarray,
    denominator: float,
    identity: np.ndarray,
    *,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Return W(vector)*amplitude**2/denominator**2 entrywise and robustly."""
    if amplitude == 0.0 or not np.any(vector):
        return np.zeros_like(identity)

    result = np.zeros_like(identity)
    for row in range(3):
        diagonal_terms = [
            _weighted_signed_product(
                float(vector[column]),
                float(vector[column]),
                denominator,
                extra_factors=(amplitude, amplitude),
                coefficient_sign=1.0,
                name="weighted wedge diagonal",
            )
            for column in range(3)
            if column != row
        ]
        result[row, row] = _finite_sum(diagonal_terms, "weighted wedge diagonal")
        for column in range(row + 1, 3):
            result[row, column] = _weighted_signed_product(
                float(vector[row]),
                float(vector[column]),
                denominator,
                extra_factors=(amplitude, amplitude),
                coefficient_sign=-1.0,
                name="weighted wedge off-diagonal",
            ) * math.copysign(1.0, float(vector[row])) * math.copysign(
                1.0, float(vector[column])
            )
            result[column, row] = result[row, column]
    if not np.all(np.isfinite(result)):
        raise ValueError("local symbol is outside the finite diagnostic range")
    return result


def _weighted_mixed_form(
    left: np.ndarray,
    right: np.ndarray,
    denominator: float,
    direction_component: float,
    identity: np.ndarray,
) -> np.ndarray:
    """Return direction_component*K(left,right)/denominator**2 entrywise."""
    if direction_component == 0.0 or not np.any(left) or not np.any(right):
        return np.zeros_like(identity)

    direction_sign = math.copysign(1.0, direction_component)
    direction_magnitude = abs(direction_component)
    result = np.zeros_like(identity)
    for row in range(3):
        diagonal_terms = [
            _weighted_signed_product(
                float(left[column]),
                float(right[column]),
                denominator,
                extra_factors=(direction_magnitude, 2.0),
                coefficient_sign=-direction_sign,
                name="weighted mixed diagonal",
            )
            for column in range(3)
            if column != row
        ]
        result[row, row] = _finite_sum(diagonal_terms, "weighted mixed diagonal")
        for column in range(row + 1, 3):
            term_ab = _weighted_signed_product(
                float(left[row]),
                float(right[column]),
                denominator,
                extra_factors=(direction_magnitude,),
                coefficient_sign=direction_sign,
                name="weighted mixed off-diagonal",
            )
            term_ba = _weighted_signed_product(
                float(right[row]),
                float(left[column]),
                denominator,
                extra_factors=(direction_magnitude,),
                coefficient_sign=direction_sign,
                name="weighted mixed off-diagonal",
            )
            result[row, column] = _finite_sum(
                [term_ab, term_ba], "weighted mixed off-diagonal"
            )
            result[column, row] = result[row, column]
    if not np.all(np.isfinite(result)):
        raise ValueError("local symbol is outside the finite diagnostic range")
    return result


def _sorted_roots(roots: np.ndarray) -> tuple[complex, ...]:
    result = tuple(complex(float(root.real), float(root.imag)) for root in roots)
    return tuple(sorted(result, key=lambda root: (root.real, root.imag)))


def _classify_characteristic_roots(
    roots: np.ndarray,
    *,
    condition_warning: bool,
) -> tuple[Literal[
    "real_roots_at_sampled_direction",
    "nonreal_roots_detected",
    "numerically_unresolved",
], float]:
    """Classify roots with per-root scales and a guard near ill-conditioned roots."""
    root_tolerances = [
        _ROOT_SIGN_TOLERANCE
        * max(1.0, math.hypot(float(root.real), float(root.imag)))
        for root in roots
    ]
    reported_tolerance = max(root_tolerances, default=_ROOT_SIGN_TOLERANCE)
    robust_nonreal = False
    ambiguous_nonreal = False
    for root, root_tolerance in zip(roots, root_tolerances):
        imaginary = abs(float(root.imag))
        if imaginary <= root_tolerance:
            continue
        magnitude = math.hypot(float(root.real), float(root.imag))
        sensitivity_tolerance = (
            _ILL_CONDITIONED_ROOT_RELATIVE_TOLERANCE * max(1.0, magnitude)
        )
        if condition_warning and imaginary <= sensitivity_tolerance:
            ambiguous_nonreal = True
        else:
            robust_nonreal = True

    if robust_nonreal:
        status = "nonreal_roots_detected"
    elif ambiguous_nonreal or condition_warning:
        status = "numerically_unresolved"
    else:
        status = "real_roots_at_sampled_direction"
    return status, reported_tolerance


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
        if not math.isfinite(derivative_norm):
            raise ValueError("derivative must have a finite norm")
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
        alpha = (0.5 * f_value) ** 2
    except (FloatingPointError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError("couplings or derivative data exceed finite diagnostic range") from exc
    if (
        not np.all(np.isfinite(v))
        or not np.all(np.isfinite(g))
        or not math.isfinite(alpha)
        or alpha <= 0.0
        or e_value <= 0.0
    ):
        raise ValueError("couplings or derivative data exceed finite diagnostic range")

    identity = np.eye(3, dtype=np.float64)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            time_block = alpha * identity
            for gradient in g:
                time_block += _weighted_wedge_metric(gradient, e_value, identity)

            mixed_block = np.zeros((3, 3), dtype=np.float64)
            for axis, component in enumerate(direction):
                mixed_block += _weighted_mixed_form(
                    g[axis], v, e_value, float(component), identity
                )

            spatial_block = -alpha * identity
            for component in direction:
                spatial_block += _weighted_wedge_metric(
                    v, e_value, identity, amplitude=abs(float(component))
                )
            for first in range(3):
                for second in range(first + 1, 3):
                    area_gradient = (
                        direction[first] * g[second] - direction[second] * g[first]
                    )
                    spatial_block -= _weighted_wedge_metric(
                        area_gradient, e_value, identity
                    )
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

    condition_warning = (
        not math.isfinite(eigenvector_condition)
        or eigenvector_condition > _EIGENVECTOR_CONDITION_LIMIT
    )
    status, root_tolerance = _classify_characteristic_roots(
        roots, condition_warning=condition_warning
    )

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
