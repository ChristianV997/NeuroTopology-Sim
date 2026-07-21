from __future__ import annotations

import numpy as np
import pytest

from validation.surrogate_testing import (
    phase_randomize_surrogate,
    surrogate_test_topology_metric,
)


def _synth(n_ch=6, n_t=1024, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n_t) / 128.0
    base = np.sin(2 * np.pi * 10 * t) + 0.5 * np.sin(2 * np.pi * 22 * t)
    return np.array([base + 0.3 * rng.standard_normal(n_t) for _ in range(n_ch)])


def test_phase_randomize_surrogate_preserves_power_spectrum():
    x = _synth()
    surr = phase_randomize_surrogate(x, method="ft", n_surrogates=5, random_state=1)
    s0 = surr[0]
    # amplitude spectrum preserved to numerical precision, per channel
    assert np.allclose(np.abs(np.fft.rfft(x, axis=1)), np.abs(np.fft.rfft(s0, axis=1)), atol=1e-8)
    # but the time-domain signal is substantially altered (phase destroyed)
    for c in range(x.shape[0]):
        r = np.corrcoef(x[c], s0[c])[0, 1]
        assert abs(r) < 0.9


def test_phase_randomize_surrogate_shape_and_count():
    x = _synth(n_ch=8, n_t=512)
    surr = phase_randomize_surrogate(x, n_surrogates=13, random_state=2)
    assert surr.shape == (13, 8, 512)


def test_iaaft_preserves_amplitude_distribution():
    rng = np.random.default_rng(3)
    n_t = 1024
    t = np.arange(n_t) / 128.0
    # skewed / heavy-tailed, non-Gaussian signal
    base = np.sin(2 * np.pi * 8 * t) + rng.exponential(1.0, n_t)
    x = np.array([base, np.roll(base, 5)])
    ft = phase_randomize_surrogate(x, method="ft", n_surrogates=1, random_state=4)[0]
    ia = phase_randomize_surrogate(x, method="iaaft", n_surrogates=1, random_state=4)[0]
    # IAAFT should match the sorted empirical distribution far better than FT
    err_ft = np.mean(np.abs(np.sort(ft[0]) - np.sort(x[0])))
    err_ia = np.mean(np.abs(np.sort(ia[0]) - np.sort(x[0])))
    assert err_ia < err_ft


def _mean_abscorr(ts, band=None):
    """metric_fn: mean off-diagonal absolute Pearson correlation across channels.

    This is broadband cross-channel structure that INDEPENDENT phase randomization
    destroys (it depends on phase alignment across the whole spectrum), so it is a
    clean instrument for the gate. (Note: PLV on narrowband signals would NOT work
    -- FT surrogates preserve the power spectrum, so a 10 Hz signal stays 10 Hz and
    two same-frequency sinusoids have PLV=1 regardless of phase; correlation avoids
    that trap.)
    """
    C = np.corrcoef(ts)
    n = C.shape[0]
    iu = np.triu_indices(n, 1)
    return float(np.mean(np.abs(C[iu])))


def _coupled(n_ch=10, n_t=1024, seed=0, indep=0.4):
    """Channels sharing a common BROADBAND signal + independent noise (real,
    spectrum-independent cross-channel structure)."""
    rng = np.random.default_rng(seed)
    common = rng.standard_normal(n_t)
    return np.array([common + indep * rng.standard_normal(n_t) for _ in range(n_ch)])


def test_surrogate_test_topology_metric_detects_real_structure():
    # strongly phase-locked channels: genuine cross-channel structure PLV sees
    x = _coupled(indep=0.4, seed=7)
    res = surrogate_test_topology_metric(x, _mean_abscorr, n_surrogates=60, random_state=11)
    assert res["n_failed"] == 0
    # real PLV structure differs strongly from the independently-randomized null
    assert res["p_value"] < 0.05 and res["passes_gate_p05"]


def test_surrogate_test_topology_metric_null_case():
    # independent white-ish noise channels: no real cross-channel structure.
    # Expect the gate to FAIL in the large majority of seeds (~alpha=0.05 FP rate).
    fails_gate = 0
    trials = 12
    for seed in range(trials):
        rng = np.random.default_rng(100 + seed)
        x = rng.standard_normal((8, 512))
        res = surrogate_test_topology_metric(x, _mean_abscorr, n_surrogates=50,
                                             two_sided=True, random_state=seed)
        if not res["passes_gate_p05"]:
            fails_gate += 1
    # should NOT pass the gate in most trials (allow a few false positives)
    assert fails_gate >= trials - 3


def test_preserve_cross_channel_lag_flag_changes_result():
    x = _coupled(indep=0.5, seed=5)
    indep = surrogate_test_topology_metric(x, _mean_abscorr, n_surrogates=40,
                                           preserve_cross_channel_lag=False, random_state=9)
    lagkeep = surrogate_test_topology_metric(x, _mean_abscorr, n_surrogates=40,
                                             preserve_cross_channel_lag=True, random_state=9)
    # preserving relative inter-channel phase yields a different null distribution
    assert not np.isclose(indep["surrogate_mean"], lagkeep["surrogate_mean"])


def test_input_validation():
    with pytest.raises(ValueError):
        phase_randomize_surrogate(np.zeros(10))          # 1D
    with pytest.raises(ValueError):
        phase_randomize_surrogate(np.zeros((1, 100)))    # <2 channels
    with pytest.raises(ValueError):
        phase_randomize_surrogate(np.zeros((3, 8)))      # too few timepoints
