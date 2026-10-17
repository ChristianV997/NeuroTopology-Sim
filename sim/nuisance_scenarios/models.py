"""Result data models and diagnostics for synthetic nuisance scenarios.

Provides structured containers for realized scenario outputs, noise properties,
SNR measurements, and coordinate jitter metrics with JSON serialization support.
Strictly tagged with status 'HOLD / SYNTHETIC_ONLY'.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from sim.nuisance_scenarios.config import NuisanceScenarioConfig


@dataclass(frozen=True)
class RealizedDiagnostics:
    """Realized statistical diagnostics of a generated scenario.

    Attributes:
        realized_snr_db: Realized SNR in decibels = 10 * log10(P_signal / P_scaled_noise).
        clean_signal_power: Global mean-squared power of the clean signal.
        noise_power_before_scaling: Power of the raw unit colored noise.
        noise_power_scaled: Power of the noise after scaling to target SNR.
        noise_scale_factor: Amplitude scaling multiplier applied to raw noise.
        estimated_chi: Fitted spectral slope from log-log periodogram (or None).
        chi_fit_r2: Coefficient of determination R^2 of spectral slope fit.
        jitter_mean_disp: Mean Euclidean displacement of jittered electrodes.
        jitter_max_disp: Maximum Euclidean displacement of jittered electrodes.
        jitter_rms_disp: Root-mean-squared displacement of jittered electrodes.
        jitter_units: Declared unit of coordinate jitter ('mm', 'cm', 'm').
        renormalize_to_sphere: Whether coordinates were projected back to sphere radius.
        is_finite: Boolean indicating all signals and coordinates are strictly finite.
        status: Governance status tag ('HOLD / SYNTHETIC_ONLY').
    """

    realized_snr_db: float
    clean_signal_power: float
    noise_power_before_scaling: float
    noise_power_scaled: float
    noise_scale_factor: float
    estimated_chi: Optional[float] = None
    chi_fit_r2: Optional[float] = None
    jitter_mean_disp: float = 0.0
    jitter_max_disp: float = 0.0
    jitter_rms_disp: float = 0.0
    jitter_units: str = "mm"
    renormalize_to_sphere: bool = False
    is_finite: bool = True
    status: str = "HOLD / SYNTHETIC_ONLY"

    def to_dict(self) -> Dict[str, Any]:
        """Convert diagnostics to serializable dictionary."""
        return {
            "realized_snr_db": float(self.realized_snr_db),
            "clean_signal_power": float(self.clean_signal_power),
            "noise_power_before_scaling": float(self.noise_power_before_scaling),
            "noise_power_scaled": float(self.noise_power_scaled),
            "noise_scale_factor": float(self.noise_scale_factor),
            "estimated_chi": float(self.estimated_chi) if self.estimated_chi is not None else None,
            "chi_fit_r2": float(self.chi_fit_r2) if self.chi_fit_r2 is not None else None,
            "jitter_mean_disp": float(self.jitter_mean_disp),
            "jitter_max_disp": float(self.jitter_max_disp),
            "jitter_rms_disp": float(self.jitter_rms_disp),
            "jitter_units": self.jitter_units,
            "renormalize_to_sphere": bool(self.renormalize_to_sphere),
            "is_finite": bool(self.is_finite),
            "status": self.status,
        }


@dataclass
class ScenarioResult:
    """Complete output bundle for a generated synthetic nuisance scenario.

    Attributes:
        scenario_id: Deterministic identifier string derived from configuration.
        config: NuisanceScenarioConfig used to generate this scenario.
        clean_signal: 2D numpy array of shape (n_channels, n_samples).
        noisy_signal: 2D numpy array of shape (n_channels, n_samples) with scaled noise.
        scaled_noise: 2D numpy array of shape (n_channels, n_samples) containing scaled noise.
        original_coordinates: Optional 2D array of shape (n_channels, 3) representing original electrode positions.
        jittered_coordinates: Optional 2D array of shape (n_channels, 3) representing displaced positions.
        diagnostics: RealizedDiagnostics instance containing verified metrics.
    """

    scenario_id: str
    config: NuisanceScenarioConfig
    clean_signal: np.ndarray
    noisy_signal: np.ndarray
    scaled_noise: np.ndarray
    original_coordinates: Optional[np.ndarray] = None
    jittered_coordinates: Optional[np.ndarray] = None
    diagnostics: RealizedDiagnostics = field(
        default_factory=lambda: RealizedDiagnostics(
            realized_snr_db=0.0,
            clean_signal_power=0.0,
            noise_power_before_scaling=0.0,
            noise_power_scaled=0.0,
            noise_scale_factor=1.0,
        )
    )

    def summary_dict(self) -> Dict[str, Any]:
        """Return compact metadata and diagnostics summary without dense arrays."""
        return {
            "scenario_id": self.scenario_id,
            "config": self.config.to_dict(),
            "signal_shape": list(self.clean_signal.shape),
            "has_coordinates": self.original_coordinates is not None,
            "coordinate_shape": (
                list(self.original_coordinates.shape)
                if self.original_coordinates is not None
                else None
            ),
            "diagnostics": self.diagnostics.to_dict(),
        }

    def to_dict(self, include_arrays: bool = False) -> Dict[str, Any]:
        """Convert scenario result to a dictionary.

        Args:
            include_arrays: If True, dense signals and coordinates are converted
                to nested lists (suitable for JSON export of small fixtures).
                If False, only shape and summary statistics are included.

        Returns:
            Dictionary representation.
        """
        d = self.summary_dict()
        if include_arrays:
            d["clean_signal"] = self.clean_signal.tolist()
            d["noisy_signal"] = self.noisy_signal.tolist()
            d["scaled_noise"] = self.scaled_noise.tolist()
            if self.original_coordinates is not None:
                d["original_coordinates"] = self.original_coordinates.tolist()
            if self.jittered_coordinates is not None:
                d["jittered_coordinates"] = self.jittered_coordinates.tolist()
        return d

    def to_json(self, include_arrays: bool = False, indent: int = 2) -> str:
        """Serialize scenario result to JSON string."""
        return json.dumps(self.to_dict(include_arrays=include_arrays), indent=indent)
