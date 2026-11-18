"""One-point, one-direction characteristic screen for the continuum SU(2) Skyrme model.

This is a diagnostic for a validated local 1-jet, not a solver certificate.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
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
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            result = np.array(array, dtype=np.float64, copy=True)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be representable as finite float64 values") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain only finite values")
    if array.dtype.kind == "f":
        if np.any((array != 0) & (result == 0)):
            raise ValueError(
                f"{name} contains nonzero values that underflow when converted to float64"
            )
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            round_tripped = np.asarray(result, dtype=array.dtype)
        if np.any(round_tripped != array):
            raise ValueError(f"{name} contains values not exactly representable as float64")
    elif array.dtype.kind in "iu":
        if any(
            int(original) != int(converted)
            for original, converted in zip(array.flat, result.flat)
        ):
            raise ValueError(f"{name} contains values not exactly representable as float64")
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
    if array.dtype.kind == "f":
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            round_tripped = np.asarray(result, dtype=array.dtype).item()
        if round_tripped != array.item():
            raise ValueError(f"{name} must be exactly representable as float64")
    elif array.dtype.kind in "iu" and int(array.item()) != int(result):
        raise ValueError(f"{name} must be exactly representable as float64")
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


def _as_exact_fraction(value: float | Fraction, name: str) -> Fraction:
    """Interpret a float64 input as its exact binary rational value."""
    if isinstance(value, Fraction):
        return value
    try:
        scalar = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} is outside the finite diagnostic range") from exc
    if not math.isfinite(scalar):
        raise ValueError(f"{name} is outside the finite diagnostic range")
    return Fraction.from_float(scalar)


def _fraction_to_finite_float(value: Fraction, name: str) -> float:
    """Round an exact rational once to float64, rejecting overflow and underflow."""
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} exceeds the finite diagnostic range") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} exceeds the finite diagnostic range")
    if value and result == 0.0:
        raise ValueError(f"{name} underflows the finite diagnostic range")
    return result


def _product_fraction_over_denominator(
    left: float | Fraction,
    right: float | Fraction,
    denominator: float | Fraction,
    *,
    name: str,
) -> Fraction:
    """Return the exact rational left*right/denominator for float64 inputs."""
    left_fraction = _as_exact_fraction(left, name)
    right_fraction = _as_exact_fraction(right, name)
    denominator_fraction = _as_exact_fraction(denominator, name)
    if denominator_fraction <= 0:
        raise ValueError(f"{name} is outside the finite diagnostic range")
    return left_fraction * right_fraction / denominator_fraction


def _weighted_product_fraction(
    left: float | Fraction,
    right: float | Fraction,
    denominator: float | Fraction,
    *,
    extra_factors: tuple[float | Fraction, ...],
    coefficient_sign: float | Fraction,
    name: str,
) -> Fraction:
    """Return an exact weighted product before any float64 rounding."""
    left_fraction = _as_exact_fraction(left, name)
    right_fraction = _as_exact_fraction(right, name)
    denominator_fraction = _as_exact_fraction(denominator, name)
    coefficient_fraction = _as_exact_fraction(coefficient_sign, name)
    extra_fraction = [_as_exact_fraction(value, name) for value in extra_factors]
    if denominator_fraction <= 0 or any(value < 0 for value in extra_fraction):
        raise ValueError(f"{name} is outside the finite diagnostic range")

    product = left_fraction * right_fraction * coefficient_fraction
    for factor in extra_fraction:
        product *= factor
    return product / (denominator_fraction * denominator_fraction)


def _sum_fraction_terms(terms: list[Fraction], name: str) -> Fraction:
    try:
        return sum(terms, Fraction(0, 1))
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{name} is outside the finite diagnostic range") from exc


def _finite_exact_sum(terms: list[Fraction], name: str) -> float:
    """Accumulate exact products, then round the complete coefficient once."""
    return _fraction_to_finite_float(_sum_fraction_terms(terms, name), name)


def _zero_fraction_matrix() -> list[list[Fraction]]:
    return [[Fraction(0, 1) for _ in range(3)] for _ in range(3)]


def _scaled_identity_fraction(scale: Fraction) -> list[list[Fraction]]:
    result = _zero_fraction_matrix()
    for index in range(3):
        result[index][index] = scale
    return result


def _accumulate_fraction_matrix(
    target: list[list[Fraction]],
    source: list[list[Fraction]],
    *,
    coefficient: Fraction = Fraction(1, 1),
) -> None:
    """Accumulate a small matrix exactly before its eventual float conversion."""
    for row in range(3):
        for column in range(3):
            target[row][column] += coefficient * source[row][column]


def _fraction_matrix_to_float(
    matrix: list[list[Fraction]],
    name: str,
) -> np.ndarray:
    return np.array(
        [
            [_fraction_to_finite_float(value, name) for value in row]
            for row in matrix
        ],
        dtype=np.float64,
    )


def _weighted_wedge_fraction(
    vector: np.ndarray | list[float | Fraction],
    denominator: float | Fraction,
    *,
    amplitude: float | Fraction = 1.0,
) -> list[list[Fraction]]:
    """Return W(vector)*amplitude**2/denominator**2 exactly."""
    values = [_as_exact_fraction(value, "weighted wedge vector") for value in vector]
    if len(values) != 3:
        raise ValueError("weighted wedge vector must have length 3")
    denominator_fraction = _as_exact_fraction(denominator, "weighted wedge denominator")
    amplitude_fraction = _as_exact_fraction(amplitude, "weighted wedge amplitude")
    if denominator_fraction <= 0 or amplitude_fraction < 0:
        raise ValueError("weighted wedge scaling is outside the finite diagnostic range")
    result = _zero_fraction_matrix()
    if amplitude_fraction == 0 or not any(values):
        return result

    for row in range(3):
        diagonal_terms = [
            _weighted_product_fraction(
                values[column],
                values[column],
                denominator_fraction,
                extra_factors=(amplitude_fraction, amplitude_fraction),
                coefficient_sign=1.0,
                name="weighted wedge diagonal",
            )
            for column in range(3)
            if column != row
        ]
        result[row][row] = _sum_fraction_terms(
            diagonal_terms, "weighted wedge diagonal"
        )
        for column in range(row + 1, 3):
            result[row][column] = _weighted_product_fraction(
                values[row],
                values[column],
                denominator_fraction,
                extra_factors=(amplitude_fraction, amplitude_fraction),
                coefficient_sign=-1.0,
                name="weighted wedge off-diagonal",
            )
            result[column][row] = result[row][column]
    return result


def _weighted_mixed_fraction(
    left: np.ndarray,
    right: np.ndarray,
    denominator: float,
    direction_component: float,
) -> list[list[Fraction]]:
    """Return direction_component*K(left,right)/denominator**2 exactly."""
    left_values = [_as_exact_fraction(value, "weighted mixed left vector") for value in left]
    right_values = [_as_exact_fraction(value, "weighted mixed right vector") for value in right]
    if len(left_values) != 3 or len(right_values) != 3:
        raise ValueError("weighted mixed vectors must have length 3")
    denominator_fraction = _as_exact_fraction(denominator, "weighted mixed denominator")
    direction_fraction = _as_exact_fraction(
        direction_component, "weighted mixed direction"
    )
    if denominator_fraction <= 0:
        raise ValueError("weighted mixed denominator is outside the finite diagnostic range")
    result = _zero_fraction_matrix()
    if direction_fraction == 0 or not any(left_values) or not any(right_values):
        return result

    direction_sign = Fraction(1, 1) if direction_fraction > 0 else Fraction(-1, 1)
    direction_magnitude = abs(direction_fraction)
    for row in range(3):
        diagonal_terms = [
            _weighted_product_fraction(
                left_values[column],
                right_values[column],
                denominator_fraction,
                extra_factors=(direction_magnitude, Fraction(2, 1)),
                coefficient_sign=-direction_sign,
                name="weighted mixed diagonal",
            )
            for column in range(3)
            if column != row
        ]
        result[row][row] = _sum_fraction_terms(
            diagonal_terms, "weighted mixed diagonal"
        )
        for column in range(row + 1, 3):
            term_ab = _weighted_product_fraction(
                left_values[row],
                right_values[column],
                denominator_fraction,
                extra_factors=(direction_magnitude,),
                coefficient_sign=direction_sign,
                name="weighted mixed off-diagonal",
            )
            term_ba = _weighted_product_fraction(
                right_values[row],
                left_values[column],
                denominator_fraction,
                extra_factors=(direction_magnitude,),
                coefficient_sign=direction_sign,
                name="weighted mixed off-diagonal",
            )
            result[row][column] = _sum_fraction_terms(
                [term_ab, term_ba], "weighted mixed off-diagonal"
            )
            result[column][row] = result[row][column]
    return result


def _weighted_wedge_metric(
    vector: np.ndarray,
    denominator: float,
    identity: np.ndarray,
    *,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Return W(vector)*amplitude**2/denominator**2 entrywise and robustly."""
    return _fraction_matrix_to_float(
        _weighted_wedge_fraction(vector, denominator, amplitude=amplitude),
        "local symbol",
    )


def _weighted_mixed_form(
    left: np.ndarray,
    right: np.ndarray,
    denominator: float,
    direction_component: float,
    identity: np.ndarray,
) -> np.ndarray:
    """Return direction_component*K(left,right)/denominator**2 exactly."""
    return _fraction_matrix_to_float(
        _weighted_mixed_fraction(left, right, denominator, direction_component),
        "local symbol",
    )



def _assemble_local_symbol_blocks(
    velocity: np.ndarray,
    gradients: np.ndarray,
    direction: np.ndarray,
    coupling: float,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the complete A, D, C blocks exactly, rounding each block once."""
    alpha_fraction = _as_exact_fraction(alpha, "Skyrme quadratic coefficient")
    time_fraction = _scaled_identity_fraction(alpha_fraction)
    for gradient in gradients:
        _accumulate_fraction_matrix(
            time_fraction, _weighted_wedge_fraction(gradient, coupling)
        )

    mixed_fraction = _zero_fraction_matrix()
    for axis, component in enumerate(direction):
        _accumulate_fraction_matrix(
            mixed_fraction,
            _weighted_mixed_fraction(
                gradients[axis], velocity, coupling, float(component)
            ),
        )

    spatial_fraction = _scaled_identity_fraction(-alpha_fraction)
    for component in direction:
        _accumulate_fraction_matrix(
            spatial_fraction,
            _weighted_wedge_fraction(
                velocity, coupling, amplitude=abs(float(component))
            ),
        )
    for first in range(3):
        for second in range(first + 1, 3):
            # Form each area component/e exactly, then keep its W contribution
            # exact while assembling C(d). This avoids raw-product underflow
            # and cancellation both within and across coefficient matrices.
            area_gradient_over_coupling = [
                _product_fraction_over_denominator(
                    float(direction[first]),
                    float(gradients[second, component]),
                    coupling,
                    name="scaled area-gradient component",
                )
                - _product_fraction_over_denominator(
                    float(direction[second]),
                    float(gradients[first, component]),
                    coupling,
                    name="scaled area-gradient component",
                )
                for component in range(3)
            ]
            _accumulate_fraction_matrix(
                spatial_fraction,
                _weighted_wedge_fraction(area_gradient_over_coupling, 1.0),
                coefficient=Fraction(-1, 1),
            )

    return (
        _fraction_matrix_to_float(time_fraction, "time-kinetic block"),
        _fraction_matrix_to_float(mixed_fraction, "mixed block"),
        _fraction_matrix_to_float(spatial_fraction, "spatial block"),
    )


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
    time_block, mixed_block, spatial_block = _assemble_local_symbol_blocks(
        v, g, direction, e_value, alpha
    )

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
