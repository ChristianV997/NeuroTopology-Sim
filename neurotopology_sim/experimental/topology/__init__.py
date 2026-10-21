"""Oriented-complex topology helpers (experimental, synthetic-only)."""

from .winding import (
    DEFAULT_TIE_TOL,
    SUPPORTED_WRAP_INTERVALS,
    TWO_PI,
    ChargeMomentResult,
    WindingError,
    WindingResult,
    branch_index_floor,
    charge_moments,
    origin_shifted_moment,
    phase_winding,
    signed_first_moment,
)

__all__ = [
    "TWO_PI",
    "SUPPORTED_WRAP_INTERVALS",
    "DEFAULT_TIE_TOL",
    "WindingError",
    "WindingResult",
    "ChargeMomentResult",
    "branch_index_floor",
    "phase_winding",
    "signed_first_moment",
    "origin_shifted_moment",
    "charge_moments",
]
