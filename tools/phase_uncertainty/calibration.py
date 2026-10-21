"""Calibration and empirical coverage evaluation for phase-uncertainty estimation.

Evaluates:
1. Circular phase error: e_theta[n] = wrap(theta_est[n] - theta_true[n])
2. Empirical coverage at 1*sigma (nominal 68.27%) and 1.96*sigma (nominal 95.0%)
3. Binned coverage, bias, and overconfidence ratio (RMS_error / predicted_std)
4. Detection of overconfident vs conservative regimes
5. Fail-closed reliability categorization (quarantining uncalibrated regimes)

Guardrail: Implementation strictly in pure NumPy and standard library.
Never labels phase_std as a statistically valid confidence interval without
empirical coverage support.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence
import numpy as np

from .candidate_estimator import (
    PhaseUncertaintyResult,
    UNIFORM_CIRCULAR_STD_CEILING,
    wrap_phase,
)


class CalibrationVerdict(str, Enum):
    """Categorization of uncertainty calibration accuracy."""
    OVERCONFIDENT = "overconfident"      # Errors are larger than predicted (ratio > 1.15)
    WELL_CALIBRATED = "well_calibrated"  # 0.85 <= ratio <= 1.15
    CONSERVATIVE = "conservative"        # Errors are smaller than predicted (ratio < 0.85)
    INSUFFICIENT_DATA = "insufficient_data"


class ReliabilityTier(str, Enum):
    """Fail-closed operational reliability classification."""
    RELIABLE = "reliable"
    MARGINAL = "marginal"
    FAIL_CLOSED_INVALID_DATA = "fail_closed_invalid_data"
    FAIL_CLOSED_NEAR_ZERO_AMP = "fail_closed_near_zero_amplitude"
    FAIL_CLOSED_FREQUENCY_DRIFT = "fail_closed_frequency_drift"
    FAIL_CLOSED_MAX_UNCERTAINTY = "fail_closed_max_uncertainty"


@dataclass(frozen=True)
class CalibrationBin:
    """Statistics for a specific predicted uncertainty bin [lower, upper)."""
    bin_idx: int
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_predicted_std: float
    mean_phase_error: float          # Circular-mean bias in radians
    rms_phase_error: float           # Empirical standard error
    coverage_1sigma: float           # Fraction with |e| <= 1.0 * phase_std (nominal ~68.3%)
    coverage_2sigma: float           # Fraction with |e| <= 1.96 * phase_std (nominal ~95.0%)
    overconfidence_ratio: float      # rms_phase_error / mean_predicted_std
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_idx": self.bin_idx,
            "bounds": [round(self.lower_bound, 4), round(self.upper_bound, 4)],
            "sample_count": self.sample_count,
            "mean_predicted_std": round(self.mean_predicted_std, 4),
            "bias_mean_error": round(self.mean_phase_error, 4),
            "empirical_rms_error": round(self.rms_phase_error, 4),
            "coverage_1sigma": round(self.coverage_1sigma, 4),
            "coverage_2sigma": round(self.coverage_2sigma, 4),
            "overconfidence_ratio": round(self.overconfidence_ratio, 4),
            "verdict": self.verdict,
        }


@dataclass
class CalibrationReport:
    """Comprehensive calibration audit report for a synthetic signal."""
    fixture_id: str
    n_samples: int
    overall_mean_predicted_std: float
    overall_bias: float
    overall_rms_error: float
    overall_coverage_1sigma: float
    overall_coverage_2sigma: float
    overall_overconfidence_ratio: float
    overall_verdict: str
    bins: list[CalibrationBin] = field(default_factory=list)
    tier_counts: dict[str, int] = field(default_factory=dict)
    summary_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "n_samples": self.n_samples,
            "overall": {
                "mean_predicted_std": round(self.overall_mean_predicted_std, 4),
                "bias_mean_error": round(self.overall_bias, 4),
                "empirical_rms_error": round(self.overall_rms_error, 4),
                "coverage_1sigma": round(self.overall_coverage_1sigma, 4),
                "coverage_2sigma": round(self.overall_coverage_2sigma, 4),
                "overconfidence_ratio": round(self.overall_overconfidence_ratio, 4),
                "verdict": self.overall_verdict,
            },
            "bins": [b.to_dict() for b in self.bins],
            "reliability_tier_counts": self.tier_counts,
            "summary_notes": self.summary_notes,
        }


def _circular_mean_phase_error(errors: np.ndarray) -> tuple[float, float]:
    """Return circular mean error and mean resultant length for wrapped radians."""
    if errors.size == 0:
        return 0.0, 0.0
    sine_mean = float(np.mean(np.sin(errors)))
    cosine_mean = float(np.mean(np.cos(errors)))
    resultant_length = math.hypot(sine_mean, cosine_mean)
    if resultant_length <= 1e-12:
        return 0.0, resultant_length
    return math.atan2(sine_mean, cosine_mean), resultant_length


def _validate_n_bins(n_bins: int) -> int:
    if isinstance(n_bins, (bool, np.bool_)) or not isinstance(n_bins, (int, np.integer)) or n_bins <= 0:
        raise ValueError("n_bins must be a positive integer")
    return int(n_bins)


def classify_frame_reliability(
    amplitude: np.ndarray,
    phase_std: np.ndarray,
    instantaneous_freq: np.ndarray,
    median_freq: float,
) -> np.ndarray:
    """Assign fail-closed reliability tier to each time frame.

    Returns array of string tier names matching ReliabilityTier enum.
    """
    try:
        amplitude_values = np.asarray(amplitude, dtype=np.float64)
        phase_std_values = np.asarray(phase_std, dtype=np.float64)
        frequency_values = np.asarray(instantaneous_freq, dtype=np.float64)
        median_freq_value = float(median_freq)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("calibration diagnostics must be numeric") from exc

    arrays = (amplitude_values, phase_std_values, frequency_values)
    if any(values.ndim != 1 for values in arrays):
        raise ValueError("calibration diagnostic arrays must be one-dimensional")
    if not (amplitude_values.shape == phase_std_values.shape == frequency_values.shape):
        raise ValueError("calibration diagnostic arrays must have identical lengths")

    n = amplitude_values.size
    tiers = np.full(n, ReliabilityTier.FAIL_CLOSED_INVALID_DATA.value, dtype=object)
    if not math.isfinite(median_freq_value):
        return tiers

    valid = (
        np.isfinite(amplitude_values)
        & np.isfinite(phase_std_values)
        & np.isfinite(frequency_values)
        & (amplitude_values >= 0.0)
        & (phase_std_values >= 0.0)
    )
    if not np.any(valid):
        return tiers

    med_amp = float(np.median(amplitude_values[valid]))
    if med_amp <= 0.0 or not math.isfinite(med_amp):
        tiers[valid] = ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value
        return tiers

    amp_floor = 0.15 * med_amp
    freq_dev = np.abs(frequency_values - median_freq_value)
    max_freq_dev = 0.5 * abs(median_freq_value)

    if not math.isfinite(amp_floor) or not math.isfinite(max_freq_dev):
        return tiers

    for i in range(n):
        if not valid[i]:
            continue
        if not math.isfinite(freq_dev[i]):
            tiers[i] = ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value
        # 1. Zero/near-zero amplitude makes phase undefined or noise-sensitive
        elif amplitude_values[i] < amp_floor:
            tiers[i] = ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value
        # 2. Uncertainty near the configured maximum
        elif phase_std_values[i] >= 0.95 * UNIFORM_CIRCULAR_STD_CEILING:
            tiers[i] = ReliabilityTier.FAIL_CLOSED_MAX_UNCERTAINTY.value
        # 3. Severe frequency drift / nonstationarity
        elif freq_dev[i] > max_freq_dev:
            tiers[i] = ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value
        # 4. Marginal regime
        elif phase_std_values[i] > 0.60 * UNIFORM_CIRCULAR_STD_CEILING or amplitude_values[i] < 0.35 * med_amp:
            tiers[i] = ReliabilityTier.MARGINAL.value
        # 5. Reliable regime
        else:
            tiers[i] = ReliabilityTier.RELIABLE.value

    return tiers


def evaluate_phase_uncertainty_calibration(
    result: PhaseUncertaintyResult,
    true_phase: np.ndarray,
    fixture_id: str = "synthetic",
    n_bins: int = 5,
) -> CalibrationReport:
    """Evaluate empirical coverage, bias, and calibration ratios across predicted uncertainty bins."""
    n_bins = _validate_n_bins(n_bins)
    try:
        est_phase = np.asarray(result.phase, dtype=np.float64)
        ref_phase = np.asarray(true_phase, dtype=np.float64)
        pred_std = np.asarray(result.phase_std, dtype=np.float64)
        amplitude = np.asarray(result.amplitude, dtype=np.float64)
        instantaneous_freq = np.asarray(result.instantaneous_freq, dtype=np.float64)
        median_freq = float(result.median_freq)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("calibration inputs must be numeric") from exc

    if est_phase.ndim != 1 or ref_phase.ndim != 1:
        raise ValueError("calibration phase arrays must be one-dimensional")
    if est_phase.shape != ref_phase.shape:
        raise ValueError(f"Shape mismatch: est_phase {est_phase.shape} != true_phase {ref_phase.shape}")

    diagnostics = {
        "phase_std": pred_std,
        "amplitude": amplitude,
        "instantaneous_freq": instantaneous_freq,
    }
    for name, values in diagnostics.items():
        if values.ndim != 1 or values.shape != est_phase.shape:
            raise ValueError(f"calibration diagnostic arrays must match phase samples: {name}")

    all_values = (est_phase, ref_phase, *diagnostics.values())
    if not math.isfinite(median_freq) or any(not np.all(np.isfinite(values)) for values in all_values):
        raise ValueError("calibration inputs must contain only finite values")
    if np.any(pred_std < 0.0) or np.any(amplitude < 0.0):
        raise ValueError("calibration uncertainty and amplitude diagnostics must be non-negative")

    n = len(est_phase)
    if n == 0:
        return CalibrationReport(
            fixture_id=fixture_id,
            n_samples=0,
            overall_mean_predicted_std=0.0,
            overall_bias=0.0,
            overall_rms_error=0.0,
            overall_coverage_1sigma=0.0,
            overall_coverage_2sigma=0.0,
            overall_overconfidence_ratio=1.0,
            overall_verdict=CalibrationVerdict.INSUFFICIENT_DATA.value,
        )

    # 1. Circular phase error in (-pi, pi]
    # Pre-wrap both phases to prevent float64 subtraction overflow when phases are large
    error = wrap_phase(wrap_phase(est_phase) - wrap_phase(ref_phase))

    # Overall metrics
    overall_mean_std = float(np.mean(pred_std))
    overall_bias, overall_bias_resultant = _circular_mean_phase_error(error)
    overall_rms = float(np.sqrt(np.mean(error ** 2)))

    cov_1 = float(np.mean(np.abs(error) <= 1.0 * pred_std))
    cov_2 = float(np.mean(np.abs(error) <= 1.96 * pred_std))

    ratio = overall_rms / max(1e-12, overall_mean_std)
    if not math.isfinite(ratio) or not math.isfinite(overall_rms) or not math.isfinite(overall_mean_std) or not math.isfinite(overall_bias):
        overall_verdict = CalibrationVerdict.OVERCONFIDENT.value
    elif ratio > 1.15:
        overall_verdict = CalibrationVerdict.OVERCONFIDENT.value
    elif ratio < 0.85:
        overall_verdict = CalibrationVerdict.CONSERVATIVE.value
    else:
        overall_verdict = CalibrationVerdict.WELL_CALIBRATED.value

    # 2. Binned calibration
    # Create bin edges between min and max of predicted std (or up to ceiling)
    min_std = float(np.min(pred_std))
    max_std = float(np.max(pred_std))
    if np.isclose(min_std, max_std):
        bin_edges = np.linspace(min_std * 0.9, max_std * 1.1 + 1e-4, n_bins + 1)
    else:
        bin_edges = np.linspace(min_std, max_std + 1e-6, n_bins + 1)

    bins: list[CalibrationBin] = []
    weak_bias_bins: list[int] = []
    for b_idx in range(n_bins):
        lo = float(bin_edges[b_idx])
        hi = float(bin_edges[b_idx + 1])
        mask = (pred_std >= lo) & (pred_std < hi)
        count = int(np.count_nonzero(mask))

        if count == 0:
            bins.append(CalibrationBin(
                bin_idx=b_idx,
                lower_bound=lo,
                upper_bound=hi,
                sample_count=0,
                mean_predicted_std=(lo + hi) / 2.0,
                mean_phase_error=0.0,
                rms_phase_error=0.0,
                coverage_1sigma=0.0,
                coverage_2sigma=0.0,
                overconfidence_ratio=1.0,
                verdict=CalibrationVerdict.INSUFFICIENT_DATA.value,
            ))
            continue

        b_err = error[mask]
        b_std = pred_std[mask]
        m_std = float(np.mean(b_std))
        m_bias, b_bias_resultant = _circular_mean_phase_error(b_err)
        if b_bias_resultant < 0.1:
            weak_bias_bins.append(b_idx)
        m_rms = float(np.sqrt(np.mean(b_err ** 2)))
        b_cov1 = float(np.mean(np.abs(b_err) <= 1.0 * b_std))
        b_cov2 = float(np.mean(np.abs(b_err) <= 1.96 * b_std))

        b_ratio = m_rms / max(1e-12, m_std)
        if not math.isfinite(b_ratio) or not math.isfinite(m_rms) or not math.isfinite(m_std) or not math.isfinite(m_bias):
            b_verdict = CalibrationVerdict.OVERCONFIDENT.value
        elif b_ratio > 1.15:
            b_verdict = CalibrationVerdict.OVERCONFIDENT.value
        elif b_ratio < 0.85:
            b_verdict = CalibrationVerdict.CONSERVATIVE.value
        else:
            b_verdict = CalibrationVerdict.WELL_CALIBRATED.value

        bins.append(CalibrationBin(
            bin_idx=b_idx,
            lower_bound=lo,
            upper_bound=hi,
            sample_count=count,
            mean_predicted_std=m_std,
            mean_phase_error=m_bias,
            rms_phase_error=m_rms,
            coverage_1sigma=b_cov1,
            coverage_2sigma=b_cov2,
            overconfidence_ratio=b_ratio,
            verdict=b_verdict,
        ))

    # 3. Classify reliability tiers
    tiers = classify_frame_reliability(
        result.amplitude,
        result.phase_std,
        result.instantaneous_freq,
        result.median_freq,
    )
    tier_counts = {t.value: int(np.count_nonzero(tiers == t.value)) for t in ReliabilityTier}

    notes = []
    if overall_bias_resultant < 0.1:
        notes.append(
            "Circular mean phase-error direction is weakly determined because the error resultant length is below 0.1."
        )
    if weak_bias_bins:
        bin_labels = ", ".join(str(b_idx) for b_idx in weak_bias_bins)
        notes.append(
            f"Circular bias direction is weakly determined for calibration bins [{bin_labels}] because their resultant length is below 0.1; "
            "a numerically near-zero mean direction in these bins is not evidence of near-zero bias."
        )
    if not math.isfinite(ratio):
        notes.append("Estimator calibration ratio is non-finite; failing closed to OVERCONFIDENT.")
    elif overall_verdict == CalibrationVerdict.OVERCONFIDENT.value:
        notes.append(f"Estimator is OVERCONFIDENT overall (RMS error is {ratio:.2f}x predicted phase_std).")
    elif overall_verdict == CalibrationVerdict.CONSERVATIVE.value:
        notes.append(f"Estimator is CONSERVATIVE overall (RMS error is {ratio:.2f}x predicted phase_std).")
    else:
        notes.append(
            "The synthetic RMS-to-reported-std ratio falls within the configured heuristic band; this is not a calibrated CI claim."
        )

    if tier_counts[ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value] > 0:
        notes.append(
            f"{tier_counts[ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value]} frames quarantined for zero or near-zero amplitude; "
            "phase is undefined at zero and noise-sensitive at low amplitude."
        )
    if tier_counts[ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value] > 0:
        notes.append(f"{tier_counts[ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value]} frames quarantined due to severe carrier frequency drift.")
    if tier_counts[ReliabilityTier.FAIL_CLOSED_MAX_UNCERTAINTY.value] > 0:
        notes.append(
            f"{tier_counts[ReliabilityTier.FAIL_CLOSED_MAX_UNCERTAINTY.value]} frames entered the high-uncertainty tier "
            "at or above 95% of the uniform circular standard-deviation ceiling; this tier threshold does not mean "
            "the reported values were capped."
        )
    saturated_2sigma = int(np.count_nonzero(1.96 * pred_std >= np.pi))
    if saturated_2sigma:
        notes.append(
            "Wrapped-error 2-sigma coverage is geometrically saturated for "
            f"{saturated_2sigma} frames (1.96 * phase_std >= pi); this is not calibration evidence."
        )

    return CalibrationReport(
        fixture_id=fixture_id,
        n_samples=n,
        overall_mean_predicted_std=overall_mean_std,
        overall_bias=overall_bias,
        overall_rms_error=overall_rms,
        overall_coverage_1sigma=cov_1,
        overall_coverage_2sigma=cov_2,
        overall_overconfidence_ratio=ratio,
        overall_verdict=overall_verdict,
        bins=bins,
        tier_counts=tier_counts,
        summary_notes=notes,
    )
