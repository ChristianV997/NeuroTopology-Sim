"""Surrogate-null contract and generators for synthetic multichannel signals.

HOLD / SYNTHETIC_ONLY. Stdlib only. No subprocess, network, or dataset access.
See ``docs/surrogate_nulls/null_contract.md`` for each null's assumptions.
"""
from .csd import (
    ESTIMATORS,
    diagnose_csd,
    estimate_csd,
    phase_loop_winding,
    winding_variation,
)
from .nulls import (
    AUTO_SPECTRUM_TOL,
    CONTRACTS,
    CROSS_SPECTRUM_STRICT_TOL,
    EXPLORATORY_NULL_IDS,
    GENERATORS,
    NULL_IDS,
    SurrogateReport,
    common_phase_prichard_theiler,
    cholesky_gaussian_cross_spectral,
    cholesky_gaussian_csd,
    draw_from_csd,
    independent_phase_univariate_ft,
    mv_iaaft_rank_adjusted,
    zero_lag_real_part_gaussian,
)
from .spectral import NonPositiveDefiniteError, SurrogateInputError

__all__ = [
    "AUTO_SPECTRUM_TOL",
    "CONTRACTS",
    "CROSS_SPECTRUM_STRICT_TOL",
    "ESTIMATORS",
    "EXPLORATORY_NULL_IDS",
    "GENERATORS",
    "NULL_IDS",
    "NonPositiveDefiniteError",
    "SurrogateInputError",
    "SurrogateReport",
    "cholesky_gaussian_cross_spectral",
    "cholesky_gaussian_csd",
    "common_phase_prichard_theiler",
    "diagnose_csd",
    "draw_from_csd",
    "estimate_csd",
    "independent_phase_univariate_ft",
    "mv_iaaft_rank_adjusted",
    "phase_loop_winding",
    "winding_variation",
    "zero_lag_real_part_gaussian",
]
