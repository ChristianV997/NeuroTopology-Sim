"""Smoke + ground-truth tests for the README-documented "Unified Quantum +
EEG Topology Pipeline" modules.

Found during a repo-wide audit: `sim/quantum_lattice/
unified_frohlich_dp_active_inference_tda_entropy.py` and
`analysis/eeg_topology/unified_sim_to_eeg_mapper.py` were referenced by the
top-level README with specific quantitative claims but had ZERO test
coverage -- not even a smoke test confirming they run without crashing. Two
real crash bugs were in fact latent: a missing `scipy.spatial.distance`
import (NameError on the first TDA checkpoint) and a `qt.mesolve(...)`
positional-arg call that raised TypeError under the installed qutip version.
Both fixed; these tests lock in that they stay runnable and that their
verifiable numeric properties hold.

These deliberately test bounded/structural properties (coherence in range,
pump-rate clipping, output keys/shapes), NOT the README's higher-level
qualitative claims ("clear Fröhlich threshold", etc.) which would need a
full multi-hundred-step run and are outside a unit test's remit.
"""
from __future__ import annotations

import numpy as np
import pytest

from analysis.eeg_topology.unified_sim_to_eeg_mapper import (
    ActiveInferenceController,
    mapper_graph,
    run_simulator,
    time_delay_embedding,
)
from sim.quantum_lattice.unified_frohlich_dp_active_inference_tda_entropy import (
    run_unified_with_entropy,
)


# ── ActiveInferenceController: exact, deterministic ──────────────────────────

def test_controller_cost_is_deterministic_linear_combination():
    c = ActiveInferenceController()
    assert c.compute_cost(2.0, 3.0) == pytest.approx(2.0 + 0.6 * 3.0)


def test_controller_pump_rate_clipped_to_valid_range():
    c = ActiveInferenceController()
    # Extreme costs must clip into the documented [0.08, 0.85] actuator range,
    # never run away unbounded.
    assert 0.08 <= c.suggest_pump_rate(1e6) <= 0.85
    assert 0.08 <= c.suggest_pump_rate(-1e6) <= 0.85


# ── run_simulator (qutip Lindblad sim) ───────────────────────────────────────

def test_run_simulator_returns_bounded_coherence():
    sig = run_simulator(N=3, steps=8, dt=0.06)
    assert sig.ndim == 1
    assert len(sig) >= 1
    # coherence is mean over sites of |<sigma_x>|, so must lie in [0, 1].
    assert np.all(sig >= 0.0)
    assert np.all(sig <= 1.0 + 1e-9)


def test_run_simulator_is_finite():
    sig = run_simulator(N=3, steps=8, dt=0.06)
    assert np.all(np.isfinite(sig))


# ── time_delay_embedding ─────────────────────────────────────────────────────

def test_time_delay_embedding_shape():
    sig = np.arange(20, dtype=float)
    emb = time_delay_embedding(sig, emb_dim=3, delay=2)
    assert emb.shape == (20 - (3 - 1) * 2, 3)


def test_time_delay_embedding_columns_are_lagged_copies():
    sig = np.arange(10, dtype=float)
    emb = time_delay_embedding(sig, emb_dim=2, delay=1)
    # column i is the signal shifted by i*delay
    np.testing.assert_array_equal(emb[:, 0], sig[0 : emb.shape[0]])
    np.testing.assert_array_equal(emb[:, 1], sig[1 : 1 + emb.shape[0]])


# ── mapper_graph guard path ──────────────────────────────────────────────────

def test_mapper_graph_small_input_guard():
    """<20 points must hit the documented guard and return an empty graph,
    not attempt a TSNE fit that would raise on too few samples."""
    cloud = np.random.default_rng(0).standard_normal((5, 3))
    assert mapper_graph(cloud) == {"nodes": 0, "links": 0}


# ── run_unified_with_entropy (full stack, tiny run) ──────────────────────────

def test_run_unified_with_entropy_runs_and_returns_expected_keys():
    result = run_unified_with_entropy(N=3, steps=6, dt=0.06, tda_interval=2)
    for key in ("time", "coherence", "beta1", "Q_abs", "pump_rate", "entropy_prod"):
        assert key in result
        assert isinstance(result[key], np.ndarray)


def test_run_unified_with_entropy_entropy_production_nonnegative():
    """Entropy production is clipped to max(0, sigma) in the code -- a
    thermodynamic sanity constraint that must hold for every checkpoint."""
    result = run_unified_with_entropy(N=3, steps=6, dt=0.06, tda_interval=2)
    assert np.all(result["entropy_prod"] >= 0.0)


def test_run_unified_with_entropy_coherence_bounded():
    result = run_unified_with_entropy(N=3, steps=6, dt=0.06, tda_interval=2)
    assert np.all(result["coherence"] >= 0.0)
    assert np.all(result["coherence"] <= 1.0 + 1e-9)
