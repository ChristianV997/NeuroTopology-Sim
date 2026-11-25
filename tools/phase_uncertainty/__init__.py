"""Narrowband Phase Uncertainty Calibration and Audit Harness."""
from __future__ import annotations

from .candidate_estimator import (
    EstimatorConfig,
    PhaseUncertaintyResult,
    UNIFORM_CIRCULAR_STD_CEILING,
    compute_analytic_signal,
    compute_mad,
    estimate_narrowband_phase_uncertainty,
    wrap_phase,
)
from .fixtures import (
    NarrowbandFixture,
    get_all_calibration_fixtures,
    make_amplitude_modulated_signal,
    make_colored_noise_signal,
    make_frequency_drift_signal,
    make_near_zero_amplitude_signal,
    make_short_window_burst,
    make_stationary_narrowband,
)
from .calibration import (
    CalibrationBin,
    CalibrationReport,
    CalibrationVerdict,
    ReliabilityTier,
    classify_frame_reliability,
    evaluate_phase_uncertainty_calibration,
)

__all__ = [
    "CalibrationBin",
    "CalibrationReport",
    "CalibrationVerdict",
    "EstimatorConfig",
    "NarrowbandFixture",
    "PhaseUncertaintyResult",
    "ReliabilityTier",
    "UNIFORM_CIRCULAR_STD_CEILING",
    "classify_frame_reliability",
    "compute_analytic_signal",
    "compute_mad",
    "estimate_narrowband_phase_uncertainty",
    "evaluate_phase_uncertainty_calibration",
    "get_all_calibration_fixtures",
    "make_amplitude_modulated_signal",
    "make_colored_noise_signal",
    "make_frequency_drift_signal",
    "make_near_zero_amplitude_signal",
    "make_short_window_burst",
    "make_stationary_narrowband",
    "wrap_phase",
]
