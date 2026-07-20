from __future__ import annotations
import numpy as np
import pytest
from core.topology import compute_Qz
from validation.synthetic import single_vortex, double_vortex, perturbed_vortex, validate_vortex_charges


def test_single_vortex_shape():
    psi = single_vortex(N=32)
    assert psi.shape == (32, 32, 32)


def test_double_vortex_shape():
    psi = double_vortex(N=32)
    assert psi.shape == (32, 32, 32)


def test_single_vortex_dtype():
    psi = single_vortex(N=8)
    assert np.issubdtype(psi.dtype, np.complexfloating)


def test_single_vortex_unit_amplitude():
    psi = single_vortex(N=8)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-10)


def test_double_vortex_unit_amplitude():
    psi = double_vortex(N=8)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-10)


def test_validate_vortex_charges_both_pass():
    result = validate_vortex_charges()
    assert result["single_vortex_pass"], (
        f"single-vortex failed: Q_mean={result['single_vortex_Q_mean']}"
    )
    assert result["double_vortex_pass"], (
        f"double-vortex failed: Q_mean={result['double_vortex_Q_mean']}"
    )


def test_validate_vortex_charges_values():
    result = validate_vortex_charges()
    assert result["single_vortex_Q_mean"] == pytest.approx(1.0, abs=0.25)
    assert result["double_vortex_Q_mean"] == pytest.approx(2.0, abs=0.25)


def test_validate_vortex_charges_keys():
    result = validate_vortex_charges()
    for key in (
        "single_vortex_Q_mean",
        "double_vortex_Q_mean",
        "single_vortex_pass",
        "double_vortex_pass",
    ):
        assert key in result


# ── perturbed_vortex (Phase 9: active-inference search target) ───────────────

def test_perturbed_vortex_zero_amplitude_matches_single_vortex_exactly():
    psi = perturbed_vortex(N=16, noise_amplitude=0.0, seed=0)
    reference = single_vortex(N=16)
    np.testing.assert_array_equal(psi, reference)


def test_perturbed_vortex_nonzero_amplitude_differs_from_single_vortex():
    psi = perturbed_vortex(N=16, noise_amplitude=1.0, seed=0)
    reference = single_vortex(N=16)
    assert not np.allclose(psi, reference)


def test_perturbed_vortex_stays_unit_amplitude():
    psi = perturbed_vortex(N=16, noise_amplitude=1.0, seed=0)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-8)


def test_perturbed_vortex_deterministic_given_seed():
    psi1 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=5)
    psi2 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=5)
    np.testing.assert_array_equal(psi1, psi2)


def test_perturbed_vortex_different_seeds_differ():
    psi1 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=1)
    psi2 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=2)
    assert not np.allclose(psi1, psi2)


def test_perturbed_vortex_charge_degrades_with_increasing_noise():
    """Winding charge must trend downward (toward 0) as noise_amplitude
    increases -- the whole premise `sim/active_inference.py`'s search relies
    on. Averaged over several seeds per amplitude to avoid single-draw noise."""
    def mean_qz(amplitude: float) -> float:
        vals = [
            float(np.mean(compute_Qz(perturbed_vortex(N=16, noise_amplitude=amplitude, seed=s))[0]))
            for s in range(8)
        ]
        return float(np.mean(vals))

    low = mean_qz(0.0)
    high = mean_qz(2.0)
    assert low > high
    assert low == pytest.approx(1.0, abs=0.05)
