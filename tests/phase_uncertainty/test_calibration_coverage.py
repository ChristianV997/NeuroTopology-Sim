"""Tests for phase-uncertainty calibration, binned coverage, and fail-closed tiers.

Verifies:
1. Empirical coverage and bias computation
2. Detection of overconfident estimator behavior under colored noise
3. Detection of conservative estimator behavior under high-SNR AWGN
4. Fail-closed quarantining of zero/near-zero amplitude frames and frequency drift
5. Guardrail: Never relabels reported phase_std as a statistically valid CI without coverage evidence
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from tools.phase_uncertainty import (
    CalibrationVerdict,
    ReliabilityTier,
    UNIFORM_CIRCULAR_STD_CEILING,
    estimate_narrowband_phase_uncertainty,
    evaluate_phase_uncertainty_calibration,
    make_colored_noise_signal,
    make_frequency_drift_signal,
    make_near_zero_amplitude_signal,
    make_stationary_narrowband,
)
from tools.phase_uncertainty.calibration import classify_frame_reliability


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


def test_zero_amplitude_frames_are_not_classified_as_reliable() -> None:
    """A zero-amplitude frame has undefined phase and must fail closed."""
    result = estimate_narrowband_phase_uncertainty(np.zeros(32))

    tiers = classify_frame_reliability(
        result.amplitude,
        result.phase_std,
        result.instantaneous_freq,
        result.median_freq,
    )

    assert set(tiers) == {ReliabilityTier.FAIL_CLOSED_NEAR_ZERO_AMP.value}


def test_non_finite_diagnostics_receive_an_explicit_fail_closed_tier() -> None:
    tiers = classify_frame_reliability(
        np.array([1.0, 1.0]),
        np.array([0.1, np.nan]),
        np.array([0.5, 0.5]),
        0.5,
    )

    assert tiers.tolist() == [
        ReliabilityTier.RELIABLE.value,
        ReliabilityTier.FAIL_CLOSED_INVALID_DATA.value,
    ]


def test_low_frequency_drift_uses_documented_relative_threshold() -> None:
    tiers = classify_frame_reliability(
        np.array([1.0]),
        np.array([0.1]),
        np.array([0.8]),
        0.5,
    )

    assert tiers.tolist() == [ReliabilityTier.FAIL_CLOSED_FREQUENCY_DRIFT.value]


def test_calibration_rejects_misaligned_diagnostic_arrays() -> None:
    fixture = make_stationary_narrowband(n_samples=24, seed=57)
    result = estimate_narrowband_phase_uncertainty(fixture.signal, fs=fixture.fs)

    with pytest.raises(ValueError, match="diagnostic arrays"):
        evaluate_phase_uncertainty_calibration(
            replace(result, amplitude=result.amplitude[:-1]),
            fixture.true_phase,
            fixture_id=fixture.fixture_id,
        )


def test_calibration_rejects_non_finite_uncertainty_values() -> None:
    fixture = make_stationary_narrowband(n_samples=24, seed=58)
    result = estimate_narrowband_phase_uncertainty(fixture.signal, fs=fixture.fs)

    with pytest.raises(ValueError, match="finite"):
        evaluate_phase_uncertainty_calibration(
            replace(result, phase_std=np.full_like(result.phase_std, np.nan)),
            fixture.true_phase,
            fixture_id=fixture.fixture_id,
        )


def test_saturated_two_sigma_coverage_is_flagged_as_uninformative() -> None:
    fixture = make_stationary_narrowband(n_samples=32, seed=59)
    result = estimate_narrowband_phase_uncertainty(fixture.signal, fs=fixture.fs)
    high_uncertainty = replace(
        result,
        phase_std=np.full_like(result.phase_std, UNIFORM_CIRCULAR_STD_CEILING),
    )

    report = evaluate_phase_uncertainty_calibration(
        high_uncertainty,
        fixture.true_phase,
        fixture_id=fixture.fixture_id,
    )

    assert report.overall_coverage_2sigma == 1.0
    assert any("geometrically saturated" in note for note in report.summary_notes)


def test_phase_bias_uses_circular_mean_across_wrap_boundary() -> None:
    fixture = make_stationary_narrowband(n_samples=4, seed=60)
    result = estimate_narrowband_phase_uncertainty(fixture.signal, fs=fixture.fs)
    wrapped_errors = np.array([np.pi - 0.1, -np.pi + 0.1, np.pi - 0.12, -np.pi + 0.12])
    edge_result = replace(
        result,
        phase=wrapped_errors,
        phase_std=np.full(4, 0.1),
        amplitude=np.ones(4),
        instantaneous_freq=np.full(4, result.median_freq),
    )

    report = evaluate_phase_uncertainty_calibration(edge_result, np.zeros(4), n_bins=1)

    assert abs(report.overall_bias) == pytest.approx(np.pi, abs=0.1)
    assert abs(report.bins[0].mean_phase_error) == pytest.approx(np.pi, abs=0.1)


def test_weak_circular_bias_direction_is_reported_per_bin() -> None:
    fixture = make_stationary_narrowband(n_samples=8, seed=61)
    result = estimate_narrowband_phase_uncertainty(fixture.signal, fs=fixture.fs)
    errors = np.array([0.0, np.pi, 0.0, np.pi, 0.2, 0.2, 0.2, 0.2])
    phase_std = np.array([0.1] * 4 + [0.5] * 4)
    ambiguous_bin = replace(
        result,
        phase=errors,
        phase_std=phase_std,
        amplitude=np.ones(8),
        instantaneous_freq=np.full(8, result.median_freq),
    )

    report = evaluate_phase_uncertainty_calibration(ambiguous_bin, np.zeros(8), n_bins=2)

    assert abs(report.overall_bias) < 0.3  # The other bin keeps the overall direction defined.
    assert abs(report.bins[0].mean_phase_error) < 0.3  # Numerically zero, but direction is ambiguous.
    assert any("bins [0]" in note and "weakly determined" in note for note in report.summary_notes)


@pytest.mark.parametrize("n_bins", [0, -1, True, 1.5], ids=["zero", "negative", "boolean", "fractional"])
def test_calibration_rejects_invalid_bin_counts(n_bins: object) -> None:
    fixture = make_stationary_narrowband(n_samples=16, seed=62)
    result = estimate_narrowband_phase_uncertainty(fixture.signal, fs=fixture.fs)

    with pytest.raises(ValueError, match="n_bins"):
        evaluate_phase_uncertainty_calibration(result, fixture.true_phase, n_bins=n_bins)


def test_cli_rejects_zero_bins_with_argument_error() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-m", "tools.phase_uncertainty.cli", "--bins", "0"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 2
    assert "--bins" in completed.stderr
    assert "positive integer" in completed.stderr


def test_reliability_classifier_accepts_signed_instantaneous_frequency() -> None:
    tiers = classify_frame_reliability(
        amplitude=np.ones(3),
        phase_std=np.full(3, 0.1),
        instantaneous_freq=np.full(3, -10.0),
        median_freq=-10.0,
    )

    assert set(tiers.tolist()) == {ReliabilityTier.RELIABLE.value}
