"""Feature extraction for respiration, cardiac/HRV, autonomic proxies, and EEG windows.

Strict scientific guardrails:
- Embodied variables are candidate explanatory features, not proven causal mechanisms.
- Do not describe respiration or parasympathetic activity as equivalent to calmness,
  detachment, equanimity, or liberation.
- No label inference.
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from tools.embodied_controls.types import (
    AutonomicProxyFeatures,
    CardiacWindowFeatures,
    NeuralWindowFeatures,
    RespiratoryWindowFeatures,
    VariableRole,
)


def extract_respiratory_features(
    resp_signal: np.ndarray | Sequence[float],
    sfreq: float,
    min_cycles: int = 2,
    variable_role: VariableRole = VariableRole.CANDIDATE_PREDICTOR,
) -> RespiratoryWindowFeatures:
    """Extract bounded respiratory metrics using zero-crossing cycle detection."""
    clean_resp = np.asarray(resp_signal, dtype=float)
    if len(clean_resp) < int(sfreq * 1.0) or sfreq <= 0 or not np.all(np.isfinite(clean_resp)):
        return RespiratoryWindowFeatures(
            respiratory_phase_rad=None,
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            cycle_count=0,
            variable_role=variable_role.value,
        )

    centered = clean_resp - np.mean(clean_resp)
    std = float(np.std(centered))
    if std < 1e-9:
        return RespiratoryWindowFeatures(
            respiratory_phase_rad=None,
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            cycle_count=0,
            variable_role=variable_role.value,
        )

    # Detect positive-going zero crossings
    signs = np.sign(centered)
    crossings = np.where((signs[:-1] <= 0) & (signs[1:] > 0))[0]

    cycle_count = len(crossings) - 1 if len(crossings) >= 2 else 0
    if cycle_count < min_cycles:
        return RespiratoryWindowFeatures(
            respiratory_phase_rad=None,
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            cycle_count=cycle_count,
            variable_role=variable_role.value,
        )

    cycle_lengths = np.diff(crossings) / sfreq
    avg_cycle_s = float(np.mean(cycle_lengths))
    resp_rate_bpm = float(60.0 / avg_cycle_s) if avg_cycle_s > 0 else None

    # Partition inspiration vs expiration
    insp_times: list[float] = []
    exp_times: list[float] = []
    for i in range(len(crossings) - 1):
        c_start = crossings[i]
        c_end = crossings[i + 1]
        cycle = centered[c_start:c_end]
        if len(cycle) < 3:
            continue
        peak_idx = int(np.argmax(cycle))
        insp_s = peak_idx / sfreq
        exp_s = (len(cycle) - peak_idx) / sfreq
        if insp_s > 0 and exp_s > 0:
            insp_times.append(insp_s)
            exp_times.append(exp_s)

    avg_insp_s = float(np.mean(insp_times)) if insp_times else None
    avg_exp_s = float(np.mean(exp_times)) if exp_times else None
    ie_ratio = (avg_insp_s / avg_exp_s) if (avg_insp_s and avg_exp_s and avg_exp_s > 0) else None

    # Instantaneous phase at end of window relative to last crossing
    last_cross = crossings[-1]
    samples_since = len(centered) - 1 - last_cross
    phase_rad = float((2.0 * np.pi * (samples_since / (avg_cycle_s * sfreq))) % (2.0 * np.pi) - np.pi) if avg_cycle_s > 0 else None

    return RespiratoryWindowFeatures(
        respiratory_phase_rad=phase_rad,
        respiratory_rate_bpm=resp_rate_bpm,
        inspiratory_duration_s=avg_insp_s,
        expiratory_duration_s=avg_exp_s,
        ie_ratio=ie_ratio,
        cycle_count=cycle_count,
        variable_role=variable_role.value,
    )


def extract_cardiac_features(
    ecg_signal: np.ndarray | Sequence[float],
    sfreq: float,
    min_peaks: int = 2,
    variable_role: VariableRole = VariableRole.COVARIATE,
) -> CardiacWindowFeatures:
    """Extract bounded heart rate and HRV-compatible metrics using refractory R-peak detection."""
    clean_ecg = np.asarray(ecg_signal, dtype=float)
    if len(clean_ecg) < int(sfreq * 1.0) or sfreq <= 0 or not np.all(np.isfinite(clean_ecg)):
        return CardiacWindowFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
            pnn50_pct=None,
            r_peak_count=0,
            variable_role=variable_role.value,
        )

    centered = clean_ecg - np.mean(clean_ecg)
    std = float(np.std(centered))
    if std < 1e-9:
        return CardiacWindowFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
            pnn50_pct=None,
            r_peak_count=0,
            variable_role=variable_role.value,
        )

    # 300 ms refractory distance (max 200 BPM)
    min_dist = max(1, int(0.3 * sfreq))
    thresh = float(np.mean(centered) + 1.5 * std)

    peaks: list[int] = []
    last_peak = -min_dist
    for idx in range(1, len(centered) - 1):
        if centered[idx] > thresh and centered[idx] > centered[idx - 1] and centered[idx] > centered[idx + 1]:
            if (idx - last_peak) >= min_dist:
                peaks.append(idx)
                last_peak = idx

    if len(peaks) < min_peaks:
        return CardiacWindowFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
            pnn50_pct=None,
            r_peak_count=len(peaks),
            variable_role=variable_role.value,
        )

    rr_ms = [(peaks[i + 1] - peaks[i]) / sfreq * 1000.0 for i in range(len(peaks) - 1)]
    mean_rr = float(np.mean(rr_ms))
    hr_bpm = float(60000.0 / mean_rr) if mean_rr > 0 else None
    sdnn = float(np.std(rr_ms)) if len(rr_ms) >= 2 else None

    if len(rr_ms) >= 2:
        diffs = np.diff(rr_ms)
        rmssd = float(np.sqrt(np.mean(np.square(diffs))))
        n_pnn50 = int(np.sum(np.abs(diffs) > 50.0))
        pnn50_pct = float(100.0 * n_pnn50 / len(diffs))
    else:
        rmssd = None
        pnn50_pct = None

    return CardiacWindowFeatures(
        heart_rate_bpm=hr_bpm,
        rr_intervals_ms=[float(x) for x in rr_ms],
        rmssd_ms=rmssd,
        sdnn_ms=sdnn,
        pnn50_pct=pnn50_pct,
        r_peak_count=len(peaks),
        variable_role=variable_role.value,
    )


def extract_autonomic_proxy_features(
    eda_signal: np.ndarray | Sequence[float] | None,
    sfreq: float,
    rmssd_ms: float | None = None,
    variable_role: VariableRole = VariableRole.MODERATOR,
) -> AutonomicProxyFeatures:
    """Extract autonomic proxy metrics (electrodermal activity and vagal proxy)."""
    tonic_mean: float | None = None
    phasic_count = 0

    if eda_signal is not None:
        clean_eda = np.asarray(eda_signal, dtype=float)
        if len(clean_eda) > 0 and np.all(np.isfinite(clean_eda)):
            tonic_mean = float(np.mean(clean_eda))
            diffs = np.diff(clean_eda)
            if len(diffs) > 2:
                std_d = float(np.std(diffs))
                thresh = std_d * 2.0
                phasic_count = int(np.sum((diffs[1:] > thresh) & (diffs[:-1] <= thresh)))

    # Vagal tone proxy from HRV RMSSD (log transform)
    vagal_proxy: float | None = None
    if rmssd_ms is not None and rmssd_ms > 0:
        vagal_proxy = float(np.log(rmssd_ms))

    # Composite proxy index
    balance_proxy: float | None = None
    if vagal_proxy is not None and tonic_mean is not None and tonic_mean > 0:
        balance_proxy = float(vagal_proxy / (1.0 + tonic_mean))

    return AutonomicProxyFeatures(
        eda_tonic_mean_us=tonic_mean,
        eda_phasic_peaks_count=phasic_count,
        autonomic_balance_proxy=balance_proxy,
        vagal_tone_proxy=vagal_proxy,
        variable_role=variable_role.value,
    )


def extract_neural_features(
    eeg_data: np.ndarray,
    sfreq: float,
) -> NeuralWindowFeatures:
    """Extract spectral bandpowers, centroid, and RMS amplitude from an EEG window."""
    data = np.asarray(eeg_data, dtype=float)
    if data.ndim == 1:
        data = data[np.newaxis, :]

    n_channels, n_samples = data.shape
    if n_samples < 8 or sfreq <= 0 or not np.all(np.isfinite(data)):
        return NeuralWindowFeatures(
            theta_power_rel=None,
            alpha_power_rel=None,
            beta_power_rel=None,
            gamma_power_rel=None,
            spectral_centroid_hz=None,
            rms_amplitude_uv=None,
            channel_count=n_channels,
        )

    # Window RMS across all channels
    rms_val = float(np.sqrt(np.mean(np.square(data))))

    # Compute FFT power spectrum averaged across channels
    freqs = np.fft.rfftfreq(n_samples, d=1.0 / sfreq)
    fft_vals = np.fft.rfft(data, axis=1)
    power_spectrum = np.mean(np.abs(fft_vals) ** 2, axis=0)

    total_power = float(np.sum(power_spectrum))
    if total_power < 1e-12:
        return NeuralWindowFeatures(
            theta_power_rel=0.0,
            alpha_power_rel=0.0,
            beta_power_rel=0.0,
            gamma_power_rel=0.0,
            spectral_centroid_hz=0.0,
            rms_amplitude_uv=rms_val,
            channel_count=n_channels,
        )

    def _band_rel_power(low: float, high: float) -> float:
        mask = (freqs >= low) & (freqs < high)
        if not np.any(mask):
            return 0.0
        return float(np.sum(power_spectrum[mask]) / total_power)

    theta = _band_rel_power(4.0, 8.0)
    alpha = _band_rel_power(8.0, 12.0)
    beta = _band_rel_power(13.0, 30.0)
    gamma = _band_rel_power(30.0, 45.0)

    centroid = float(np.sum(freqs * power_spectrum) / total_power)

    return NeuralWindowFeatures(
        theta_power_rel=theta,
        alpha_power_rel=alpha,
        beta_power_rel=beta,
        gamma_power_rel=gamma,
        spectral_centroid_hz=centroid,
        rms_amplitude_uv=rms_val,
        channel_count=n_channels,
    )
