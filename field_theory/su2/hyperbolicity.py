"""Narrow principal-symbol diagnostic for a homogeneous geodesic background.

This analytic special case is separate from the lattice trajectory solver.
It can detect loss of real transverse principal roots in the specified
background family; it does not assess the full nonlinear PDE.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import sys
from typing import Literal

import numpy as np


_CONSTRAINT_TOLERANCE = 1.0e-10
_FLOAT_SIGN_TOLERANCE = 64.0 * sys.float_info.epsilon


@dataclass(frozen=True)
class UniformGeodesicPrincipalSymbolDiagnostic:
    """Result limited to transverse modes of a homogeneous S3 geodesic."""

    model: Literal["uniform_geodesic_transverse_symbol_v1"]
    scope: Literal["homogeneous_geodesic_transverse_principal_symbol_only"]
    status: Literal[
        "real_for_uniform_geodesic_transverse_sector",
        "threshold_for_uniform_geodesic_transverse_sector",
        "nonreal_for_uniform_geodesic_transverse_sector",
    ]
    background_speed: float
    critical_speed: float
    normalized_time_gradient: float
    transverse_speed_squared: float
    classification_tolerance: float
    transverse_principal_roots_per_unit_wavenumber: tuple[complex, complex]
    local_time_kinetic_hessian_min_eigenvalue: float
    full_system_hyperbolicity_status: Literal["not_assessed"]


def _finite_real_vector4(value: object, name: str) -> np.ndarray:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real vector of length 4") from exc
    if array.shape != (4,) or array.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite real vector of length 4")
    vector = array.astype(float, copy=True)
    if not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain only finite values")
    return vector


def _finite_positive_real(value: object, name: str) -> float:
    try:
        scalar = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive real scalar") from exc
    if scalar.ndim != 0 or scalar.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a finite positive real scalar")
    try:
        number = float(scalar)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive real scalar") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a finite positive real scalar")
    return number


def analyze_uniform_geodesic_transverse_symbol(
    field: object,
    velocity: object,
    *,
    f_pi: object,
    e: object,
) -> UniformGeodesicPrincipalSymbolDiagnostic:
    """Analyze transverse principal roots for one exact homogeneous geodesic.

    ``field`` and ``velocity`` give an initial point and tangent vector in
    ``R^4``; the diagnostic assumes their exact homogeneous geodesic evolution
    on ``S^3``. Values and couplings are dimensionless, matching
    :mod:`field_theory.su2.lorentzian`.

    For background speed ``u = |velocity|``, the transverse principal symbol
    has ``omega**2 / |xi|**2 = 1 - 4*u**2/(e**2*f_pi**2)``. This result is
    specific to the homogeneous-geodesic transverse sector. In particular,
    it is not a hyperbolicity certificate for an arbitrary lattice field or
    for the full nonlinear Skyrme system.
    """
    n = _finite_real_vector4(field, "field")
    v = _finite_real_vector4(velocity, "velocity")
    f_pi_value = _finite_positive_real(f_pi, "f_pi")
    e_value = _finite_positive_real(e, "e")

    field_norm = math.hypot(*(float(component) for component in n))
    if not math.isfinite(field_norm) or not math.isclose(
        field_norm, 1.0, rel_tol=0.0, abs_tol=_CONSTRAINT_TOLERANCE
    ):
        raise ValueError("field must have unit norm on S3")

    speed = math.hypot(*(float(component) for component in v))
    if not math.isfinite(speed):
        raise ValueError("velocity must have a finite norm")
    try:
        tangent_residual = math.fsum(
            float(n_component) * float(v_component)
            for n_component, v_component in zip(n, v)
        )
    except OverflowError as exc:
        raise ValueError("velocity must be tangent to S3 at field") from exc
    tangent_tolerance = _CONSTRAINT_TOLERANCE * max(1.0, speed)
    if not math.isfinite(tangent_residual) or abs(tangent_residual) > tangent_tolerance:
        raise ValueError("velocity must be tangent to S3 at field")

    critical_speed = 0.5 * f_pi_value * e_value
    time_hessian_min = 0.25 * f_pi_value * f_pi_value
    if (
        not math.isfinite(critical_speed)
        or critical_speed <= 0.0
        or not math.isfinite(time_hessian_min)
        or time_hessian_min <= 0.0
    ):
        raise ValueError("f_pi and e must yield finite positive diagnostic scales")

    speed_ratio = speed / critical_speed
    ratio_squared = speed_ratio * speed_ratio
    if not math.isfinite(speed_ratio) or not math.isfinite(ratio_squared):
        raise ValueError("background speed and couplings exceed finite diagnostic range")

    transverse_speed_squared = 1.0 - ratio_squared
    if not math.isfinite(transverse_speed_squared):
        raise ValueError("principal-symbol result is outside finite diagnostic range")
    sign_tolerance = _FLOAT_SIGN_TOLERANCE * max(1.0, ratio_squared)

    if transverse_speed_squared > sign_tolerance:
        root = math.sqrt(transverse_speed_squared)
        status = "real_for_uniform_geodesic_transverse_sector"
        roots = (-complex(root, 0.0), complex(root, 0.0))
    elif transverse_speed_squared < -sign_tolerance:
        root = math.sqrt(-transverse_speed_squared)
        status = "nonreal_for_uniform_geodesic_transverse_sector"
        roots = (-complex(0.0, root), complex(0.0, root))
    else:
        status = "threshold_for_uniform_geodesic_transverse_sector"
        roots = (0j, 0j)

    return UniformGeodesicPrincipalSymbolDiagnostic(
        model="uniform_geodesic_transverse_symbol_v1",
        scope="homogeneous_geodesic_transverse_principal_symbol_only",
        status=status,
        background_speed=speed,
        critical_speed=critical_speed,
        normalized_time_gradient=speed_ratio,
        transverse_speed_squared=transverse_speed_squared,
        classification_tolerance=sign_tolerance,
        transverse_principal_roots_per_unit_wavenumber=roots,
        local_time_kinetic_hessian_min_eigenvalue=time_hessian_min,
        full_system_hyperbolicity_status="not_assessed",
    )

