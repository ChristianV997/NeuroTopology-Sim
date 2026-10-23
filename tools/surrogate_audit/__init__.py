"""Synthetic verification surface for multivariate surrogate nulls (HOLD / SYNTHETIC_ONLY).

This package is an **audit/verifier API**, not the Round 6 production candidate
(which was not present on ``origin/main`` at implementation time). It does not
modify ``validation/surrogate_testing.py`` and never emits scientific VALIDATED.

Nulls implemented here are intentionally **not interchangeable**:

* ``mv_fpr`` — shared Fourier phase multiplier per frequency (preserves the
  full complex cross-spectral matrix algebraically; does **not** restore
  per-channel amplitude quantiles).
* ``mv_iaaft`` — iterative amplitude-adjusted FT with per-channel rank
  restoration (exact marginals after rank step; post-rank cross-spectral
  error is reported honestly and may be ``UNMET`` vs the strict 1e-3 gate).
"""
from __future__ import annotations

from .errors import SurrogateAuditError
from .metrics import (
    SPECTRAL_GATE_1E3,
    cross_spectral_tensor,
    marginal_sorted_error,
    relative_cross_spectral_error,
)
from .mv_fpr import generate_mv_fpr, randomized_frequency_bins
from .mv_iaaft import generate_mv_iaaft
from .report import audit_surrogate, dumps_report
from .status import AuditStatus, EvidenceClass

__all__ = [
    "SPECTRAL_GATE_1E3",
    "AuditStatus",
    "EvidenceClass",
    "SurrogateAuditError",
    "audit_surrogate",
    "cross_spectral_tensor",
    "dumps_report",
    "generate_mv_fpr",
    "generate_mv_iaaft",
    "marginal_sorted_error",
    "randomized_frequency_bins",
    "relative_cross_spectral_error",
]
