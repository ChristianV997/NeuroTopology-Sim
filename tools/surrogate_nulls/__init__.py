"""Surrogate-null contract and generators for synthetic multichannel signals.

HOLD / SYNTHETIC_ONLY. Stdlib only. No subprocess, network, or dataset access.
See ``docs/surrogate_nulls/null_contract.md`` for each null's assumptions.
"""
from .nulls import (
    AUTO_SPECTRUM_TOL,
    CONTRACTS,
    CROSS_SPECTRUM_STRICT_TOL,
    GENERATORS,
    NULL_IDS,
    SurrogateReport,
    common_phase_prichard_theiler,
    cholesky_gaussian_cross_spectral,
    draw_from_csd,
    independent_phase_univariate_ft,
    mv_iaaft_rank_adjusted,
)
from .spectral import NonPositiveDefiniteError, SurrogateInputError

__all__ = [
    "AUTO_SPECTRUM_TOL",
    "CONTRACTS",
    "CROSS_SPECTRUM_STRICT_TOL",
    "GENERATORS",
    "NULL_IDS",
    "NonPositiveDefiniteError",
    "SurrogateInputError",
    "SurrogateReport",
    "cholesky_gaussian_cross_spectral",
    "common_phase_prichard_theiler",
    "draw_from_csd",
    "independent_phase_univariate_ft",
    "mv_iaaft_rank_adjusted",
]
