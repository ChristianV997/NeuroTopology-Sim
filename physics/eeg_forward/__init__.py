"""Experimental four-shell EEG forward model (HOLD / SYNTHETIC_ONLY).

Public names live in ``four_sphere``. Importing this package runs no computation
and loads only NumPy. See ``docs/physics/four_sphere_forward_model.md`` for the
equations, conventions, attribution, and limitations.
"""
from .four_sphere import (
    DEFAULT_MAX_DEGREE,
    DEFAULT_RESIDUAL_TOL,
    DEFAULT_TAIL_TOL,
    FourSphereError,
    FourSphereGeometry,
    FourSphereInputError,
    FourSphereQualityError,
    FourSphereResult,
    forward_potentials,
    transfer_ratios,
)

__all__ = [
    "DEFAULT_MAX_DEGREE",
    "DEFAULT_RESIDUAL_TOL",
    "DEFAULT_TAIL_TOL",
    "FourSphereError",
    "FourSphereGeometry",
    "FourSphereInputError",
    "FourSphereQualityError",
    "FourSphereResult",
    "forward_potentials",
    "transfer_ratios",
]
