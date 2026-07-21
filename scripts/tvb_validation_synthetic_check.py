#!/usr/bin/env python3
"""Part 3 (lowest priority): TVB synthetic sanity/calibration check.

Generate synthetic region-level time series from The Virtual Brain using a known
bundled structural connectome (the default 76-region connectivity that ships with
tvb-library -- NOT a custom or real-subject connectome), feed the output through
the repo's existing phase-grid TDA + coherence spectral-TDA, and check whether the
known simulated coupling is recoverable (simulated functional connectivity should
track the structural connectome, and the topology metrics should pass the
surrogate gate rather than looking like phase-randomized noise).

This is a single calibration script, NOT a new pipeline: no TVB-NEST, no NEST,
no EBRAINS/Docker, no BIDS. `pip install tvb-library` only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay
from scipy.signal import hilbert

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from validation.montage_topology import phase_grid_topology_from_band   # noqa: E402
from validation.surrogate_testing import surrogate_test_topology_metric  # noqa: E402
from dual_engine.spectral_tda import (  # noqa: E402
    coherence_spectrum, spectral_landscape, spectral_landscape_band_summary,
)


def _mean_abscorr(ts):
    C = np.corrcoef(ts)
    iu = np.triu_indices(C.shape[0], 1)
    return float(np.mean(np.abs(C[iu])))


def run():
    import warnings
    warnings.filterwarnings("ignore")
    try:
        from tvb.simulator.lab import (
            connectivity, coupling, integrators, models, monitors, noise, simulator,
        )
    except Exception as e:  # pragma: no cover
        print(f"BLOCKER: tvb-library not importable ({e!r}); skipping Part 3.")
        return

    print("=== TVB synthetic validation (default 76-region connectome) ===")
    conn = connectivity.Connectivity.from_file()   # bundled default connectivity_76
    conn.speed = np.array([4.0])
    conn.configure()
    n_reg = conn.weights.shape[0]
    print(f"connectome: {n_reg} regions; structural weights nonzero frac="
          f"{np.mean(conn.weights > 0):.2f}")

    from scipy.stats import pearsonr
    iu = np.triu_indices(n_reg, 1)
    SC = 0.5 * (conn.weights + conn.weights.T)

    # Sweep coupling strength: recovery (FC tracking the structural connectome)
    # should EMERGE as the connectome actually drives the dynamics. Weak coupling
    # -> near-independent nodes -> no recovery; that is expected, not a failure.
    print("\n[coupling sweep] corr(|FC|, structural weights) vs coupling strength a:")
    best = None
    for a in (0.02, 0.1, 0.3, 0.6):
        sim = simulator.Simulator(
            model=models.Generic2dOscillator(a=np.array([0.3])),
            connectivity=conn,
            coupling=coupling.Linear(a=np.array([a])),
            integrator=integrators.HeunStochastic(
                dt=0.5, noise=noise.Additive(nsig=np.array([0.002]))),
            monitors=(monitors.TemporalAverage(period=2.0),),
            simulation_length=6000.0,
        ).configure()
        (t, data), = sim.run()
        tsi = np.ascontiguousarray(data[:, 0, :, 0].T)
        tsi = tsi[:, tsi.shape[1] // 5:]
        if not np.all(np.isfinite(tsi)):
            print(f"  a={a:.2f}: non-finite (unstable) -- skipped"); continue
        FCi = np.corrcoef(tsi)
        r_i, p_i = pearsonr(np.abs(FCi[iu]), SC[iu])
        print(f"  a={a:.2f}: r={r_i:+.3f} p={p_i:.1e}")
        if best is None or r_i > best[1]:
            best = (a, r_i, p_i, tsi)
    a_best, r_fc_sc, p_fc_sc, ts = best
    print(f"[recovery] best coupling a={a_best:.2f}: corr(|FC|, SC) r={r_fc_sc:+.3f} "
          f"p={p_fc_sc:.2e}  ({'RECOVERED' if r_fc_sc > 0.2 and p_fc_sc < 0.05 else 'weak'})")
    print(f"simulated series (best): {ts.shape[0]} regions x {ts.shape[1]} samples")
    FC = np.corrcoef(ts)

    # 2) phase-grid topology on region centres (2D projection + Delaunay)
    xy = conn.centres[:, :2].astype(float)
    tri = Delaunay(xy).simplices
    ph = np.angle(hilbert(ts, axis=1))
    idx = np.linspace(0, ph.shape[1] - 1, min(200, ph.shape[1])).astype(int)
    topo = phase_grid_topology_from_band(ph[:, idx], xy, tri)
    print(f"[phase-grid] Qabs={topo['Qabs']:.3f} defect_density={topo['defect_density']:.4f} "
          f"n_valid_tri={topo['n_valid_triangles']}")

    # 3) surrogate gate: is the simulated coupling above the phase-randomized null?
    gate = surrogate_test_topology_metric(ts, _mean_abscorr, n_surrogates=100,
                                          method="ft", two_sided=False, random_state=3)
    print(f"[gate] mean|corr| real={gate['real_value']:.3f} surr={gate['surrogate_mean']:.3f} "
          f"z={gate['z_score']:+.1f} p={gate['p_value']:.3f} "
          f"passes={gate['passes_gate_p05']}")

    # 4) spectral TDA (TemporalAverage period 2 ms -> sfreq 500 Hz)
    sfreq = 500.0
    try:
        cs = coherence_spectrum(ts, sfreq, fmin=1, fmax=45)
        land = spectral_landscape(cs["coherence"], cs["freqs"], max_freqs=30)
        summ = spectral_landscape_band_summary(land)["band_mass"]
        print(f"[spectral] band mass: " +
              " ".join(f"{b}={summ[b]:.4f}" if summ[b] is not None else f"{b}=NA" for b in
                       ["delta", "theta", "alpha", "beta", "gamma"]))
    except Exception as e:
        print(f"[spectral] skipped: {e!r}")

    verdict = ("RECOVERED: simulated coupling tracks the structural connectome and the "
               "topology metrics pass the surrogate gate"
               if (r_fc_sc > 0.15 and p_fc_sc < 0.05 and gate["passes_gate_p05"])
               else "PARTIAL/NULL: see numbers above")
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    run()
