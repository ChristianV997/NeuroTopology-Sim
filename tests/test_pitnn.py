"""Offline contract tests for the deterministic exploratory PITNN layer."""
import json
import numpy as np
import pytest

from run_pitnn import run_pipeline
from sim.pitnn.bayesian_falsification import compare_models
from sim.pitnn.mumax3_macro_tda import invert_macro_signal
from sim.pitnn.spirit_gneb_well import calculate_gneb_well
from sim.pitnn.vampire_os_llg import LLGConfig, OpenSystemLLGSimulator, simulate_os_llg


def test_llg_is_deterministic_and_normalized():
    a = simulate_os_llg(LLGConfig(n_spins=8, steps=10, seed=4))
    b = simulate_os_llg(LLGConfig(n_spins=8, steps=10, seed=4))
    assert a == b
    assert a["max_spin_norm_error"] < 1e-12
    assert np.isfinite(a["tau_eff_s"])


def test_gneb_outputs_barrier_and_flattening_proxy():
    result = calculate_gneb_well()
    flat = calculate_gneb_well(type("Cfg", (), {"n_images": 8, "defect_charge": 1, "curvature": 1.0, "meditative_flattening": 1.0, "metabolic_scale_W": 1e-12})())
    assert result["topological_barrier_eV"] == pytest.approx(0.55)
    assert flat["hessian_min_eigenvalue"] == 0.0


def test_bayes_gate_does_not_claim_success_for_constant_data():
    y = np.ones(32)
    result = compare_models(y, invert_macro_signal(y + np.linspace(0, 1e-6, 32)))
    assert result["verdict"] == "NOT_SUPPORTED"


def test_runner_writes_reproducible_contract(tmp_path):
    a = run_pipeline(output_dir=tmp_path / "a", n_samples=32, n_spins=6, steps=8)
    b = run_pipeline(output_dir=tmp_path / "b", n_samples=32, n_spins=6, steps=8)
    assert a == b
    record = json.loads((tmp_path / "a" / "RunRecord.json").read_text())
    assert record["run_kind"] == "pitnn"
    assert record["data_mode"] == "synthetic_demo"


def test_runner_fast_options_keep_synthetic_guardrail(tmp_path):
    result = run_pipeline(output_dir=tmp_path / "fast", n_samples=32, n_spins=8, steps=8,
                          advanced_biophysics=True, fast_backend=True, fast_tda=True,
                          mcwf_trajectories=4, fast_ep=True)
    assert result["verdict"] == "NOT_SUPPORTED"
    assert "advanced_biophysics" in result["metrics"]


def test_long_horizon_spinor_norm_stability():
    """Audit 100,000 explicit steps for finite state and bounded norm drift."""
    np.random.seed(42)
    sim = OpenSystemLLGSimulator(num_spins=100, alpha=0.01, dt=1e-15, temperature=310.0)
    h_ext = np.zeros((100, 3))
    drift_history = []
    for step in range(1, 100_001):
        sim.step(h_ext)
        if step % 10_000 == 0:
            assert np.all(np.isfinite(sim.S))
            drift = float(np.max(np.abs(np.linalg.norm(sim.S, axis=1) - 1.0)))
            drift_history.append(drift)
            assert drift < 1e-10
    assert drift_history[-1] < 1e-10


def test_integrator_raw_step_truncation_error():
    """Confirm the unprojected 1 fs update remains numerically bounded."""
    np.random.seed(42)
    sim = OpenSystemLLGSimulator(num_spins=100, alpha=0.01, dt=1e-15, temperature=310.0)
    h_ext = np.zeros((100, 3))
    h_eff = sim.compute_effective_field(h_ext)
    h_total = h_eff + sim.get_thermal_noise()
    factor = -1.76e11 / (1.0 + sim.alpha ** 2)
    precession = np.cross(sim.S, h_total)
    damping = np.cross(sim.S, precession)
    derivative = factor * (precession + sim.alpha * damping) + sim.get_ciss_torque()
    raw = sim.S + derivative * sim.dt
    assert float(np.max(np.abs(np.linalg.norm(raw, axis=1) - 1.0))) < 1e-4
