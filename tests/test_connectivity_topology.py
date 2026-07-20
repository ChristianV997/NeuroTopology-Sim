"""Synthetic ground-truth tests for analysis/connectivity_topology.py -- the
real PLV + ripser persistent-homology core factored out of
analysis/itct/itct_cessation_protocol_v3_full_stack.py in the "beyond topology"
instrumentation pass. Each test proves the instrument catches what it's
supposed to catch on a constructed signal with a known answer, following this
session's established pattern (see tests/test_permutation.py's
pseudoreplication regression test).
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from analysis.connectivity_topology import (
    compute_beta1,
    compute_granger_causality,
    compute_granger_causality_matrix,
    compute_persistence_diagram,
    compute_pli,
    compute_plv,
    compute_spectral_dimension,
    compute_wpli,
)

_HAVE_MNE_CONNECTIVITY = importlib.util.find_spec("mne_connectivity") is not None


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


# ---------------------------------------------------------------------------
# compute_pli
# ---------------------------------------------------------------------------

def test_pli_diagonal_is_one_by_convention():
    rng = np.random.default_rng(5)
    signals = rng.standard_normal((4, 300))
    pli = compute_pli(signals)
    assert np.allclose(np.diag(pli), 1.0)


def test_pli_symmetric():
    rng = np.random.default_rng(6)
    signals = rng.standard_normal((4, 300))
    pli = compute_pli(signals)
    assert np.allclose(pli, pli.T)


def test_pli_zero_for_zero_lag_coupling():
    """PLI's defining property: a phase lag of exactly 0 (or pi) gives PLI=0
    -- the sign of sin(phase_diff) is undefined/oscillates around zero, so a
    perfectly IN-PHASE pair (the classic volume-conduction artifact case)
    must show PLI near 0, unlike PLV which would show ~1.0 for the same
    signals."""
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 5 * t)
    signals = np.array([base, base])  # identical signals: zero-lag "coupling"
    pli = compute_pli(signals)
    assert pli[0, 1] < 0.05


def test_pli_nonzero_for_consistent_nonzero_lag():
    """A consistent, nonzero phase lag (not 0 or pi) must give PLI > 0,
    unlike the zero-lag case above -- this is the coupling PLI is meant to
    detect."""
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 5 * t)
    lagged = np.sin(2 * np.pi * 5 * t + np.pi / 3)  # consistent 60-degree lag
    signals = np.array([base, lagged])
    pli = compute_pli(signals)
    assert pli[0, 1] > 0.7


# ---------------------------------------------------------------------------
# compute_wpli
# ---------------------------------------------------------------------------

def test_wpli_diagonal_is_one_by_convention():
    rng = np.random.default_rng(7)
    signals = rng.standard_normal((4, 300))
    wpli = compute_wpli(signals)
    assert np.allclose(np.diag(wpli), 1.0)


def test_wpli_symmetric():
    rng = np.random.default_rng(8)
    signals = rng.standard_normal((4, 300))
    wpli = compute_wpli(signals)
    assert np.allclose(wpli, wpli.T)


def test_wpli_zero_for_zero_lag_coupling():
    """Same defining property as PLI: zero-lag coupling gives wPLI near 0."""
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 5 * t)
    signals = np.array([base, base])
    wpli = compute_wpli(signals)
    assert wpli[0, 1] < 0.05


def test_wpli_nonzero_for_consistent_nonzero_lag():
    t = np.linspace(0, 4, 1000)
    base = np.sin(2 * np.pi * 5 * t)
    lagged = np.sin(2 * np.pi * 5 * t + np.pi / 3)
    signals = np.array([base, lagged])
    wpli = compute_wpli(signals)
    assert wpli[0, 1] > 0.7


@pytest.mark.skipif(not _HAVE_MNE_CONNECTIVITY, reason="requires mne-connectivity")
def test_wpli_qualitatively_agrees_with_mne_connectivity_reference():
    """Cross-validation against the maintained `mne-connectivity` reference
    implementation. Exact numerical agreement isn't expected: mne-connectivity's
    wPLI averages the cross-spectrum across repeated TRIALS/EPOCHS (its
    documented use case), while this repo's signals have no trial structure
    and compute_wpli instead averages across TIME SAMPLES within one window
    (the same formula, applied to whichever axis represents repeated
    observations -- see compute_wpli's docstring). What both implementations
    must agree on: a channel pair with a genuine, consistent phase
    relationship shows much higher connectivity than a pair of independent
    noise channels -- checked here by feeding mne-connectivity multiple
    epochs with a fixed cross-epoch phase LAG (its native use case) and
    checking this module's single-window function on the concatenated signal
    shows the same qualitative ranking.
    """
    from mne_connectivity import spectral_connectivity_epochs

    sfreq = 250.0
    n_epochs = 20
    n_samples = 200
    rng = np.random.default_rng(9)

    sig0 = np.zeros((n_epochs, n_samples))
    sig1 = np.zeros((n_epochs, n_samples))
    sig2 = np.zeros((n_epochs, n_samples))
    sig3 = np.zeros((n_epochs, n_samples))
    t = np.arange(n_samples) / sfreq
    for e in range(n_epochs):
        phase_offset = rng.uniform(0, 2 * np.pi)
        sig0[e] = np.sin(2 * np.pi * 10 * t + phase_offset) + 0.05 * rng.standard_normal(n_samples)
        sig1[e] = np.sin(2 * np.pi * 10 * t + phase_offset + 0.3) + 0.05 * rng.standard_normal(n_samples)
        sig2[e] = rng.standard_normal(n_samples)
        sig3[e] = rng.standard_normal(n_samples)

    data = np.stack([sig0, sig1, sig2, sig3], axis=1)  # (epochs, channels, samples)
    con = spectral_connectivity_epochs(
        data, method="wpli", sfreq=sfreq, fmin=8, fmax=13, faverage=True, verbose=False
    )
    ref = con.get_data(output="dense")[:, :, 0]
    ref_connected = ref[1, 0]  # sig0-sig1: fixed phase lag across epochs
    ref_independent = max(ref[2, 0], ref[3, 0], ref[3, 2])

    concat = np.array([sig0.flatten(), sig1.flatten(), sig2.flatten(), sig3.flatten()])
    mine = compute_wpli(concat)
    mine_connected = mine[0, 1]
    mine_independent = max(mine[2, 0], mine[3, 0], mine[3, 2])

    assert ref_connected > ref_independent  # sanity: reference sees the real coupling
    assert mine_connected > mine_independent  # this module agrees on the ranking


# ---------------------------------------------------------------------------
# compute_granger_causality / compute_granger_causality_matrix
# ---------------------------------------------------------------------------

def test_granger_causality_detects_known_directed_influence():
    """Construct y that genuinely drives x with a 2-sample lag (x[t] depends
    on y[t-2]) -- the textbook case Granger causality is built to detect.
    Must find y->x significant (low p-value)."""
    rng = np.random.default_rng(10)
    n = 300
    y = rng.standard_normal(n)
    x = np.zeros(n)
    for t in range(2, n):
        x[t] = 0.8 * y[t - 2] + 0.1 * rng.standard_normal()

    result = compute_granger_causality(x, y, maxlag=5)
    assert result["min_p_value"] < 0.01


def test_granger_causality_independent_series_not_significant():
    """Two independent random series must NOT show significant Granger
    causality -- the null case."""
    rng = np.random.default_rng(11)
    x = rng.standard_normal(300)
    y = rng.standard_normal(300)
    result = compute_granger_causality(x, y, maxlag=5)
    assert result["min_p_value"] > 0.01


def test_granger_causality_matrix_shape_and_keys():
    rng = np.random.default_rng(12)
    signals = rng.standard_normal((3, 200))
    result = compute_granger_causality_matrix(signals, maxlag=3)
    assert len(result) == 3 * 2  # every ordered pair, no self-pairs
    assert "1->0" in result and "0->1" in result
    assert "0->0" not in result
