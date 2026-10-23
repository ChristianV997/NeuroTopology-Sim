"""Reproducible nuisance scenario factory for synthetic operating-characteristic studies.

This package provides pure NumPy, deterministic generators for colored noise (1/f^chi),
target SNR scaling, and electrode coordinate jitter for evaluation studies.
Status: HOLD / SYNTHETIC_ONLY.
"""
from __future__ import annotations

from sim.nuisance_scenarios.colored_noise import (
    SpectralSlopeFit,
    estimate_spectral_slope,
    generate_colored_noise,
)
from sim.nuisance_scenarios.config import (
    NuisanceGridConfig,
    NuisanceScenarioConfig,
)
from sim.nuisance_scenarios.factory import (
    NuisanceScenarioFactory,
    generate_default_signal,
    generate_synthetic_spherical_coordinates,
)
from sim.nuisance_scenarios.jitter import (
    JitteredCoordinateResult,
    apply_coordinate_jitter,
)
from sim.nuisance_scenarios.models import (
    RealizedDiagnostics,
    ScenarioResult,
)
from sim.nuisance_scenarios.snr_mixer import (
    MixedSignalResult,
    mix_at_target_snr,
)

__all__ = [
    "NuisanceScenarioConfig",
    "NuisanceGridConfig",
    "generate_colored_noise",
    "estimate_spectral_slope",
    "SpectralSlopeFit",
    "mix_at_target_snr",
    "MixedSignalResult",
    "apply_coordinate_jitter",
    "JitteredCoordinateResult",
    "RealizedDiagnostics",
    "ScenarioResult",
    "NuisanceScenarioFactory",
    "generate_synthetic_spherical_coordinates",
    "generate_default_signal",
]
