"""Tests for bit-for-bit seed reproducibility and RNG isolation."""
from __future__ import annotations

import numpy as np
import pytest

from sim.nuisance_scenarios.colored_noise import generate_colored_noise
from sim.nuisance_scenarios.config import NuisanceScenarioConfig
from sim.nuisance_scenarios.factory import (
    NuisanceScenarioFactory,
    generate_synthetic_spherical_coordinates,
)
from sim.nuisance_scenarios.jitter import apply_coordinate_jitter


def test_seed_bit_for_bit_reproducibility() -> None:
    """Verifies that running the factory twice with the same seed yields bit-for-bit identical arrays."""
    cfg = NuisanceScenarioConfig(
        noise_exponent=1.0,
        target_snr_db=5.0,
        coordinate_jitter_std=2.0,
        coordinate_units="mm",
        seed=12345,
    )
    res1 = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")
    res2 = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")

    np.testing.assert_array_equal(res1.clean_signal, res2.clean_signal)
    np.testing.assert_array_equal(res1.noisy_signal, res2.noisy_signal)
    np.testing.assert_array_equal(res1.scaled_noise, res2.scaled_noise)
    assert res1.original_coordinates is not None and res2.original_coordinates is not None
    assert res1.jittered_coordinates is not None and res2.jittered_coordinates is not None
    np.testing.assert_array_equal(res1.original_coordinates, res2.original_coordinates)
    np.testing.assert_array_equal(res1.jittered_coordinates, res2.jittered_coordinates)

    assert res1.scenario_id == res2.scenario_id
    assert res1.diagnostics.realized_snr_db == pytest.approx(res2.diagnostics.realized_snr_db, abs=1e-12)
    assert res1.diagnostics.jitter_mean_disp == pytest.approx(res2.diagnostics.jitter_mean_disp, abs=1e-12)


def test_different_seeds_yield_different_realizations() -> None:
    """Verifies that different seeds yield distinct noise and coordinate realizations."""
    cfg1 = NuisanceScenarioConfig(noise_exponent=1.0, target_snr_db=0.0, coordinate_jitter_std=2.0, seed=111)
    cfg2 = NuisanceScenarioConfig(noise_exponent=1.0, target_snr_db=0.0, coordinate_jitter_std=2.0, seed=222)

    res1 = NuisanceScenarioFactory.generate(cfg1, coordinates="synthetic_sphere")
    res2 = NuisanceScenarioFactory.generate(cfg2, coordinates="synthetic_sphere")

    assert not np.array_equal(res1.noisy_signal, res2.noisy_signal)
    assert not np.array_equal(res1.scaled_noise, res2.scaled_noise)
    assert not np.array_equal(res1.jittered_coordinates, res2.jittered_coordinates)


def test_independent_sub_generators() -> None:
    """Verifies that noise generation is independent of whether coordinates are provided."""
    cfg = NuisanceScenarioConfig(noise_exponent=1.0, target_snr_db=6.0, coordinate_jitter_std=1.5, seed=999)

    res_no_coords = NuisanceScenarioFactory.generate(cfg, coordinates=None)
    res_with_coords = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")

    # Noise and noisy signals must be bit-for-bit identical regardless of coordinates
    np.testing.assert_array_equal(res_no_coords.scaled_noise, res_with_coords.scaled_noise)
    np.testing.assert_array_equal(res_no_coords.noisy_signal, res_with_coords.noisy_signal)
    np.testing.assert_array_equal(res_no_coords.clean_signal, res_with_coords.clean_signal)


def test_low_level_colored_noise_seed_reproducibility() -> None:
    """Verifies low-level generate_colored_noise produces identical arrays with identical seed."""
    noise1 = generate_colored_noise(n_samples=500, chi=1.5, n_channels=4, sfreq_hz=250.0, seed=777)
    noise2 = generate_colored_noise(n_samples=500, chi=1.5, n_channels=4, sfreq_hz=250.0, seed=777)
    noise3 = generate_colored_noise(n_samples=500, chi=1.5, n_channels=4, sfreq_hz=250.0, seed=888)

    np.testing.assert_array_equal(noise1, noise2)
    assert not np.array_equal(noise1, noise3)


def test_low_level_jitter_seed_reproducibility() -> None:
    """Verifies low-level apply_coordinate_jitter produces identical arrays with identical seed."""
    coords = generate_synthetic_spherical_coordinates(n_points=16, radius=100.0)
    jit1 = apply_coordinate_jitter(coords, jitter_std=3.0, seed=54321)
    jit2 = apply_coordinate_jitter(coords, jitter_std=3.0, seed=54321)
    jit3 = apply_coordinate_jitter(coords, jitter_std=3.0, seed=98765)

    np.testing.assert_array_equal(jit1.jittered_coordinates, jit2.jittered_coordinates)
    assert not np.array_equal(jit1.jittered_coordinates, jit3.jittered_coordinates)
