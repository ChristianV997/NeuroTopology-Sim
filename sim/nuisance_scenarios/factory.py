"""Reproducible nuisance scenario factory for synthetic operating-characteristic studies.

Assembles controlled colored noise, target SNR mixing, and electrode coordinate jitter
into fully-audited ScenarioResult bundles with deterministic seeding.
Adheres strictly to 'HOLD / SYNTHETIC_ONLY' and pure NumPy implementation.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Union

import numpy as np

from sim.nuisance_scenarios.colored_noise import (
    estimate_spectral_slope,
    generate_colored_noise,
)
from sim.nuisance_scenarios.config import NuisanceGridConfig, NuisanceScenarioConfig
from sim.nuisance_scenarios.jitter import apply_coordinate_jitter
from sim.nuisance_scenarios.models import RealizedDiagnostics, ScenarioResult
from sim.nuisance_scenarios.snr_mixer import mix_at_target_snr


def generate_synthetic_spherical_coordinates(
    n_points: int,
    radius: float = 100.0,
) -> np.ndarray:
    """Generate deterministic synthetic electrode coordinates on a sphere via Fibonacci spiral.

    Args:
        n_points: Number of points (electrodes).
        radius: Sphere radius in declared units (default 100.0 for mm).

    Returns:
        Array of shape (n_points, 3) with Cartesian coordinates strictly on sphere shell.
    """
    if n_points <= 0:
        raise ValueError(f"n_points must be positive, got {n_points}")
    if radius <= 0.0 or not np.isfinite(radius):
        raise ValueError(f"radius must be positive and finite, got {radius}")

    indices = np.arange(n_points, dtype=np.float64) + 0.5
    phi = np.arccos(1.0 - 2.0 * indices / n_points)
    golden_ratio = (1.0 + np.sqrt(5.0)) / 2.0
    theta = 2.0 * np.pi * indices / golden_ratio

    x = radius * np.sin(phi) * np.cos(theta)
    y = radius * np.sin(phi) * np.sin(theta)
    z = radius * np.cos(phi)
    return np.column_stack([x, y, z])


def generate_default_signal(
    n_channels: int,
    n_samples: int,
    sampling_rate_hz: float,
) -> np.ndarray:
    """Generate deterministic multi-frequency synthetic signals with channel phase shifts.

    Produces a composite signal composed of 10 Hz and 20 Hz components with progressive
    phase offsets across channels. Global power is strictly positive.

    Args:
        n_channels: Number of channels.
        n_samples: Number of time samples.
        sampling_rate_hz: Sampling rate in Hz.

    Returns:
        Array of shape (n_channels, n_samples) with non-zero mean-squared power.
    """
    if n_channels <= 0:
        raise ValueError(f"n_channels must be positive, got {n_channels}")
    if n_samples <= 0:
        raise ValueError(f"n_samples must be positive, got {n_samples}")
    if sampling_rate_hz <= 0.0:
        raise ValueError(f"sampling_rate_hz must be positive, got {sampling_rate_hz}")

    t = np.arange(n_samples, dtype=np.float64) / sampling_rate_hz
    phases = np.linspace(0.0, 2.0 * np.pi, n_channels, endpoint=False)[:, np.newaxis]
    sig = np.sin(2.0 * np.pi * 10.0 * t + phases) + 0.5 * np.cos(
        2.0 * np.pi * 20.0 * t + 2.0 * phases
    )
    return sig


class NuisanceScenarioFactory:
    """Factory for generating synthetic nuisance scenarios under explicit seed control."""

    @staticmethod
    def generate(
        config: NuisanceScenarioConfig,
        clean_signal: Optional[np.ndarray] = None,
        coordinates: Optional[Union[np.ndarray, str]] = None,
        signal_generator: Optional[
            Callable[[int, int, float, np.random.Generator], np.ndarray]
        ] = None,
    ) -> ScenarioResult:
        """Generate a single scenario result from configuration.

        Args:
            config: NuisanceScenarioConfig specifying parameters and seed.
            clean_signal: Optional pre-existing clean signal array of shape (n_channels, n_samples).
            coordinates: Optional electrode coordinates array of shape (n_channels, 3),
                or the string "synthetic_sphere" / "sphere" to automatically generate
                Fibonacci spherical layout.
            signal_generator: Optional callable(n_channels, n_samples, sampling_rate_hz, rng)
                returning clean signal array of shape (n_channels, n_samples).

        Returns:
            ScenarioResult bundle with clean, noisy, and noise signals, coordinates,
            and realized statistical diagnostics.
        """
        # Independent seed sequences for signal, noise, and jitter
        ss = np.random.SeedSequence(config.seed)
        sig_ss, noise_ss, jitter_ss = ss.spawn(3)
        sig_rng = np.random.default_rng(sig_ss)
        noise_rng = np.random.default_rng(noise_ss)
        jitter_rng = np.random.default_rng(jitter_ss)

        # 1. Resolve clean signal
        if clean_signal is not None:
            clean = np.asarray(clean_signal, dtype=np.float64)
            if clean.ndim != 2:
                raise ValueError(
                    f"clean_signal must be 2D of shape (n_channels, n_samples), got {clean.shape}"
                )
            if clean.shape[0] != config.n_channels or clean.shape[1] != config.n_samples:
                raise ValueError(
                    f"clean_signal shape {clean.shape} does not match config "
                    f"({config.n_channels}, {config.n_samples})"
                )
            if not np.all(np.isfinite(clean)):
                raise ValueError("clean_signal contains NaN or infinite values")
        elif signal_generator is not None:
            clean = np.asarray(
                signal_generator(
                    config.n_channels,
                    config.n_samples,
                    config.sampling_rate_hz,
                    sig_rng,
                ),
                dtype=np.float64,
            )
            if clean.shape != (config.n_channels, config.n_samples):
                raise ValueError(
                    f"signal_generator returned shape {clean.shape}, expected "
                    f"({config.n_channels}, {config.n_samples})"
                )
            if not np.all(np.isfinite(clean)):
                raise ValueError("signal_generator returned NaN or infinite values")
        else:
            clean = generate_default_signal(
                config.n_channels, config.n_samples, config.sampling_rate_hz
            )

        # 2. Generate raw colored noise
        raw_noise = generate_colored_noise(
            n_channels=config.n_channels,
            n_samples=config.n_samples,
            chi=config.chi,
            sampling_rate_hz=config.sampling_rate_hz,
            rng=noise_rng,
        )

        # 3. Estimate spectral slope
        slope_fit = estimate_spectral_slope(raw_noise, config.sampling_rate_hz)

        # 4. Mix signal and noise at target SNR
        mix_res = mix_at_target_snr(
            clean_signal=clean,
            noise=raw_noise,
            target_snr_db=config.target_snr_db,
        )

        # 5. Handle coordinates
        orig_coords: Optional[np.ndarray] = None
        jittered_coords: Optional[np.ndarray] = None
        mean_disp = 0.0
        max_disp = 0.0
        rms_disp = 0.0

        if isinstance(coordinates, str) and coordinates.lower() in ("sphere", "synthetic_sphere"):
            units = str(config.jitter_units).strip().lower()
            if units == "mm":
                radius = 100.0
            elif units == "cm":
                radius = 10.0
            elif units == "m":
                radius = 0.1
            else:
                raise ValueError(
                    f"unsupported coordinate units for synthetic_sphere: {config.jitter_units!r}"
                )
            orig_coords = generate_synthetic_spherical_coordinates(config.n_channels, radius=radius)
        elif coordinates is not None:
            orig_coords = np.asarray(coordinates, dtype=np.float64)
            if orig_coords.ndim != 2 or orig_coords.shape != (config.n_channels, 3):
                raise ValueError(
                    f"coordinates must have shape ({config.n_channels}, 3), got {orig_coords.shape}"
                )
            if not np.all(np.isfinite(orig_coords)):
                raise ValueError("coordinates contain NaN or infinite values")

        if orig_coords is not None:
            j_res = apply_coordinate_jitter(
                coords=orig_coords,
                jitter_std=config.jitter_std,
                rng=jitter_rng,
                renormalize_to_sphere=config.renormalize_to_sphere,
                units=config.jitter_units,
            )
            jittered_coords = j_res.jittered_coords
            mean_disp = j_res.mean_displacement
            max_disp = j_res.max_displacement
            rms_disp = j_res.rms_displacement

        # 6. Verify finiteness
        is_finite = bool(
            np.all(np.isfinite(clean))
            and np.all(np.isfinite(mix_res.noisy_signal))
            and np.all(np.isfinite(mix_res.scaled_noise))
            and (orig_coords is None or np.all(np.isfinite(orig_coords)))
            and (jittered_coords is None or np.all(np.isfinite(jittered_coords)))
        )

        diagnostics = RealizedDiagnostics(
            realized_snr_db=mix_res.realized_snr_db,
            clean_signal_power=mix_res.clean_signal_power,
            noise_power_before_scaling=mix_res.noise_power_before_scaling,
            noise_power_scaled=mix_res.noise_power_scaled,
            noise_scale_factor=mix_res.noise_scale_factor,
            estimated_chi=slope_fit.estimated_chi,
            chi_fit_r2=slope_fit.fit_r2,
            jitter_mean_disp=mean_disp,
            jitter_max_disp=max_disp,
            jitter_rms_disp=rms_disp,
            jitter_units=config.jitter_units,
            renormalize_to_sphere=config.renormalize_to_sphere,
            is_finite=is_finite,
            status="HOLD / SYNTHETIC_ONLY",
        )

        return ScenarioResult(
            scenario_id=config.scenario_id,
            config=config,
            clean_signal=clean,
            noisy_signal=mix_res.noisy_signal,
            scaled_noise=mix_res.scaled_noise,
            original_coordinates=orig_coords,
            jittered_coordinates=jittered_coords,
            diagnostics=diagnostics,
        )

    @classmethod
    def generate_grid(
        cls,
        grid_config: NuisanceGridConfig,
        clean_signal: Optional[np.ndarray] = None,
        coordinates: Optional[Union[np.ndarray, str]] = None,
        signal_generator: Optional[
            Callable[[int, int, float, np.random.Generator], np.ndarray]
        ] = None,
    ) -> List[ScenarioResult]:
        """Generate a list of ScenarioResults across a parameter grid.

        Args:
            grid_config: NuisanceGridConfig defining parameter sweep.
            clean_signal: Optional clean signal shared across scenarios.
            coordinates: Optional coordinates shared across scenarios.
            signal_generator: Optional callable generator.

        Returns:
            List of ScenarioResult bundles.
        """
        results: List[ScenarioResult] = []
        for cfg in grid_config.scenarios():
            res = cls.generate(
                config=cfg,
                clean_signal=clean_signal,
                coordinates=coordinates,
                signal_generator=signal_generator,
            )
            results.append(res)
        return results
