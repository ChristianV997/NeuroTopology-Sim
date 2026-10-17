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
    mean_phase_error: float          # Bias
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


def classify_frame_reliability(
    amplitude: np.ndarray,
    phase_std: np.ndarray,
    instantaneous_freq: np.ndarray,
    median_freq: float,
) -> np.ndarray:
    """Assign fail-closed reliability tier to each time frame.

    Returns array of string tier names matching ReliabilityTier enum.
    """
    n = len(amplitude)
    tiers = np.empty(n, dtype=object)

    med_amp = float(np.median(amplitude)) if n > 0 else 1.0
    amp_floor = 0.15 * med_amp

    freq_dev = np.abs(instantaneous_freq - median_freq)
    max_freq_dev = 0.5 * max(1.0, abs(median_freq))

    for i in range(n):
        # 1. Near-zero amplitude singularity
        if amplitude[i] < amp_floor:
            tiers[i] = ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value
        # 2. Uncertainty pegged at ceiling
        elif phase_std[i] >= 0.95 * UNIFORM_CIRCULAR_STD_CEILING:
            tiers[i] = ReliabilityTier.FAIL_CLOSED_MAX_UNCERTAINTY.value
        # 3. Severe frequency drift / nonstationarity
        elif freq_dev[i] > max_freq_dev:
            tiers[i] = ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value
        # 4. Marginal regime
        elif phase_std[i] > 0.60 * UNIFORM_CIRCULAR_STD_CEILING or amplitude[i] < 0.35 * med_amp:
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
    est_phase = np.asarray(result.phase, dtype=np.float64)
    ref_phase = np.asarray(true_phase, dtype=np.float64)
    pred_std = np.asarray(result.phase_std, dtype=np.float64)

    if est_phase.shape != ref_phase.shape:
        raise ValueError(f"Shape mismatch: est_phase {est_phase.shape} != true_phase {ref_phase.shape}")

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
    error = wrap_phase(est_phase - ref_phase)

    # Overall metrics
    overall_mean_std = float(np.mean(pred_std))
    overall_bias = float(np.mean(error))
    overall_rms = float(np.sqrt(np.mean(error ** 2)))

    cov_1 = float(np.mean(np.abs(error) <= 1.0 * pred_std))
    cov_2 = float(np.mean(np.abs(error) <= 1.96 * pred_std))

    ratio = overall_rms / max(1e-12, overall_mean_std)
    if ratio > 1.15:
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
        m_bias = float(np.mean(b_err))
        m_rms = float(np.sqrt(np.mean(b_err ** 2)))
        b_cov1 = float(np.mean(np.abs(b_err) <= 1.0 * b_std))
        b_cov2 = float(np.mean(np.abs(b_err) <= 1.96 * b_std))

        b_ratio = m_rms / max(1e-12, m_std)
        if b_ratio > 1.15:
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
    if overall_verdict == CalibrationVerdict.OVERCONFIDENT.value:
        notes.append(f"Estimator is OVERCONFIDENT overall (RMS error is {ratio:.2f}x predicted phase_std).")
    elif overall_verdict == CalibrationVerdict.CONSERVATIVE.value:
        notes.append(f"Estimator is CONSERVATIVE overall (RMS error is {ratio:.2f}x predicted phase_std).")
    else:
        notes.append("Estimator is reasonably calibrated overall under the tested synthetic regime.")

    if tier_counts[ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value] > 0:
        notes.append(f"{tier_counts[ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value]} frames quarantined due to near-zero amplitude singularities.")
    if tier_counts[ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value] > 0:
        notes.append(f"{tier_counts[ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value]} frames quarantined due to severe carrier frequency drift.")
    if tier_counts[ReliabilityTier.FAIL_CLOSED_MAX_UNCERTAINTY.value] > 0:
        notes.append(f"{tier_counts[ReliabilityTier.FAIL_CLOSED_MAX_UNCERTAINTY.value]} frames capped at uniform circular std ceiling pi/sqrt(3).")

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
