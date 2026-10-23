"""Tests for NuisanceScenarioFactory, parameter grid generation, and serialization."""
from __future__ import annotations

import json
import numpy as np
import pytest

from sim.nuisance_scenarios.config import NuisanceGridConfig, NuisanceScenarioConfig
from sim.nuisance_scenarios.factory import (
    NuisanceScenarioFactory,
    generate_default_signal,
    generate_synthetic_spherical_coordinates,
)
from sim.nuisance_scenarios.models import ScenarioResult


def test_factory_generate_default() -> None:
    """Verifies factory generates a complete ScenarioResult using defaults."""
    cfg = NuisanceScenarioConfig(
        noise_exponent=1.0,
        target_snr_db=6.0,
        coordinate_jitter_std=2.0,
        coordinate_units="mm",
        renormalize_to_sphere=True,
        sfreq_hz=200.0,
        duration_s=1.0,
        n_channels=4,
        seed=42,
    )
    res = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")

    assert isinstance(res, ScenarioResult)
    assert res.scenario_id == cfg.scenario_id
    assert res.clean_signal.shape == (4, 200)
    assert res.noisy_signal.shape == (4, 200)
    assert res.scaled_noise.shape == (4, 200)
    assert res.original_coordinates is not None
    assert res.jittered_coordinates is not None
    assert res.original_coordinates.shape == (4, 3)
    assert res.jittered_coordinates.shape == (4, 3)

    assert res.diagnostics.status == "HOLD / SYNTHETIC_ONLY"
    assert res.diagnostics.realized_snr_db == pytest.approx(6.0, abs=1e-5)
    assert res.diagnostics.renormalize_to_sphere is True
    assert res.diagnostics.is_finite is True


@pytest.mark.parametrize("n_points", [2.5, True])
def test_synthetic_coordinate_generator_rejects_noninteger_count(n_points: object) -> None:
    with pytest.raises(ValueError, match="n_points"):
        generate_synthetic_spherical_coordinates(n_points=n_points)


@pytest.mark.parametrize("radius", [True, float("nan"), 10**400])
def test_synthetic_coordinate_generator_rejects_invalid_radius(radius: object) -> None:
    with pytest.raises(ValueError, match="radius"):
        generate_synthetic_spherical_coordinates(n_points=4, radius=radius)


@pytest.mark.parametrize(
    ("n_channels", "n_samples", "sampling_rate_hz"),
    [
        (True, 16, 100.0),
        (2, 4.5, 100.0),
        (2, 16, True),
        (2, 16, float("nan")),
        (2, 16, 10**400),
    ],
)
def test_default_signal_generator_rejects_invalid_numeric_inputs(
    n_channels: object, n_samples: object, sampling_rate_hz: object
) -> None:
    with pytest.raises(ValueError):
        generate_default_signal(
            n_channels=n_channels,
            n_samples=n_samples,
            sampling_rate_hz=sampling_rate_hz,
        )


def test_factory_with_custom_clean_signal() -> None:
    """Verifies factory accepts an external clean signal array."""
    cfg = NuisanceScenarioConfig(
        noise_exponent=0.5,
        target_snr_db=10.0,
        coordinate_jitter_std=0.0,
        sfreq_hz=100.0,
        duration_s=1.0,
        n_channels=2,
    )
    t = np.linspace(0, 1, 100, endpoint=False)
    custom_signal = np.vstack([np.sin(2 * np.pi * 5 * t), np.cos(2 * np.pi * 5 * t)])

    res = NuisanceScenarioFactory.generate(cfg, clean_signal=custom_signal)
    np.testing.assert_array_equal(res.clean_signal, custom_signal)
    assert res.diagnostics.realized_snr_db == pytest.approx(10.0, abs=1e-5)


def test_factory_with_signal_generator_callable() -> None:
    """Verifies factory accepts a custom signal generator callable."""
    cfg = NuisanceScenarioConfig(
        noise_exponent=1.0,
        target_snr_db=3.0,
        sfreq_hz=250.0,
        duration_s=2.0,
        n_channels=8,
    )

    def custom_generator(n_ch: int, n_samp: int, sfreq: float, rng: np.random.Generator) -> np.ndarray:
        # Generates deterministic pulses
        sig = np.zeros((n_ch, n_samp))
        sig[:, ::50] = 5.0
        return sig

    res = NuisanceScenarioFactory.generate(cfg, signal_generator=custom_generator)
    assert res.clean_signal.shape == (8, 500)
    assert res.diagnostics.realized_snr_db == pytest.approx(3.0, abs=1e-5)


def test_factory_grid_generation() -> None:
    """Verifies multi-dimensional parameter grid generation."""
    grid = NuisanceGridConfig(
        chi_values=[0.0, 1.5],
        snr_db_values=[-6.0, 12.0],
        jitter_std_values=[0.0, 3.0],
        seeds=[42],
        renormalize_options=[False, True],
        sfreq_hz=100.0,
        duration_s=1.0,
        n_channels=4,
    )
    # Expected size: 2 * 2 * 2 * 1 * 2 = 16 scenarios
    results = NuisanceScenarioFactory.generate_grid(grid, coordinates="synthetic_sphere")
    assert len(results) == 16

    # Verify scenario IDs are unique
    ids = [r.scenario_id for r in results]
    assert len(set(ids)) == 16


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("noise_exponent", 1.001),
        ("target_snr_db", 0.04),
        ("sfreq_hz", 101.0),
        ("duration_s", 2.01),
        ("n_channels", 5),
    ],
)
def test_generated_scenario_ids_distinguish_configuration_values(
    field: str, value: object
) -> None:
    base = NuisanceScenarioConfig()
    changed = NuisanceScenarioConfig(**{field: value})

    assert base.scenario_id != changed.scenario_id


def test_serialization_to_dict_and_json() -> None:
    """Verifies summary_dict, to_dict, and to_json serialization formats."""
    cfg = NuisanceScenarioConfig(
        noise_exponent=1.0,
        target_snr_db=0.0,
        coordinate_jitter_std=1.0,
        sfreq_hz=100.0,
        duration_s=0.5,
        n_channels=2,
    )
    res = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")

    # 1. Summary dict (compact)
    summary = res.summary_dict()
    assert summary["scenario_id"] == cfg.scenario_id
    assert summary["signal_shape"] == [2, 50]
    assert "clean_signal" not in summary
    assert summary["diagnostics"]["status"] == "HOLD / SYNTHETIC_ONLY"

    # 2. JSON without arrays
    json_compact = res.to_json(include_arrays=False)
    parsed_compact = json.loads(json_compact)
    assert parsed_compact["scenario_id"] == cfg.scenario_id
    assert "clean_signal" not in parsed_compact

    # 3. JSON with arrays
    json_full = res.to_json(include_arrays=True)
    parsed_full = json.loads(json_full)
    assert "clean_signal" in parsed_full
    assert len(parsed_full["clean_signal"]) == 2
    assert len(parsed_full["clean_signal"][0]) == 50


def test_factory_error_handling() -> None:
    """Verifies factory fails fast on invalid input signals or coordinates."""
    cfg = NuisanceScenarioConfig(n_channels=4, sfreq_hz=100.0, duration_s=1.0)  # expects 100 samples

    # Wrong channel count
    with pytest.raises(ValueError, match="does not match config"):
        NuisanceScenarioFactory.generate(cfg, clean_signal=np.ones((2, 100)))

    # Wrong sample count
    with pytest.raises(ValueError, match="does not match config"):
        NuisanceScenarioFactory.generate(cfg, clean_signal=np.ones((4, 50)))

    # Wrong coordinate shape
    with pytest.raises(ValueError, match="coordinates must have shape"):
        NuisanceScenarioFactory.generate(cfg, coordinates=np.ones((4, 4)))

    # Callable returning wrong shape
    with pytest.raises(ValueError, match="signal_generator returned shape"):
        NuisanceScenarioFactory.generate(
            cfg, signal_generator=lambda n_ch, n_samp, sf, rng: np.zeros((2, 2))
        )
