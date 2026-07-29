import numpy as np
import pytest

from research_runtime.tsnr import bootstrap_mean, compute_tsnr, paired_effect, phase_randomize_timeseries


def test_phase_randomization_preserves_power_spectrum():
    t = np.linspace(0, 2 * np.pi, 128, endpoint=False)
    values = np.vstack([np.sin(3 * t) + 0.2 * np.sin(9 * t), np.cos(5 * t)])
    randomized = phase_randomize_timeseries(values, seed=7)
    assert np.allclose(np.abs(np.fft.rfft(values, axis=1)), np.abs(np.fft.rfft(randomized, axis=1)))


def test_paired_effect_is_reproducible():
    first = [1.2, 1.1, 1.4, 1.3, 1.5]
    second = [0.9, 1.0, 1.1, 1.0, 1.2]
    assert paired_effect(first, second, seed=4) == paired_effect(first, second, seed=4)


def test_tsnr_detects_effect_above_surrogate_scale():
    result = compute_tsnr(2.0, [0.1, 0.2, 0.15, 0.12], seed=2, draws=1000)
    assert result["tsnr"] > 10
    assert result["tsnr_bootstrap_lower"] > 0


def test_tsnr_rejects_zero_surrogate_scale():
    with pytest.raises(ValueError, match="zero scale"):
        compute_tsnr(1.0, [0.0, 0.0])


def test_bootstrap_interval_is_order_invariant():
    assert bootstrap_mean([1.0, 2.0, 3.0], seed=3, draws=100) == bootstrap_mean([3.0, 2.0, 1.0], seed=3, draws=100)
