"""Tests for `sim/speculative/langevin_lattice.py` -- offline, no network.

Synthetic ground-truth pattern: fractional noise generation is validated
against an independent DFA (antropy) recovery of the requested Hurst
exponent, the same discipline used for this repo's DFA/MFDFA ground-truth
tests (`tests/btc_icft/test_dfa_mfdfa_features.py`).
"""
from __future__ import annotations

import numpy as np
import pytest

from sim.speculative import SPECULATIVE_BANNER
from sim.speculative.langevin_lattice import (
    LangevinLatticeResult,
    _generate_noise,
    build_speculative_report,
    run_langevin_lattice,
)


# ── run_langevin_lattice: basic shape/telemetry correctness ─────────────────

def test_run_returns_result_dataclass():
    result = run_langevin_lattice(N=8, n_steps=5, seed=0)
    assert isinstance(result, LangevinLatticeResult)


def test_run_steps_length_matches_n_steps():
    result = run_langevin_lattice(N=8, n_steps=7, seed=0)
    assert len(result.steps) == 7


def test_run_final_field_shape_matches_grid():
    result = run_langevin_lattice(N=10, n_steps=5, seed=0)
    assert result.final_field.shape == (10, 10)


def test_run_final_field_is_finite():
    result = run_langevin_lattice(N=8, n_steps=20, seed=0)
    assert np.all(np.isfinite(result.final_field))


def test_run_step_telemetry_has_expected_keys():
    result = run_langevin_lattice(N=8, n_steps=5, seed=0)
    for s in result.steps:
        assert {"step", "mean", "std", "energy"}.issubset(s.keys())


def test_run_rejects_unknown_noise_mode():
    with pytest.raises(ValueError):
        run_langevin_lattice(N=8, n_steps=5, noise_mode="not_a_real_mode")


def test_run_deterministic_given_seed():
    r1 = run_langevin_lattice(N=8, n_steps=10, seed=42)
    r2 = run_langevin_lattice(N=8, n_steps=10, seed=42)
    np.testing.assert_array_equal(r1.final_field, r2.final_field)


def test_run_different_seeds_differ():
    r1 = run_langevin_lattice(N=8, n_steps=10, seed=1)
    r2 = run_langevin_lattice(N=8, n_steps=10, seed=2)
    assert not np.allclose(r1.final_field, r2.final_field)


def test_run_params_recorded():
    result = run_langevin_lattice(N=8, n_steps=5, noise_mode="fractional", hurst=0.3, seed=0)
    assert result.params["noise_mode"] == "fractional"
    assert result.params["hurst"] == 0.3


def test_run_damping_reduces_field_energy_over_time_with_zero_noise():
    """With noise_amplitude=0, pure damped diffusion must monotonically
    dissipate energy from its initial random field -- a basic sanity check
    on the deterministic (drift-only) part of the update."""
    result = run_langevin_lattice(N=16, n_steps=30, noise_amplitude=0.0, damping=0.5, seed=0)
    energies = [s["energy"] for s in result.steps]
    assert energies[-1] < energies[0]


# ── _generate_noise: white vs fractional ─────────────────────────────────────

def test_generate_noise_white_shape():
    noise = _generate_noise(n_steps=10, N=4, noise_mode="white", hurst=0.5, seed=0)
    assert noise.shape == (10, 4, 4)


def test_generate_noise_fractional_shape():
    noise = _generate_noise(n_steps=10, N=4, noise_mode="fractional", hurst=0.7, seed=0)
    assert noise.shape == (10, 4, 4)


def test_generate_noise_rejects_unknown_mode():
    with pytest.raises(ValueError):
        _generate_noise(n_steps=10, N=4, noise_mode="bogus", hurst=0.5, seed=0)


def test_generate_noise_fractional_deterministic_given_seed():
    n1 = _generate_noise(n_steps=20, N=3, noise_mode="fractional", hurst=0.6, seed=7)
    n2 = _generate_noise(n_steps=20, N=3, noise_mode="fractional", hurst=0.6, seed=7)
    np.testing.assert_array_equal(n1, n2)


def test_generate_noise_fractional_does_not_mutate_global_random_state():
    """The fbm library only supports global-state seeding; the generator
    must save/restore np.random's global state so it doesn't leak into
    unrelated code that also uses np.random."""
    np.random.seed(12345)
    state_before = np.random.get_state()
    _generate_noise(n_steps=10, N=4, noise_mode="fractional", hurst=0.5, seed=0)
    state_after = np.random.get_state()
    assert state_before[1].tolist() == state_after[1].tolist()
    assert state_before[2] == state_after[2]


def test_generate_noise_fractional_hurst_recovered_by_dfa():
    """Ground-truth check: DFA (antropy) applied directly to a single grid
    point's fGn time series must recover something close to the requested
    Hurst exponent -- proving this is real fractional noise with the
    requested long-range correlation structure, not disguised white noise."""
    import antropy as ant

    for H in (0.2, 0.5, 0.8):
        noise = _generate_noise(n_steps=3000, N=2, noise_mode="fractional", hurst=H, seed=0)
        series = np.ascontiguousarray(noise[:, 0, 0], dtype=np.float64)
        dfa_h = ant.detrended_fluctuation(series)
        assert dfa_h == pytest.approx(H, abs=0.15), f"H={H}: DFA recovered {dfa_h}"


def test_generate_noise_fractional_differs_across_grid_points():
    """Each grid point must get its own independent fGn draw, not the same
    series broadcast across space."""
    noise = _generate_noise(n_steps=50, N=4, noise_mode="fractional", hurst=0.7, seed=0)
    assert not np.allclose(noise[:, 0, 0], noise[:, 1, 1])


# ── build_speculative_report: banner + guardrail enforcement ────────────────

def test_build_speculative_report_contains_banner():
    result = run_langevin_lattice(N=8, n_steps=5, seed=0)
    report = build_speculative_report(result)
    assert SPECULATIVE_BANNER in report


def test_build_speculative_report_is_valid_per_validate_speculative_text():
    from sim.speculative import validate_speculative_text

    result = run_langevin_lattice(N=8, n_steps=5, seed=0)
    report = build_speculative_report(result)
    validate_speculative_text(report)  # must not raise
