"""Multivariate IAAFT with honest pre-rank / post-rank cross-spectral reporting.

Null assumption
---------------
Iterative amplitude-adjusted Fourier transform (Schreiber & Schmitz style) with
**per-channel** rank (quantile) restoration. Auto-spectra are targeted each
iteration; the **full cross-spectral tensor is not guaranteed** after the final
rank step. The strict ``1e-3`` post-rank spectral gate is therefore often
``UNMET`` — this package reports that status explicitly and still returns the
rank-adjusted signal (never substitutes the pre-rank signal to hide the miss).

Procedure (default returns post-rank)
-------------------------------------
1. Start from a deterministic per-channel random permutation of the original.
2. Iterate up to ``max_iter``:
   a. **Spectrum step (pre-rank candidate):** replace each channel's ``rfft``
      magnitudes with the original target magnitudes; keep current phases.
   b. **Rank step (post-rank):** replace values by the original sorted sample
      values at the current ranks (exact marginal restoration).
3. After the final iteration, measure cross-spectral error on the spectrum-step
   array (pre-rank) and on the rank-adjusted array (post-rank).

Independent per-channel phase evolution is intentional: this is **not** MV-FPR
and must not be treated as interchangeable with shared-phase preservation.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

import numpy as np

from .errors import SurrogateAuditError
from .metrics import (
    SPECTRAL_GATE_1E3,
    marginal_sorted_error,
    relative_cross_spectral_error,
    validate_array,
)
from .status import AuditStatus


def generate_mv_iaaft(
    x: np.ndarray,
    *,
    seed: int = 0,
    max_iter: int = 50,
    spectral_gate: float = SPECTRAL_GATE_1E3,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Generate rank-adjusted MV-IAAFT and report pre/post-rank spectral errors.

    Returns the **post-rank** surrogate by default. If post-rank relative
    cross-spectral error exceeds ``spectral_gate``, ``spectral_gate_status`` is
    ``UNMET`` (still returning the rank-adjusted array).
    """
    if not isinstance(max_iter, int) or max_iter < 1:
        raise SurrogateAuditError("max_iter must be an integer >= 1")
    if not isinstance(spectral_gate, (int, float)) or not math.isfinite(spectral_gate) or spectral_gate <= 0:
        raise SurrogateAuditError("spectral_gate must be a finite positive number")

    arr = validate_array(x, min_channels=1, min_time=2)
    n_ch, n_t = arr.shape
    rng = np.random.default_rng(seed)

    target_amp = np.abs(np.fft.rfft(arr, axis=1))
    sorted_vals = np.sort(arr, axis=1)

    # Independent permutations per channel (deterministic under seed).
    s = np.empty_like(arr)
    for c in range(n_ch):
        s[c] = rng.permutation(arr[c])

    pre_rank = s.copy()
    post_rank = s.copy()
    prev_ranks = None

    for _ in range(max_iter):
        # (a) impose amplitude spectra, keep current phases
        S = np.fft.rfft(s, axis=1)
        phase = np.angle(S)
        # DC / Nyquist stay real via irfft of conjugate-symmetric construction.
        pre_rank = np.fft.irfft(target_amp * np.exp(1j * phase), n=n_t, axis=1)

        # (b) exact per-channel quantile / sorted-value restoration
        ranks = np.argsort(np.argsort(pre_rank, axis=1), axis=1)
        post_rank = np.take_along_axis(sorted_vals, ranks, axis=1)

        if prev_ranks is not None and np.array_equal(ranks, prev_ranks):
            s = post_rank
            break
        prev_ranks = ranks
        s = post_rank

    if not np.all(np.isfinite(pre_rank)) or not np.all(np.isfinite(post_rank)):
        raise SurrogateAuditError("MV-IAAFT produced non-finite values")

    pre_err = relative_cross_spectral_error(arr, pre_rank)
    post_err = relative_cross_spectral_error(arr, post_rank)
    marg_err = marginal_sorted_error(arr, post_rank)

    if post_err <= spectral_gate:
        gate_status = AuditStatus.MET.value
    else:
        gate_status = AuditStatus.UNMET.value

    meta = {
        "method": "mv_iaaft",
        "null_assumption": (
            "per_channel_iaaft_restores_amplitude_quantiles;"
            "cross_spectrum_not_guaranteed_after_rank_adjustment"
        ),
        "seed": int(seed),
        "max_iter": int(max_iter),
        "n_channels": int(n_ch),
        "n_time": int(n_t),
        "returned_signal": "post_rank",
        "pre_rank_cross_spectral_error": float(pre_err),
        "post_rank_cross_spectral_error": float(post_err),
        "marginal_sorted_error": float(marg_err),
        "spectral_gate": float(spectral_gate),
        "spectral_gate_status": gate_status,
        "strict_1e3_post_rank_gate_guaranteed": False,
        "interchangeable_with_mv_fpr": False,
        "round6_candidate_tested": False,
        "round6_note": (
            "Round 6 production candidate was not present on origin/main; "
            "this verifier implements the stated MV-IAAFT reporting contract "
            "separately and must not be read as a test of the missing candidate."
        ),
        "evidence_class": "SYNTHETIC_ONLY",
        "scientific_validated": False,
    }
    # Always return post-rank — never hide UNMET by swapping in pre-rank.
    return post_rank.astype(np.float64, copy=False), meta
