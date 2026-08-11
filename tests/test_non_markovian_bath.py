import numpy as np
import pytest
from sim.pitnn.non_markovian_bath import (
    DrudeLorentzBath,
    MultiExponentialMemoryBath,
    OscillatoryMemoryBath,
    integrate_stable_observables,
    blp_measure,
)

def test_bath_spectrum_kernel_and_deterministic_noise():
    bath = DrudeLorentzBath(); frequencies = np.array([0.0, 1e12, 5e13])
    assert np.all(bath.spectral_density(frequencies) >= 0)
    assert np.isclose(bath.memory_kernel(1e-15), bath.memory_kernel(-1e-15))
    assert np.array_equal(bath.colored_noise(20, 1e-15, seed=2), bath.colored_noise(20, 1e-15, seed=2))

def test_blp_measure_only_counts_backflow():
    t = np.arange(4, dtype=float); assert blp_measure(np.array([1.0, .8, .9, .7]), t) == pytest.approx(.1)


def test_multi_exponential_kernel_is_positive_and_symmetric():
    bath = MultiExponentialMemoryBath(amplitudes_s2=(2.0, 1.0), memory_times_s=(1e-9, 3e-9))
    lags = np.array([-2e-9, 0.0, 2e-9])
    kernel = bath.memory_kernel(lags)
    assert np.all(kernel >= 0)
    assert np.isclose(kernel[0], kernel[2])


def test_oscillatory_kernel_can_change_sign_but_remains_finite():
    bath = OscillatoryMemoryBath(amplitude_s2=2.0, memory_time_s=1e-9, angular_frequency_s=np.pi / 1e-9)
    lags = np.array([0.0, 0.5e-9, 1e-9])
    kernel = bath.memory_kernel(lags)
    assert np.all(np.isfinite(kernel))
    assert kernel[0] >= kernel[1]


def test_stable_observables_accept_adaptive_grid():
    times = np.linspace(0.0, 1e-8, 101)
    kernel = np.exp(-times / 1e-9)
    observables = integrate_stable_observables(times, 1e8, kernel, dephasing_rate_s=1e7)
    assert observables["integrated_population"] > 0
    assert observables["integrated_coherence"] > 0
