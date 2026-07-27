"""Deterministic preprocessing and topology summaries for local recordings.

Arrays use shape ``(samples, channels)`` and amplitudes are dimensionless after
per-channel z-scoring.  Frequencies are in Hz and phases in radians.  This
module deliberately contains no dataset downloads or claims about biology.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

from .ingest_empirical import EmpiricalSignal, _normalize


BandName = Literal["gamma", "alpha", "mu"]


@dataclass(frozen=True)
class EmpiricalCondition:
    """One labelled condition with filtered signal and phase observables."""

    label: str
    signal: EmpiricalSignal
    coherence: np.ndarray
    winding: np.ndarray
    charge: np.ndarray
    beta_1: np.ndarray
    source_kind: str

    def summary(self) -> dict[str, float | int | str]:
        """Return finite scalar topology summaries for JSON serialization."""
        return {
            "label": self.label,
            "n_samples": int(self.signal.data.shape[0]),
            "n_channels": int(self.signal.data.shape[1]),
            "mean_winding": float(np.mean(self.winding)),
            "mean_q": float(np.mean(self.charge)),
            "mean_beta_1": float(np.mean(self.beta_1)),
            "source_kind": self.source_kind,
        }


def _band_edges(band: BandName | tuple[float, float]) -> tuple[float, float]:
    if isinstance(band, tuple):
        low, high = band
    elif band == "gamma":
        low, high = 30.0, 80.0
    elif band in {"alpha", "mu"}:
        low, high = 8.0, 13.0
    else:
        raise ValueError(f"unsupported band: {band}")
    if not (0.0 < low < high):
        raise ValueError("band edges must satisfy 0 < low < high")
    return float(low), float(high)


def bandpass_filter(data: np.ndarray, sample_rate_hz: float,
                    band: BandName | tuple[float, float] = "gamma",
                    order: int = 4) -> np.ndarray:
    """Apply a zero-phase Butterworth bandpass to ``(samples, channels)``."""
    values = np.asarray(data, dtype=float)
    if values.ndim != 2 or values.shape[0] < 16 or values.shape[1] < 1:
        raise ValueError("data must have shape (samples>=16, channels>=1)")
    if not np.all(np.isfinite(values)) or sample_rate_hz <= 0 or order < 1:
        raise ValueError("data must be finite; sample rate and order must be positive")
    low, high = _band_edges(band)
    nyquist = sample_rate_hz / 2.0
    if high >= nyquist:
        raise ValueError("upper band edge must be below Nyquist frequency")
    sos = butter(order, (low / nyquist, high / nyquist), btype="bandpass", output="sos")
    # sosfiltfilt needs enough edge samples for stable initial conditions.
    if values.shape[0] <= 3 * (2 * sos.shape[0] + 1):
        raise ValueError("recording is too short for the requested zero-phase filter")
    filtered = sosfiltfilt(sos, values, axis=0)
    if not np.all(np.isfinite(filtered)):
        raise FloatingPointError("bandpass filter produced non-finite values")
    return filtered


def analytic_phase(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return analytic signal and unwrapped phase in radians."""
    values = np.asarray(data, dtype=float)
    if values.ndim != 2 or values.shape[0] < 8 or not np.all(np.isfinite(values)):
        raise ValueError("data must be finite with shape (samples>=8, channels)")
    analytic = hilbert(values, axis=0)
    phase = np.unwrap(np.angle(analytic), axis=0)
    return analytic, phase


def phase_coherence_matrix(phase: np.ndarray) -> np.ndarray:
    """Compute instantaneous cross-channel phase coherence ``R(t,i,j)``."""
    values = np.asarray(phase, dtype=float)
    if values.ndim != 2 or not np.all(np.isfinite(values)):
        raise ValueError("phase must have shape (samples, channels) and be finite")
    differences = values[:, :, None] - values[:, None, :]
    coherence = np.cos(differences)
    return np.asarray((coherence + np.swapaxes(coherence, 1, 2)) * 0.5, dtype=float)


def topology_from_phase(phase: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract phase winding, scalar charge, and a conservative beta-1 proxy."""
    values = np.asarray(phase, dtype=float)
    if values.ndim != 2 or values.shape[1] < 3 or not np.all(np.isfinite(values)):
        raise ValueError("phase must have shape (samples, channels>=3)")
    wrapped = (values - values[:, :1] + np.pi) % (2.0 * np.pi) - np.pi
    winding = np.sum(np.diff(np.column_stack((wrapped, wrapped[:, :1])), axis=1), axis=1) / (2.0 * np.pi)
    triad = np.stack((np.cos(values[:, 0]), np.sin(values[:, 0]), np.cos(values[:, 1])), axis=1)
    triad_next = np.stack((np.cos(values[:, 1]), np.sin(values[:, 1]), np.cos(values[:, 2])), axis=1)
    triad_last = np.stack((np.cos(values[:, 2]), np.sin(values[:, 2]), np.cos(values[:, 0])), axis=1)
    charge = np.einsum("ij,ij->i", triad, np.cross(triad_next, triad_last)) / (4.0 * np.pi)
    gradients = np.abs(np.diff(wrapped, axis=1))
    beta_1 = np.sum(gradients > (0.75 * np.pi), axis=1).astype(int)
    return winding, charge, beta_1


def standardize_condition(data: np.ndarray, sample_rate_hz: float, label: str,
                          band: BandName | tuple[float, float] = "gamma",
                          source_kind: str = "empirical_csv") -> EmpiricalCondition:
    """Normalize, filter, and derive topology metrics for one condition."""
    normalized = _normalize(np.asarray(data, dtype=float))
    filtered = bandpass_filter(normalized, sample_rate_hz, band=band)
    analytic, phase = analytic_phase(filtered)
    signal = EmpiricalSignal(filtered, analytic, phase, float(sample_rate_hz), source_kind)
    winding, charge, beta_1 = topology_from_phase(phase)
    return EmpiricalCondition(label, signal, phase_coherence_matrix(phase), winding, charge, beta_1, source_kind)


def generate_mock_conditions(n_samples: int = 512, n_channels: int = 6,
                             sample_rate_hz: float = 250.0, seed: int = 0) -> dict[str, EmpiricalCondition]:
    """Generate deterministic awake/sedated fixtures for pipeline validation only."""
    if n_samples < 64 or n_channels < 3 or sample_rate_hz <= 160.0:
        raise ValueError("fixture requires samples>=64, channels>=3 and sample rate>160 Hz")
    rng = np.random.default_rng(seed)
    time = np.arange(n_samples, dtype=float) / sample_rate_hz
    carrier = 40.0
    awake = np.empty((n_samples, n_channels), dtype=float)
    sedated = np.empty_like(awake)
    for channel in range(n_channels):
        phase_offset = 2.0 * np.pi * channel / n_channels
        awake[:, channel] = np.sin(2.0 * np.pi * carrier * time + phase_offset + 0.7 * np.sin(2.0 * np.pi * 2.0 * time))
        sedated[:, channel] = np.sin(2.0 * np.pi * carrier * time + 0.05 * phase_offset)
    awake += 0.03 * rng.normal(size=awake.shape)
    sedated += 0.01 * rng.normal(size=sedated.shape)
    return {
        "awake": standardize_condition(awake, sample_rate_hz, "awake", source_kind="synthetic_demo"),
        "sedated": standardize_condition(sedated, sample_rate_hz, "sedated", source_kind="synthetic_demo"),
    }
