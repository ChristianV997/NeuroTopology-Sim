"""Multivariate Fourier phase randomization with a shared phase per frequency.

Null assumption
---------------
At each randomized frequency bin, multiply **every channel** by the same complex
phase factor ``exp(i φ_f)``. Relative inter-channel phases are unchanged, so the
full complex cross-spectral tensor is preserved algebraically (up to FFT
round-off). Per-channel amplitude *quantiles* are **not** restored.

This is a different null from independent per-channel phase randomization
(``validation.surrogate_testing`` default), which destroys cross-channel phase
structure.

Bins
----
* Bin 0 (DC) is never randomized (must remain real).
* For even ``n_time``, the Nyquist bin is never randomized (must remain real).
* All other positive-frequency ``rfft`` bins receive one shared ``φ_f``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from .errors import SurrogateAuditError
from .metrics import validate_array


def randomized_frequency_bins(n_time: int) -> List[int]:
    """Return ``rfft`` bin indices that receive a shared random phase."""
    if n_time < 2:
        raise SurrogateAuditError("n_time must be >= 2")
    n_freq = n_time // 2 + 1
    # Exclude DC (0). Exclude Nyquist (last bin) when n_time is even.
    hi = n_freq - 1 if (n_time % 2 == 0) else n_freq
    return list(range(1, hi))


def generate_mv_fpr(
    x: np.ndarray,
    *,
    seed: int = 0,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Generate one shared-phase MV-FPR surrogate.

    Parameters
    ----------
    x :
        Array shaped ``(n_channels, n_time)``.
    seed :
        Deterministic ``numpy.random.Generator`` seed.

    Returns
    -------
    surrogate : ndarray
        Same shape as ``x``.
    meta : dict
        Includes randomized bin indices and null-assumption label.
    """
    arr = validate_array(x, min_channels=1, min_time=2)
    n_ch, n_t = arr.shape
    rng = np.random.default_rng(seed)

    F = np.fft.rfft(arr, axis=1)
    bins = randomized_frequency_bins(n_t)
    n_freq = F.shape[1]

    # Shared multiplicative phase per randomized frequency only.
    # DC and Nyquist bins are left byte-for-byte unchanged so their real
    # coefficients (including negative DC/Nyquist) are preserved exactly.
    Fs = F.copy()
    if bins:
        shared = rng.uniform(0.0, 2.0 * np.pi, size=len(bins))
        idx = np.asarray(bins, dtype=int)
        Fs[:, idx] = Fs[:, idx] * np.exp(1j * shared)[None, :]

    # Zero-power / constant channels: non-DC bins are ~0; untouched DC remains.
    out = np.fft.irfft(Fs, n=n_t, axis=1)
    if not np.all(np.isfinite(out)):
        raise SurrogateAuditError("MV-FPR produced non-finite values")

    meta = {
        "method": "mv_fpr",
        "null_assumption": (
            "shared_phase_multiplier_preserves_cross_spectrum;"
            "does_not_restore_amplitude_quantiles"
        ),
        "seed": int(seed),
        "n_channels": int(n_ch),
        "n_time": int(n_t),
        "n_freq": int(n_freq),
        "randomized_bins": bins,
        "fixed_real_bins": [0] + ([n_freq - 1] if n_t % 2 == 0 else []),
        "interchangeable_with_mv_iaaft": False,
        "round6_candidate_tested": False,
        "round6_note": (
            "Round 6 production candidate was not present on origin/main; "
            "this is a separate audit implementation of the stated MV-FPR contract."
        ),
    }
    return out.astype(np.float64, copy=False), meta
