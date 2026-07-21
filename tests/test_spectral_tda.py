from __future__ import annotations

import numpy as np
import pytest

from dual_engine.spectral_tda import (
    coherence_spectrum,
    spectral_landscape,
    spectral_landscape_band_summary,
)


def test_coherence_spectrum_shape_and_finite():
    rng = np.random.default_rng(0)
    sfreq = 128.0
    ts = rng.standard_normal((6, 2048))
    res = coherence_spectrum(ts, sfreq, fmin=1, fmax=45)
    coh, freqs = res["coherence"], res["freqs"]
    assert coh.shape[0] == coh.shape[1] == 6
    assert coh.shape[2] == freqs.size
    assert np.all(np.isfinite(coh))
    assert coh.min() >= 0.0 and coh.max() <= 1.0 + 1e-9
    assert freqs.min() >= 1.0 and freqs.max() <= 45.0


def test_coherence_spectrum_validation():
    with pytest.raises(ValueError):
        coherence_spectrum(np.zeros(100), 128.0)          # 1D
    with pytest.raises(ValueError):
        coherence_spectrum(np.zeros((1, 512)), 128.0)     # <2 channels


def _beta_ring(sfreq=128.0, n_t=8192, seed=0):
    """6 channels wired into a RING that exists ONLY in the beta band (13-30 Hz).

    Each channel i = beta_driver[i] + beta_driver[(i+1)%6] + noise, so adjacent
    channels (i, i+1) share a beta driver (coupled) but non-adjacent channels
    share none (uncoupled). That adjacency ring is a genuine 1-cycle -> an H1 loop
    in the beta coherence filtration, and nothing analogous in the other bands
    (independent noise there). This is the core regression: spectral TDA must put
    the loop 'mass' in beta specifically.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_t) / sfreq
    n = 6

    def beta_driver():
        s = np.zeros(n_t)
        for f in np.arange(15, 26, 0.5):
            s += np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
        return s

    drivers = [beta_driver() for _ in range(n)]
    chans = [2.0 * (drivers[i] + drivers[(i + 1) % n]) + rng.standard_normal(n_t) for i in range(n)]
    return np.array(chans), sfreq


def test_spectral_landscape_band_summary_localizes_frequency_coupling():
    ts, sfreq = _beta_ring()
    res = coherence_spectrum(ts, sfreq, fmin=1, fmax=45)
    land = spectral_landscape(res["coherence"], res["freqs"])
    summ = spectral_landscape_band_summary(land)["band_mass"]
    # the beta-band ring must carry the most topological (loop) mass of any band
    assert summ["beta"] is not None
    others = {b: m for b, m in summ.items() if b != "beta" and m is not None}
    assert summ["beta"] == max([summ["beta"], *others.values()]), \
        f"beta={summ['beta']:.4e} not the max; others={others}"
    assert summ["beta"] > max(others.values()), \
        f"beta ({summ['beta']:.4e}) not strictly > others {others}"


def test_spectral_landscape_finite_and_shape():
    rng = np.random.default_rng(1)
    ts = rng.standard_normal((5, 2048))
    res = coherence_spectrum(ts, 128.0, fmin=1, fmax=45)
    grid = np.linspace(0, 1, 50)
    land = spectral_landscape(res["coherence"], res["freqs"], filtration_values=grid, max_freqs=20)
    assert land["landscape"].shape[1] == 50
    assert land["landscape"].shape[0] <= 20
    assert np.all(np.isfinite(land["landscape"]))
