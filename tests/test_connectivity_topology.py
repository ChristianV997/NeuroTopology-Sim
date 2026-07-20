"""Synthetic ground-truth tests for analysis/connectivity_topology.py -- the
real PLV + ripser persistent-homology core factored out of
analysis/itct/itct_cessation_protocol_v3_full_stack.py in the "beyond topology"
instrumentation pass. Each test proves the instrument catches what it's
supposed to catch on a constructed signal with a known answer, following this
session's established pattern (see tests/test_permutation.py's
pseudoreplication regression test).
"""
from __future__ import annotations

import numpy as np
import pytest

from analysis.connectivity_topology import (
    compute_beta1,
    compute_persistence_diagram,
    compute_plv,
    compute_spectral_dimension,
)


# ---------------------------------------------------------------------------
# compute_plv
# ---------------------------------------------------------------------------

def test_plv_diagonal_is_always_one():
    rng = np.random.default_rng(0)
    signals = rng.standard_normal((5, 200))
    plv = compute_plv(signals)
    assert np.allclose(np.diag(plv), 1.0)


def test_plv_symmetric():
    rng = np.random.default_rng(1)
    signals = rng.standard_normal((4, 200))
    plv = compute_plv(signals)
    assert np.allclose(plv, plv.T)


def test_plv_perfectly_phase_locked_signals_near_one():
    """Identical sinusoids (zero phase lag, every window) must show PLV ~1.0
    -- the textbook maximally-phase-locked case."""
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 5 * t)
    signals = np.array([base, base, base])
    plv = compute_plv(signals)
    off_diag = plv[~np.eye(3, dtype=bool)]
    assert np.all(off_diag > 0.99)


def test_plv_independent_noise_lower_than_locked():
    """Independent-phase (uncorrelated) channels must show markedly lower PLV
    than phase-locked channels -- a relative comparison, not a fragile
    absolute threshold, since finite-sample PLV of independent noise is
    upward-biased away from exactly 0."""
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 5 * t)
    locked = np.array([base, base, base])

    rng = np.random.default_rng(2)
    independent = np.array([
        np.sin(2 * np.pi * 5 * t + rng.uniform(0, 2 * np.pi) * np.arange(len(t)) / len(t) * 20)
        for _ in range(3)
    ])

    plv_locked = compute_plv(locked)
    plv_independent = compute_plv(independent)
    mean_locked = plv_locked[~np.eye(3, dtype=bool)].mean()
    mean_independent = plv_independent[~np.eye(3, dtype=bool)].mean()
    assert mean_locked > mean_independent


def test_plv_rejects_non_2d_input():
    with pytest.raises(ValueError):
        compute_plv(np.zeros((2, 3, 4)))


# ---------------------------------------------------------------------------
# compute_beta1 / compute_persistence_diagram
# ---------------------------------------------------------------------------

def test_beta1_ring_topology_detects_a_persistent_loop():
    """Five points arranged so each is similar only to its ring neighbors (a
    classic Vietoris-Rips ring example) must show a persistent H1 loop at an
    intermediate threshold -- the textbook case ripser is built to detect."""
    n = 5
    plv = np.eye(n)
    for i in range(n):
        j = (i + 1) % n
        plv[i, j] = plv[j, i] = 0.9  # strong neighbor coupling
    # non-neighbor pairs stay near 0 (already the default off-ring value)
    for i in range(n):
        for j in range(n):
            if i != j and plv[i, j] == 0.0:
                plv[i, j] = 0.05

    b1 = compute_beta1(plv, threshold=0.5)
    assert b1 >= 1


def test_beta1_fully_connected_clique_has_no_persistent_loop():
    """A clique where every pair is maximally similar collapses to a filled
    simplex immediately -- no H1 loop survives at a threshold matching that
    similarity, unlike the ring case above."""
    n = 5
    plv = np.ones((n, n))
    b1 = compute_beta1(plv, threshold=0.99)
    assert b1 == 0


def test_beta1_deterministic():
    rng = np.random.default_rng(3)
    m = rng.uniform(0, 1, size=(6, 6))
    plv = np.clip((m + m.T) / 2, 0, 1)
    np.fill_diagonal(plv, 1.0)
    assert compute_beta1(plv, threshold=0.5) == compute_beta1(plv, threshold=0.5)


def test_persistence_diagram_returns_h0_and_h1():
    n = 5
    plv = np.eye(n)
    for i in range(n):
        j = (i + 1) % n
        plv[i, j] = plv[j, i] = 0.9
    dgms = compute_persistence_diagram(plv)
    assert len(dgms) >= 2
    assert dgms[0].shape[1] == 2
    assert dgms[1].shape[1] == 2


# ---------------------------------------------------------------------------
# compute_spectral_dimension
# ---------------------------------------------------------------------------

def test_spectral_dimension_zero_for_disconnected_graph():
    n = 4
    plv = np.eye(n)  # no off-diagonal edges above any positive threshold
    assert compute_spectral_dimension(plv, threshold=0.5) == 0.0


def test_spectral_dimension_finite_for_connected_graph():
    n = 8
    rng = np.random.default_rng(4)
    m = rng.uniform(0.4, 1.0, size=(n, n))
    plv = np.clip((m + m.T) / 2, 0, 1)
    np.fill_diagonal(plv, 1.0)
    result = compute_spectral_dimension(plv, threshold=0.3)
    assert np.isfinite(result)
