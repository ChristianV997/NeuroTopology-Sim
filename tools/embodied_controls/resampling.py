"""Resampling, clock alignment, and drift estimation for embodied-control signals.

Enforces causal interpolation and strict sample-rate metadata provenance.
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from tools.embodied_controls.types import (
    ClockDriftDiagnostics,
    InterpolationMethod,
    ResamplingRecord,
)


def resample_causal_linear(
    data: np.ndarray,
    source_fs: float,
    target_fs: float,
    channel_name: str = "signal",
) -> tuple[np.ndarray, ResamplingRecord]:
    """Resample 1D signal using strictly causal linear interpolation.
    
    Target sample at time t_k is evaluated strictly from surrounding past samples.
    """
    if abs(source_fs - target_fs) < 1e-4:
        return data.copy(), ResamplingRecord(
            channel_name=channel_name,
            source_sfreq_hz=source_fs,
            target_sfreq_hz=target_fs,
            ratio=1.0,
            method=InterpolationMethod.IDENTITY.value,
            interpolated=False,
        )

    n_source = len(data)
    if n_source == 0 or source_fs <= 0 or target_fs <= 0:
        return np.zeros(0, dtype=data.dtype), ResamplingRecord(
            channel_name=channel_name,
            source_sfreq_hz=source_fs,
            target_sfreq_hz=target_fs,
            ratio=target_fs / source_fs if source_fs > 0 else 1.0,
            method=InterpolationMethod.CAUSAL_LINEAR.value,
            interpolated=True,
        )

    duration_s = n_source / source_fs
    n_target = max(1, int(math.floor(duration_s * target_fs)))

    target_times = np.arange(n_target, dtype=float) / target_fs
    source_positions = target_times * source_fs

    idx_floor = np.floor(source_positions).astype(int)
    idx_floor = np.clip(idx_floor, 0, n_source - 1)
    idx_ceil = np.clip(idx_floor + 1, 0, n_source - 1)
    weights = source_positions - idx_floor

    resampled = (1.0 - weights) * data[idx_floor] + weights * data[idx_ceil]
    record = ResamplingRecord(
        channel_name=channel_name,
        source_sfreq_hz=source_fs,
        target_sfreq_hz=target_fs,
        ratio=float(target_fs / source_fs),
        method=InterpolationMethod.CAUSAL_LINEAR.value,
        interpolated=True,
    )
    return resampled, record


def resample_nearest(
    data: np.ndarray,
    source_fs: float,
    target_fs: float,
    channel_name: str = "signal",
) -> tuple[np.ndarray, ResamplingRecord]:
    """Resample 1D signal using nearest-neighbor interpolation."""
    if abs(source_fs - target_fs) < 1e-4:
        return data.copy(), ResamplingRecord(
            channel_name=channel_name,
            source_sfreq_hz=source_fs,
            target_sfreq_hz=target_fs,
            ratio=1.0,
            method=InterpolationMethod.IDENTITY.value,
            interpolated=False,
        )

    n_source = len(data)
    if n_source == 0 or source_fs <= 0 or target_fs <= 0:
        return np.zeros(0, dtype=data.dtype), ResamplingRecord(
            channel_name=channel_name,
            source_sfreq_hz=source_fs,
            target_sfreq_hz=target_fs,
            ratio=target_fs / source_fs if source_fs > 0 else 1.0,
            method=InterpolationMethod.NEAREST.value,
            interpolated=True,
        )

    duration_s = n_source / source_fs
    n_target = max(1, int(math.floor(duration_s * target_fs)))

    target_times = np.arange(n_target, dtype=float) / target_fs
    source_positions = np.round(target_times * source_fs).astype(int)
    source_positions = np.clip(source_positions, 0, n_source - 1)

    resampled = data[source_positions]
    record = ResamplingRecord(
        channel_name=channel_name,
        source_sfreq_hz=source_fs,
        target_sfreq_hz=target_fs,
        ratio=float(target_fs / source_fs),
        method=InterpolationMethod.NEAREST.value,
        interpolated=True,
    )
    return resampled, record


def detect_clock_drift(
    timestamps: np.ndarray | Sequence[float],
    nominal_fs: float,
    drift_threshold_ppm: float = 50.0,
) -> ClockDriftDiagnostics:
    """Diagnose inter-sensor clock drift, jitter, and timestamp discontinuities."""
    ts = np.asarray(timestamps, dtype=float)
    if len(ts) < 2 or nominal_fs <= 0:
        return ClockDriftDiagnostics(
            estimated_drift_ppm=0.0,
            drift_detected=False,
            clock_discontinuity_s=0.0,
            warning=None,
        )

    nominal_dt = 1.0 / nominal_fs
    diffs = np.diff(ts)

    # Detect largest discontinuity
    max_discontinuity = float(np.max(np.abs(diffs - nominal_dt)))

    # Estimate mean drift in parts-per-million (ppm)
    mean_dt = float(np.mean(diffs))
    drift_fraction = abs(mean_dt - nominal_dt) / nominal_dt
    drift_ppm = float(drift_fraction * 1e6)

    drift_detected = (drift_ppm > drift_threshold_ppm) or (max_discontinuity > 0.05 * nominal_dt)
    warning = None
    if drift_detected:
        warning = f"Clock drift ({drift_ppm:.1f} ppm) or discontinuity ({max_discontinuity:.4f}s) detected."

    return ClockDriftDiagnostics(
        estimated_drift_ppm=drift_ppm,
        drift_detected=drift_detected,
        clock_discontinuity_s=max_discontinuity,
        warning=warning,
    )
