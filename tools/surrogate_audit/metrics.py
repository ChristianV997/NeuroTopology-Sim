"""Spectral and marginal error definitions for surrogate audit.

Cross-spectral error
--------------------
Let ``F`` be the real-FFT of an array shaped ``(n_channels, n_time)``.
The complex cross-spectral tensor is

    C[f, i, j] = F[i, f] * conj(F[j, f]) / n_time

for every frequency bin ``f``. The **relative cross-spectral error** between
original ``X`` and surrogate ``S`` is the Frobenius relative residual

    ||C_S - C_X||_F / ||C_X||_F

This uses the **full channel×channel complex matrix at every frequency**, not
per-channel auto-spectra alone. Auto-spectral error is reported separately
when useful, but never as a substitute for the multivariate gate.

Marginal (quantile) error
-------------------------
For each channel ``c``, compare ``sort(S[c])`` to ``sort(X[c])``. The channel
error is ``max_t |sort(S[c])_t - sort(X[c])_t|``; the reported scalar is the
max over channels. Exact rank restoration yields ~0 (numerical float noise).
"""
from __future__ import annotations

import numpy as np

from .errors import SurrogateAuditError

SPECTRAL_GATE_1E3 = 1e-3


def validate_array(x: np.ndarray, *, min_channels: int = 1, min_time: int = 2) -> np.ndarray:
    if np.iscomplexobj(x):
        raise SurrogateAuditError("complex input arrays are not supported; expected real-valued array")
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 2:
        raise SurrogateAuditError(f"expected 2-D (n_channels, n_time), got shape {arr.shape}")
    if arr.shape[0] < min_channels:
        raise SurrogateAuditError(f"need >= {min_channels} channels, got {arr.shape[0]}")
    if arr.shape[1] < min_time:
        raise SurrogateAuditError(f"need >= {min_time} time samples, got {arr.shape[1]}")
    if not np.all(np.isfinite(arr)):
        raise SurrogateAuditError("array contains non-finite values")
    return arr


def cross_spectral_tensor(x: np.ndarray) -> np.ndarray:
    """Return ``C`` with shape ``(n_freq, n_channels, n_channels)`` (complex128)."""
    arr = validate_array(x)
    n_ch, n_t = arr.shape
    F = np.fft.rfft(arr, axis=1)  # (n_ch, n_freq)
    # C[f] = outer(F[:,f], conj(F[:,f])) / n_t
    C = (F[:, None, :] * np.conj(F[None, :, :])) / float(n_t)
    # Currently (n_ch, n_ch, n_freq) — move freq to leading axis.
    return np.transpose(C, (2, 0, 1))


def relative_cross_spectral_error(original: np.ndarray, surrogate: np.ndarray) -> float:
    """Frobenius relative error of the full complex cross-spectral tensor.

    Strictly scale-invariant: relative error = ||C_surr - C_orig||_F / ||C_orig||_F.
    Normalizes Fourier coefficients by original peak spectral magnitude before forming
    cross-spectral products, completely preventing float underflow or overflow across
    the entire finite float64 dynamic range (e.g. 1e-250 to 1e250).
    """
    x0 = validate_array(original)
    x1 = validate_array(surrogate)
    if x0.shape != x1.shape:
        raise SurrogateAuditError("original/surrogate shapes disagree for spectral error")
    n_ch, n_t = x0.shape
    F0 = np.fft.rfft(x0, axis=1)
    F1 = np.fft.rfft(x1, axis=1)

    m0 = float(np.max(np.abs(F0)))
    if m0 == 0.0:
        m1 = float(np.max(np.abs(F1)))
        return 0.0 if m1 == 0.0 else float("inf")

    scaled_F0 = F0 / m0
    scaled_F1 = F1 / m0
    if not np.all(np.isfinite(scaled_F1)) or float(np.max(np.abs(scaled_F1))) > 1e150:
        return float("inf")

    scaled_C0 = (scaled_F0[:, None, :] * np.conj(scaled_F0[None, :, :])) / float(n_t)
    scaled_C1 = (scaled_F1[:, None, :] * np.conj(scaled_F1[None, :, :])) / float(n_t)

    diff = scaled_C1 - scaled_C0
    num = float(np.linalg.norm(diff))
    den = float(np.linalg.norm(scaled_C0))
    return num / den


def relative_autospectral_error(original: np.ndarray, surrogate: np.ndarray) -> float:
    """Relative error of per-channel auto-spectra only (not the multivariate gate).

    Strictly scale-invariant: relative error = ||A_surr - A_orig||_F / ||A_orig||_F.
    Normalizes Fourier coefficients by original peak spectral magnitude before squaring,
    completely preventing float underflow or overflow across the entire finite float64
    dynamic range (e.g. 1e-250 to 1e250).
    """
    x0 = validate_array(original)
    x1 = validate_array(surrogate)
    if x0.shape != x1.shape:
        raise SurrogateAuditError("original/surrogate shapes disagree for autospectral error")
    F0 = np.fft.rfft(x0, axis=1)
    F1 = np.fft.rfft(x1, axis=1)

    m0 = float(np.max(np.abs(F0)))
    if m0 == 0.0:
        m1 = float(np.max(np.abs(F1)))
        return 0.0 if m1 == 0.0 else float("inf")

    scaled_F0 = F0 / m0
    scaled_F1 = F1 / m0
    if not np.all(np.isfinite(scaled_F1)) or float(np.max(np.abs(scaled_F1))) > 1e150:
        return float("inf")

    scaled_a0 = np.abs(scaled_F0) ** 2
    scaled_a1 = np.abs(scaled_F1) ** 2
    diff = scaled_a1 - scaled_a0
    num = float(np.linalg.norm(diff))
    den = float(np.linalg.norm(scaled_a0))
    return num / den


def marginal_sorted_error(original: np.ndarray, surrogate: np.ndarray) -> float:
    """Max over channels of max abs difference between sorted values."""
    x = validate_array(original)
    s = validate_array(surrogate)
    if x.shape != s.shape:
        raise SurrogateAuditError("original/surrogate shapes disagree for marginal error")
    errs = [float(np.max(np.abs(np.sort(s[c]) - np.sort(x[c])))) for c in range(x.shape[0])]
    return float(max(errs)) if errs else 0.0
