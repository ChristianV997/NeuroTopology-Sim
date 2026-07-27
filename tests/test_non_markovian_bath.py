import numpy as np
import pytest
from sim.pitnn.non_markovian_bath import DrudeLorentzBath, blp_measure

def test_bath_spectrum_kernel_and_deterministic_noise():
    bath = DrudeLorentzBath(); frequencies = np.array([0.0, 1e12, 5e13])
    assert np.all(bath.spectral_density(frequencies) >= 0)
    assert np.isclose(bath.memory_kernel(1e-15), bath.memory_kernel(-1e-15))
    assert np.array_equal(bath.colored_noise(20, 1e-15, seed=2), bath.colored_noise(20, 1e-15, seed=2))

def test_blp_measure_only_counts_backflow():
    t = np.arange(4, dtype=float); assert blp_measure(np.array([1.0, .8, .9, .7]), t) == pytest.approx(.1)
