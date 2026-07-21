"""Analytic-phase utilities for EEG validation.

These helpers expose band-specific Hilbert analytic phase extraction and a few
proxy-metric helpers that the EEG pipeline uses. None of the metrics defined
here are validated consciousness biomarkers — they are exploratory analytic-phase
proxies used as scaffolding for null-controlled experiments.

Distinctions intended by this module:

* ``temporal_phase_proxy_metrics``      — legacy direct ``np.angle`` path; kept
  only as a documented proxy. Not a true neural phase field.
* ``channel_phase_gradient_metrics``    — gradient over channel order; treats
  channel index as a 1D coordinate. Not a spatial topology.
* ``phase_grid_topology_metrics``       — operates on a true 2D phase grid
  (e.g. interpolated montage). Uses the canonical ``core.topology`` primitives.

Bands follow common EEG conventions and exclude DC.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Tuple

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

from core.topology import (
    compute_Qabs_slice,
    compute_Q_slice,
    plaquette_charge,
)

DEFAULT_EEG_BANDS: Dict[str, Tuple[float, float]] = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma_low": (30.0, 45.0),
}

_NUMERICAL_STABILITY_EPSILON = 1e-12


def _validate_band(low_hz: float, high_hz: float, sfreq: float) -> None:
    if sfreq <= 0:
        raise ValueError(f"sfreq must be > 0, got {sfreq}")
    if low_hz <= 0:
        raise ValueError(f"low_hz must be > 0, got {low_hz}")
    if high_hz <= low_hz:
        raise ValueError(
            f"high_hz must be > low_hz, got low={low_hz}, high={high_hz}"
        )
    if high_hz >= sfreq / 2.0:
        raise ValueError(
            f"high_hz ({high_hz}) must be below Nyquist ({sfreq / 2.0})"
        )


def bandpass_hilbert_phase(
    data: np.ndarray,
    sfreq: float,
    low_hz: float,
    high_hz: float,
    order: int = 4,
) -> np.ndarray:
    """Bandpass-filter then Hilbert-transform to recover analytic phase.

    Parameters
    ----------
    data : ndarray, shape (n_channels, n_samples)
    sfreq : sampling frequency in Hz
    low_hz, high_hz : passband edges in Hz; must satisfy 0 < low < high < sfreq/2
    order : Butterworth order (per-side); used as ``order`` in ``butter(..., output="sos")``

    Returns
    -------
    phase : ndarray, shape (n_channels, n_samples), values in (-pi, pi]
    """
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"data must be 2D (channels x samples), got shape {arr.shape}")
    _validate_band(low_hz, high_hz, sfreq)

    nyq = sfreq / 2.0
    sos = butter(order, [low_hz / nyq, high_hz / nyq], btype="band", output="sos")
    filtered = sosfiltfilt(sos, arr, axis=-1)
    analytic = hilbert(filtered, axis=-1)
    return np.angle(analytic)


def analytic_phases_by_band(
    data: np.ndarray,
    sfreq: float,
    bands: Optional[Mapping[str, Tuple[float, float]]] = None,
) -> Dict[str, np.ndarray]:
    """Return a dict ``{band_name: phase_array}`` of analytic phases per band.

    Bands whose upper edge is at or above ``sfreq / 2`` are silently skipped so
    callers can supply a default band table on low-rate recordings.
    """
    bands = bands if bands is not None else DEFAULT_EEG_BANDS
    nyq = sfreq / 2.0
    out: Dict[str, np.ndarray] = {}
    for name, (lo, hi) in bands.items():
        if hi >= nyq:
            continue
        out[name] = bandpass_hilbert_phase(data, sfreq, lo, hi)
    return out




def analytic_phase_amplitude_by_band(
    data: np.ndarray,
    sfreq: float,
    bands: Optional[Mapping[str, Tuple[float, float]]] = None,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Return ``{band_name: (phase, amplitude)}`` from Hilbert analytic signal."""
    bands = bands if bands is not None else DEFAULT_EEG_BANDS
    nyq = sfreq / 2.0
    out: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"data must be 2D (channels x samples), got shape {arr.shape}")
    for name, (lo, hi) in bands.items():
        if hi >= nyq:
            continue
        _validate_band(lo, hi, sfreq)
        sos = butter(4, [lo / nyq, hi / nyq], btype="band", output="sos")
        filtered = sosfiltfilt(sos, arr, axis=-1)
        analytic = hilbert(filtered, axis=-1)
        out[name] = (np.angle(analytic), np.abs(analytic))
    return out
def temporal_phase_proxy_metrics(data: np.ndarray) -> Dict[str, float]:
    """Legacy direct ``np.angle`` proxy.

    Treats raw real-valued samples as if they carried analytic phase; this is
    not a valid neural phase field and is retained only as an exploratory
    proxy for backward comparison.
    """
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"data must be 2D, got shape {arr.shape}")
    phi = np.unwrap(np.angle(arr), axis=1)
    grad = np.diff(phi, axis=1)
    Q = float(np.sum(grad) / (2.0 * np.pi))
    Qabs = float(np.sum(np.abs(grad)) / (2.0 * np.pi))
    phase_grad = float(np.mean(np.abs(grad)))
    f_dress = float(
        (Qabs - abs(Q)) / (abs(Q) + _NUMERICAL_STABILITY_EPSILON)
    )
    return {
        "Q": Q,
        "Qabs": Qabs,
        "phase_grad": phase_grad,
        "f_dress": f_dress,
        "metric_kind": "temporal_phase_proxy",
    }


def channel_phase_gradient_metrics(phase: np.ndarray) -> Dict[str, float]:
    """Phase gradient along the channel-index axis.

    Treats channel index as a 1D ordering. This is a proxy, not a spatial
    topology — channel order does not encode geometry. Useful only as a coarse
    inter-channel coherence summary on a single band.
    """
    arr = np.asarray(phase, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"phase must be 2D (channels x samples), got {arr.shape}")

    from core.topology import wrap_phase

    # Wrapped differences across channels at each time sample
    chan_diff = wrap_phase(arr[1:, :] - arr[:-1, :])
    # Mean absolute gradient across channels and time
    phase_grad = float(np.mean(np.abs(chan_diff)))

    # Time-averaged channel diff to get a smooth Q-like signed/unsigned summary
    mean_chan_diff = chan_diff.mean(axis=1)
    Q = float(np.sum(mean_chan_diff) / (2.0 * np.pi))
    Qabs = float(np.sum(np.abs(mean_chan_diff)) / (2.0 * np.pi))
    f_dress = float(
        (Qabs - abs(Q)) / (abs(Q) + _NUMERICAL_STABILITY_EPSILON)
    )
    return {
        "Q": Q,
        "Qabs": Qabs,
        "phase_grad": phase_grad,
        "f_dress": f_dress,
        "metric_kind": "analytic_phase_proxy",
    }


def kuramoto_order_metrics(phase: np.ndarray) -> Dict[str, float]:
    """Kuramoto order parameter R(t) = |mean_channels exp(i*theta(t))| and
    metastability = std_t(R(t)) on a band's analytic phase.

    Published comparator (Deco/Kringelbach/Cabral whole-brain literature;
    fabridamicelli/kuramoto formalizes the same order parameter): the tightest
    *scalar* analogue of this module's own `f_dress` -- both are order/disorder
    summaries of the identical instantaneous phase field, so a real topological
    effect should, at minimum, not contradict what this standard synchrony
    scalar reports on the same window. R in [0, 1]: 0 = fully incoherent
    (random phases), 1 = fully phase-locked. High metastability means R(t)
    itself fluctuates over the window (repeated synchronize/desynchronize),
    not that any single instant is partially synchronized.
    """
    arr = np.asarray(phase, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"phase must be 2D (channels x samples), got {arr.shape}")
    if arr.shape[0] < 2:
        raise ValueError(f"need at least 2 channels, got {arr.shape[0]}")
    R = np.abs(np.mean(np.exp(1j * arr), axis=0))  # (n_samples,)
    r_mean = float(np.mean(R))
    metastability = float(np.std(R))
    if not (np.isfinite(r_mean) and np.isfinite(metastability)):
        raise ValueError("Non-finite Kuramoto order-parameter metrics")
    return {
        "R_mean": r_mean,
        "metastability": metastability,
        "metric_kind": "kuramoto_metastability",
    }


def leida_state_metrics(phase: np.ndarray, n_states: int = 3, random_state: int = 0) -> Dict[str, object]:
    """Leading Eigenvector Dynamics Analysis (Cabral et al. 2017) within one
    window: reduces the instantaneous phase-coherence matrix
    cos(theta_i(t) - theta_j(t)) to its leading eigenvector V1(t) -- a signed
    +/-1-ish partition of channels, directly analogous in kind (though not in
    construction) to this module's own signed winding charge -- then
    k-means-clusters {V1(t)} into ``n_states`` recurrent phase-locking states
    and reports fractional occupancy and the transition count.

    Scope, stated plainly: this is a PER-WINDOW LEiDA (states are discovered
    fresh within each call's samples), not a whole-recording state atlas shared
    across windows/subjects -- the published method typically clusters
    eigenvectors pooled across an entire cohort. That full-cohort version is a
    larger restructuring (state labels would need to be fit once and reused);
    this per-window form is still a valid, self-contained comparator for the
    intended use here -- testing whether Qz sign-flips / f_dress excursions
    coincide with LEiDA-state transitions on the SAME window.
    """
    from sklearn.cluster import KMeans

    arr = np.asarray(phase, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"phase must be 2D (channels x samples), got {arr.shape}")
    n_ch, n_t = arr.shape
    if n_ch < 3:
        raise ValueError(f"need at least 3 channels, got {n_ch}")
    if n_t < n_states * 2:
        raise ValueError(f"need at least {n_states * 2} samples for {n_states} states, got {n_t}")

    # Instantaneous phase-coherence matrix per sample, leading eigenvector only.
    # cos(theta_i - theta_j) = cos(theta_i)cos(theta_j) + sin(theta_i)sin(theta_j),
    # vectorized: cos_t, sin_t are (n_ch, n_t), outer products computed per timepoint
    cos_t, sin_t = np.cos(arr), np.sin(arr)
    V1 = np.empty((n_t, n_ch), dtype=float)

    for t in range(n_t):
        c, s = cos_t[:, t], sin_t[:, t]
        # Vectorized outer product: einsum is faster than nested outer() calls
        coh = np.einsum('i,j->ij', c, c) + np.einsum('i,j->ij', s, s)
        eigvals, eigvecs = np.linalg.eigh(coh)
        v = eigvecs[:, -1]  # largest eigenvalue's eigenvector
        if np.sum(v < 0) < np.sum(v > 0):  # LEiDA sign convention: majority negative
            v = -v
        V1[t] = v

    labels = KMeans(n_clusters=n_states, n_init=10, random_state=random_state).fit_predict(V1)
    occupancy = {int(k): float(np.mean(labels == k)) for k in range(n_states)}
    n_transitions = int(np.sum(labels[1:] != labels[:-1]))
    dominant_state = int(max(occupancy, key=occupancy.get))

    if not all(np.isfinite(v) for v in occupancy.values()):
        raise ValueError("Non-finite LEiDA occupancy metrics")

    return {
        "occupancy": occupancy,
        "dominant_state": dominant_state,
        "dominant_occupancy": occupancy[dominant_state],
        "n_transitions": n_transitions,
        "n_states": n_states,
        "metric_kind": "leida_state",
    }


def phase_grid_topology_metrics(theta2d: np.ndarray) -> Dict[str, float]:
    """Compute Q / Qabs / f_dress on a true 2D phase grid.

    The caller is responsible for producing ``theta2d`` from a montage-aware
    interpolation; this function does not infer geometry from EEG channel
    order.
    """
    arr = np.asarray(theta2d, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"theta2d must be 2D, got shape {arr.shape}")
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        raise ValueError(
            f"theta2d must have at least 2x2 plaquettes, got {arr.shape}"
        )
    Q = float(compute_Q_slice(arr))
    Qabs = float(compute_Qabs_slice(arr))
    plaq = plaquette_charge(arr)
    phase_grad = float(np.mean(np.abs(plaq)))
    f_dress = float((Qabs - abs(Q)) / (abs(Q) + _NUMERICAL_STABILITY_EPSILON))
    return {
        "Q": Q,
        "Qabs": Qabs,
        "phase_grad": phase_grad,
        "f_dress": f_dress,
        "metric_kind": "phase_grid_topology",
    }
