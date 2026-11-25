"""Lightweight engineering probes for adversarial checks (not scientific estimators)."""
from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, Optional

import numpy as np


def _zscore(x: np.ndarray) -> np.ndarray:
    mu = x.mean(axis=1, keepdims=True)
    sd = x.std(axis=1, keepdims=True)
    sd = np.where(sd > 1e-12, sd, 1.0)
    return (x - mu) / sd


def pairwise_mean_abs_corr(x: np.ndarray) -> float:
    """Mean absolute off-diagonal Pearson correlation (engineering probe)."""
    z = _zscore(np.asarray(x, dtype=np.float64))
    n = z.shape[0]
    if n < 2:
        return 0.0
    c = np.corrcoef(z)
    mask = ~np.eye(n, dtype=bool)
    vals = np.abs(c[mask])
    return float(np.mean(vals)) if vals.size else 0.0


def max_abs_pairwise_corr(x: np.ndarray) -> float:
    z = _zscore(np.asarray(x, dtype=np.float64))
    n = z.shape[0]
    if n < 2:
        return 0.0
    c = np.corrcoef(z)
    mask = ~np.eye(n, dtype=bool)
    return float(np.max(np.abs(c[mask]))) if mask.any() else 0.0


def max_abs_triadic_moment(x: np.ndarray, max_triads: int = 20) -> float:
    """Max |E[z_i z_j z_k]| over triads (engineering third-order probe)."""
    z = _zscore(np.asarray(x, dtype=np.float64))
    n = z.shape[0]
    if n < 3:
        return 0.0
    best = 0.0
    count = 0
    for i, j, k in combinations(range(n), 3):
        m = float(np.mean(z[i] * z[j] * z[k]))
        best = max(best, abs(m))
        count += 1
        if count >= max_triads:
            break
    return best


def spectral_bandpower_ratio(x: np.ndarray, fs: float = 128.0) -> float:
    """AM sensitivity probe: modulation-band power over a quiet mid-band.

    For an amplitude-modulated carrier, energy appears near the modulation
    frequency in the squared envelope; we approximate this via low-frequency
    power of ``signal**2`` relative to a mid-band floor.
    """
    arr = np.asarray(x, dtype=np.float64)
    sig = arr[0]
    env = sig.astype(np.float64) ** 2
    env = env - env.mean()
    spec = np.abs(np.fft.rfft(env)) ** 2
    freqs = np.fft.rfftfreq(env.size, d=1.0 / fs)
    mod = float(np.sum(spec[(freqs >= 0.5) & (freqs <= 2.0)]))
    mid = float(np.sum(spec[(freqs >= 3.0) & (freqs <= 6.0)]))
    return mod / (mid + 1e-12)


def lag1_mean_abs_acf(x: np.ndarray) -> float:
    arr = np.asarray(x, dtype=np.float64)
    vals = []
    for c in range(arr.shape[0]):
        xc = arr[c] - arr[c].mean()
        v = float(np.dot(xc, xc))
        if v <= 0:
            vals.append(0.0)
        else:
            vals.append(abs(float(np.dot(xc[1:], xc[:-1]) / v)))
    return float(np.mean(vals)) if vals else 0.0


def probe_bundle(x: np.ndarray) -> Dict[str, float]:
    return {
        "pairwise_mean_abs_corr": pairwise_mean_abs_corr(x),
        "max_abs_pairwise_corr": max_abs_pairwise_corr(x),
        "max_abs_triadic_moment": max_abs_triadic_moment(x),
        "spectral_bandpower_ratio": spectral_bandpower_ratio(x),
        "lag1_mean_abs_acf": lag1_mean_abs_acf(x),
    }


def soft_import_hypergraph():
    try:
        from topo_monitor.higher_order.hypergraph import SparseDirectedHypergraph
        from topo_monitor.higher_order.hypergraph_types import DirectedHyperedge

        return SparseDirectedHypergraph, DirectedHyperedge
    except Exception:
        return None, None


def soft_import_surrogate():
    try:
        from validation.surrogate_testing import phase_randomize_surrogate

        return phase_randomize_surrogate
    except Exception:
        return None


def hypergraph_triad_summary(weight: float = 1.0) -> Optional[Dict[str, Any]]:
    """Read-only smoke against SparseDirectedHypergraph when available."""
    HG, Edge = soft_import_hypergraph()
    if HG is None:
        return None
    edge = Edge(source_nodes=("A", "B"), target_nodes=("C",), weight=float(weight), synthetic=True)
    hg = HG([edge])
    summary = hg.compute_summary()
    return {
        "hyperedge_count": summary.hyperedge_count,
        "order_distribution": dict(summary.order_distribution),
        "available": True,
    }


def surrogate_pairwise_gate(x: np.ndarray, seed: int = 0, n_surr: int = 20) -> Dict[str, Any]:
    """Compare pairwise probe on real vs phase-shuffle null (engineering gate)."""
    real = max_abs_pairwise_corr(x)
    null_fn = soft_import_surrogate()
    rng = np.random.default_rng(seed)
    null_vals = []
    if null_fn is not None:
        sur = null_fn(x, method="ft", n_surrogates=n_surr, random_state=seed)
        for i in range(sur.shape[0]):
            null_vals.append(max_abs_pairwise_corr(sur[i]))
    else:
        from tools.higher_order_validation.nulls import phase_shuffle_null

        for i in range(n_surr):
            null_vals.append(max_abs_pairwise_corr(phase_shuffle_null(x, seed=seed + i)))
    null_arr = np.asarray(null_vals, dtype=np.float64)
    p = float((np.sum(null_arr >= real) + 1) / (null_arr.size + 1))
    return {
        "real_max_abs_pairwise_corr": real,
        "null_mean": float(np.mean(null_arr)),
        "null_p_engineering": p,
        "n_surrogates": int(null_arr.size),
    }
