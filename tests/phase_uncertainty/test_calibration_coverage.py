"""Tests for phase-uncertainty calibration, binned coverage, and fail-closed tiers.

Verifies:
1. Empirical coverage and bias computation
2. Detection of overconfident estimator behavior under colored noise
3. Detection of conservative estimator behavior under high-SNR AWGN
4. Fail-closed quarantining of near-zero amplitude singularities and frequency drift
5. Guardrail: Never relabels reported phase_std as a statistically valid CI without coverage evidence
"""
from __future__ import annotations

import pytest

from tools.phase_uncertainty import (
    CalibrationVerdict,
    ReliabilityTier,
    estimate_narrowband_phase_uncertainty,
    evaluate_phase_uncertainty_calibration,
    make_colored_noise_signal,
    make_frequency_drift_signal,
    make_near_zero_amplitude_signal,
    make_stationary_narrowband,
)


def test_empirical_coverage_computation_bounds() -> None:
    """Coverage values must be strictly valid probabilities in [0.0, 1.0]."""
    fix = make_stationary_narrowband(n_samples=500, snr_db=10.0, seed=51)
    res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)
    cal = evaluate_phase_uncertainty_calibration(res, fix.true_phase, fixture_id=fix.fixture_id, n_bins=5)

    assert 0.0 <= cal.overall_coverage_1sigma <= 1.0
    assert 0.0 <= cal.overall_coverage_2sigma <= 1.0
    assert cal.overall_rms_error >= 0.0
    assert cal.overall_mean_predicted_std > 0.0

    # Coverage at 2 sigma must be >= coverage at 1 sigma
    assert cal.overall_coverage_2sigma >= cal.overall_coverage_1sigma

    # Check bins
    assert len(cal.bins) == 5
    for b in cal.bins:
        if b.sample_count > 0:
            assert 0.0 <= b.coverage_1sigma <= 1.0
            assert 0.0 <= b.coverage_2sigma <= 1.0
            assert b.coverage_2sigma >= b.coverage_1sigma - 1e-9


def test_overconfidence_detected_under_colored_noise() -> None:
    """Estimator is proven to be OVERCONFIDENT under positively correlated noise."""
    fix = make_colored_noise_signal(n_samples=1000, ar_coef=0.85, snr_db=8.0, seed=52)
    res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)
    cal = evaluate_phase_uncertainty_calibration(res, fix.true_phase, fixture_id=fix.fixture_id, n_bins=5)

    # Under AR(1) noise, empirical RMS error is significantly larger than predicted phase_std
    assert cal.overall_overconfidence_ratio > 1.25
    assert cal.overall_verdict == CalibrationVerdict.OVERCONFIDENT.value

    # Nominal 1-sigma coverage (68.3%) collapses under overconfidence
    assert cal.overall_coverage_1sigma < 0.60


def test_conservatism_detected_under_high_snr_awgn() -> None:
    """Estimator is CONSERVATIVE under high-SNR AWGN due to dual-counting SNR and jitter terms."""
    fix = make_stationary_narrowband(n_samples=1000, snr_db=20.0, seed=53)
    res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)
    cal = evaluate_phase_uncertainty_calibration(res, fix.true_phase, fixture_id=fix.fixture_id, n_bins=5)

    # Predicted std is larger than empirical RMS error
    assert cal.overall_overconfidence_ratio < 0.85
    assert cal.overall_verdict == CalibrationVerdict.CONSERVATIVE.value

    # Empirical coverage exceeds nominal Gaussian bounds
    assert cal.overall_coverage_1sigma > 0.75


def test_fail_closed_quarantine_near_zero_amplitude() -> None:
    """Frames during deep amplitude dips are quarantined into fail_closed_near_zero_amplitude."""
    dip_start = 300
    dip_len = 200
    fix = make_near_zero_amplitude_signal(
        n_samples=800,
        dip_start=dip_start,
        dip_len=dip_len,
        snr_db=15.0,
        seed=54,
    )
    res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)
    cal = evaluate_phase_uncertainty_calibration(res, fix.true_phase, fixture_id=fix.fixture_id, n_bins=5)

    # Quarantined count must be non-zero
    notch_count = cal.tier_counts[ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value]
    assert notch_count > 100


def test_fail_closed_quarantine_frequency_drift() -> None:
    """Frames during severe carrier drift are quarantined into fail_closed_frequency_drift."""
    fix = make_frequency_drift_signal(
        n_samples=1000,
        f_start=5.0,
        f_end=25.0,  # Large drift relative to center
        snr_db=12.0,
        seed=55,
    )
    res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)
    cal = evaluate_phase_uncertainty_calibration(res, fix.true_phase, fixture_id=fix.fixture_id, n_bins=5)

    drift_count = cal.tier_counts[ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value]
    assert drift_count > 200


def test_guardrail_unsupported_ci_claims_rejected() -> None:
    """Verifies candidate metadata explicitly declares unexecuted candidate status."""
    fix = make_stationary_narrowband(n_samples=100, seed=56)
    res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)

    assert res.metadata["candidate_status"] == "reconstructed_from_contract_not_previously_executed"
    assert "ci_confidence_level" not in res.metadata
