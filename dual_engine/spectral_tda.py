"""Spectral TDA: frequency-resolved persistence landscapes from EEG coherence.

Pragmatic implementation of the core idea in Ombao et al., "Spectral Topological
Data Analysis of Brain Signals" (arXiv:2401.05343): instead of collapsing a
recording to one distance matrix and then testing band-by-band by hand (what
every prior report in this project did), build a persistence landscape at each
frequency directly from the coherence matrix, giving a frequency-resolved
topological summary that can then be integrated within canonical bands.

Only the practically useful core is implemented (not the full functional-data
apparatus of the paper):
  coherence_spectrum          -> (n_ch, n_ch, n_freq) magnitude-squared coherence
  spectral_landscape          -> first persistence landscape per frequency
  spectral_landscape_band_summary -> per-band mean landscape "mass"

persim is not a repo dependency, so the (first) persistence landscape is
implemented directly: lambda_1(t) = max over (b,d) points of max(0, min(t-b, d-t)).
Homology is via ripser, matching the other pipelines in this repo.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-12
DEFAULT_BANDS = {"delta": (1., 4.), "theta": (4., 8.), "alpha": (8., 13.),
                 "beta": (13., 30.), "gamma": (30., 45.)}


def coherence_spectrum(
    timeseries: np.ndarray,
    sfreq: float,
    fmin: float = 1.0,
    fmax: float = 45.0,
    n_freq_bins: int | None = None,
    nperseg: int | None = None,
) -> dict:
    """Welch magnitude-squared coherence across channels vs frequency.

    Returns {"coherence": (n_ch, n_ch, n_freq), "freqs": (n_freq,)} over
    [fmin, fmax]. Coherence at frequency f is |S_ij(f)|^2 / (S_ii(f) S_jj(f)),
    where S is the averaged cross-spectral matrix over Hann-windowed, 50%-
    overlapping segments. Output is continuous-frequency-resolved (band binning
    is a downstream concern, done in spectral_landscape_band_summary).
    """
    ts = np.asarray(timeseries, dtype=float)
    if ts.ndim != 2:
        raise ValueError(f"timeseries must be 2D (n_channels, n_timepoints), got {ts.shape}")
    n_ch, n_t = ts.shape
    if n_ch < 2:
        raise ValueError(f"need at least 2 channels, got {n_ch}")
    if sfreq <= 0:
        raise ValueError(f"sfreq must be positive, got {sfreq}")
    if nperseg is None:
        nperseg = int(min(n_t, max(64, round(sfreq * 2))))  # ~2 s segments, >=64
    nperseg = min(nperseg, n_t)
    if nperseg < 16:
        raise ValueError(f"recording too short for coherence (nperseg={nperseg})")
    step = max(1, nperseg // 2)
    win = np.hanning(nperseg)
    starts = list(range(0, n_t - nperseg + 1, step))
    if len(starts) < 2:
        starts = [0]
    # segment FFTs: (n_seg, n_ch, n_freq)
    segs = np.stack([np.fft.rfft(ts[:, s:s + nperseg] * win[None, :], axis=1) for s in starts], axis=0)
    freqs = np.fft.rfftfreq(nperseg, d=1.0 / sfreq)
    band = (freqs >= fmin) & (freqs <= fmax)
    segs = segs[:, :, band]
    freqs = freqs[band]
    if freqs.size == 0:
        raise ValueError(f"no FFT bins in [{fmin}, {fmax}] Hz at sfreq={sfreq}")
    # cross-spectral matrix per frequency, averaged over segments (vectorized)
    # S[f] = mean_seg outer(X[:,f], conj(X[:,f]))
    # Vectorize using einsum: for each (ch_i, ch_j, freq), sum segments
    S = np.einsum('scf,sdf->cdf', segs, np.conj(segs)) / segs.shape[0]  # (n_ch, n_ch, n_freq)
    # Extract PSD (diagonal of S) for each frequency
    diag_idx = np.arange(n_ch)
    psd = np.real(S[diag_idx, diag_idx, :])  # (n_ch, n_freq)
    denom = psd[None, :, :] * psd[:, None, :]  # (n_ch, n_ch, n_freq) via broadcasting
    c = (np.abs(S) ** 2) / (denom + EPS)
    # Set diagonal to 1 (vectorized)
    c[diag_idx, diag_idx, :] = 1.0
    coh = np.clip(np.real(c), 0.0, 1.0)
    if n_freq_bins is not None and n_freq_bins < freqs.size:
        idx = np.linspace(0, freqs.size - 1, n_freq_bins).astype(int)
        coh = coh[:, :, idx]
        freqs = freqs[idx]
    if not np.all(np.isfinite(coh)):
        raise ValueError("coherence contains non-finite values")
    return {"coherence": coh, "freqs": freqs, "metric_kind": "coherence_spectrum"}


def _first_landscape(diagram: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """First persistence landscape lambda_1 sampled on grid, from an H1 diagram."""
    if diagram is None or diagram.size == 0:
        return np.zeros_like(grid)
    finite = diagram[np.isfinite(diagram).all(axis=1)]
    if finite.size == 0:
        return np.zeros_like(grid)
    b = finite[:, 0][:, None]
    d = finite[:, 1][:, None]
    tents = np.maximum(0.0, np.minimum(grid[None, :] - b, d - grid[None, :]))  # (m, G)
    return tents.max(axis=0)


def spectral_landscape(
    coherence_tensor: np.ndarray,
    freqs: np.ndarray,
    filtration_values: np.ndarray | None = None,
    max_freqs: int = 64,
) -> dict:
    """First persistence landscape at each frequency, from 1 - coherence distances.

    For each frequency, D = 1 - coherence(f) (a [0,1] distance matrix) is fed to
    ripser (H1), and the first persistence landscape is sampled on
    ``filtration_values`` (default: 100 points on [0, 1], the range of 1-coh).
    If there are more than ``max_freqs`` frequencies, an evenly-spaced subset is
    used (documented downsampling to keep per-recording cost bounded) and the
    frequencies actually used are returned.

    Returns {"landscape": (n_freqs_used, resolution), "freqs_used", "grid", ...}.
    """
    from ripser import ripser

    coh = np.asarray(coherence_tensor, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    if coh.ndim != 3 or coh.shape[0] != coh.shape[1]:
        raise ValueError(f"coherence_tensor must be (n_ch, n_ch, n_freq), got {coh.shape}")
    if coh.shape[2] != freqs.size:
        raise ValueError("freqs length must match coherence_tensor last axis")
    if filtration_values is None:
        filtration_values = np.linspace(0.0, 1.0, 100)
    grid = np.asarray(filtration_values, dtype=float)

    nf = freqs.size
    used_idx = (np.linspace(0, nf - 1, max_freqs).astype(int) if nf > max_freqs else np.arange(nf))
    used_idx = np.unique(used_idx)
    land = np.empty((used_idx.size, grid.size), dtype=float)
    for row, fi in enumerate(used_idx):
        D = 1.0 - coh[:, :, fi]
        np.fill_diagonal(D, 0.0)
        D = 0.5 * (D + D.T)
        D[D < 0] = 0.0
        dgm = ripser(D, distance_matrix=True, maxdim=1)["dgms"][1]
        land[row] = _first_landscape(dgm, grid)
    if not np.all(np.isfinite(land)):
        raise ValueError("spectral landscape contains non-finite values")
    return {"landscape": land, "freqs_used": freqs[used_idx], "grid": grid,
            "metric_kind": "spectral_landscape"}


def spectral_landscape_band_summary(
    spectral_landscape_result: dict,
    band_edges: dict | None = None,
) -> dict:
    """Per-band mean landscape "mass" (integral of the first landscape over the
    filtration), averaged across the frequencies falling in each band.

    "Mass" summarizes how much persistent topological structure exists in that
    band's coherence filtration -- directly comparable, band-for-band, to the
    scalar per-band metrics already computed for ds003969. Bands with no
    frequencies present are reported as None (not a fabricated 0).
    """
    if "landscape" not in spectral_landscape_result or "freqs_used" not in spectral_landscape_result:
        raise ValueError("spectral_landscape_result missing 'landscape'/'freqs_used'")
    land = np.asarray(spectral_landscape_result["landscape"], dtype=float)
    freqs = np.asarray(spectral_landscape_result["freqs_used"], dtype=float)
    grid = np.asarray(spectral_landscape_result["grid"], dtype=float)
    bands = band_edges or DEFAULT_BANDS

    # trapezoidal integral of each frequency's landscape over the filtration grid
    # (manual, to stay independent of np.trapz/np.trapezoid naming across versions)
    mass = np.sum(0.5 * (land[:, 1:] + land[:, :-1]) * np.diff(grid)[None, :], axis=1)
    out = {}
    for name, (lo, hi) in bands.items():
        sel = (freqs >= lo) & (freqs < hi)
        out[name] = float(np.mean(mass[sel])) if np.any(sel) else None
    for k, v in out.items():
        if v is not None and not np.isfinite(v):
            raise ValueError(f"non-finite band mass for {k}")
    return {"band_mass": out, "n_freqs_used": int(freqs.size),
            "metric_kind": "spectral_landscape_band_summary"}
