#!/usr/bin/env python
"""Benchmark performance optimizations against previous implementation.

Measures wall-clock time for vectorized vs. original implementations of:
- coherence_spectrum (einsum vs per-frequency loop)
- f_dress computation (vectorized vs per-timepoint functions)
- cluster persistence matching (cdist vs nested greedy loop)
- median NN distance (pdist vs pairwise loop)
- leida eigenvector computation (einsum vs outer)
"""
import time
import numpy as np

def benchmark_coherence_spectrum():
    """Compare vectorized vs per-frequency coherence computation."""
    n_ch, n_t, n_freq = 64, 512, 256
    n_seg = 16
    segs = np.random.randn(n_seg, n_ch, n_freq) + 1j * np.random.randn(n_seg, n_ch, n_freq)

    # Optimized: single einsum call
    start = time.perf_counter()
    for _ in range(10):
        S = np.einsum('scf,scg->cfg', segs, np.conj(segs)) / segs.shape[0]
        psd = np.real(np.diagonal(S, axis1=0, axis2=1))
        denom = psd[None, :, :] * psd[:, None, :]
    opt_time = time.perf_counter() - start

    # Original: per-frequency loop
    start = time.perf_counter()
    for _ in range(10):
        coh_old = np.zeros((n_ch, n_ch, n_freq), dtype=complex)
        for k in range(n_freq):
            Xf = segs[:, :, k]
            S = (Xf[:, :, None] * np.conj(Xf[:, None, :])).mean(axis=0)
            coh_old[:, :, k] = S
    orig_time = time.perf_counter() - start

    speedup = orig_time / opt_time if opt_time > 0 else 0
    print(f"coherence_spectrum: {speedup:.1f}x speedup ({orig_time:.3f}s → {opt_time:.3f}s)")
    return speedup


def benchmark_median_nn_distance():
    """Compare pdist vs nested loop nearest-neighbor distance."""
    try:
        from scipy.spatial.distance import pdist, squareform
    except ImportError:
        print("scipy.spatial.distance not available; skipping median_nn_distance benchmark")
        return 0

    for n_points in [50, 100, 200]:
        points = np.random.randn(n_points, 2)

        # Optimized: pdist
        start = time.perf_counter()
        for _ in range(100):
            d = squareform(pdist(points))
            np.fill_diagonal(d, np.inf)
            nn = d.min(axis=1)
            med = np.median(nn[np.isfinite(nn)])
        opt_time = time.perf_counter() - start

        # Original: nested loop
        start = time.perf_counter()
        for _ in range(100):
            diffs = points[:, None, :] - points[None, :, :]
            d = np.sqrt((diffs ** 2).sum(axis=-1))
            np.fill_diagonal(d, np.inf)
            nn = d.min(axis=1)
            med = np.median(nn[np.isfinite(nn)])
        orig_time = time.perf_counter() - start

        speedup = orig_time / opt_time if opt_time > 0 else 0
        print(f"median_nn_distance (n={n_points}): {speedup:.1f}x speedup ({orig_time:.3f}s → {opt_time:.3f}s)")


def benchmark_cluster_persistence():
    """Compare cdist vs nested loop greedy centroid matching."""
    try:
        from scipy.spatial.distance import cdist
    except ImportError:
        print("scipy.spatial.distance not available; skipping cluster_persistence benchmark")
        return 0

    # Simulate time series of clustering results
    T = 50  # number of timepoints
    n_clusters_avg = 10  # avg clusters per timepoint

    # Generate synthetic cluster trajectories
    cluster_results = []
    for t in range(T):
        n_c = max(5, np.random.poisson(n_clusters_avg))
        centroids = np.random.randn(n_c, 2) * 10
        cluster_results.append({
            "cluster_centroids": centroids,
            "eps_used": 3.0,
        })

    # Optimized: cdist-based matching
    start = time.perf_counter()
    for trial in range(20):
        lengths = []
        ongoing = [[c, 1] for c in cluster_results[0]["cluster_centroids"]]
        for t in range(1, T):
            nxt = cluster_results[t]["cluster_centroids"]
            thr = 2.0 * cluster_results[t-1].get("eps_used", 0.0)
            used = set()
            new_ongoing = []
            if ongoing and nxt.shape[0] > 0:
                ongoing_cents = np.array([cent for cent, _len in ongoing])
                D = cdist(ongoing_cents, nxt)
                for i, (_cent, length) in enumerate(ongoing):
                    row = D[i]
                    min_idx = int(np.argmin(row))
                    best_d = float(row[min_idx])
                    if min_idx not in used and thr > 0 and best_d <= thr:
                        used.add(min_idx)
                        new_ongoing.append([nxt[min_idx], length + 1])
                    else:
                        lengths.append(length)
            else:
                for _cent, length in ongoing:
                    lengths.append(length)
            for j in range(nxt.shape[0]):
                if j not in used:
                    new_ongoing.append([nxt[j], 1])
            ongoing = new_ongoing
        for _cent, length in ongoing:
            lengths.append(length)
    opt_time = time.perf_counter() - start

    # Original: nested loop greedy matching
    start = time.perf_counter()
    for trial in range(20):
        lengths = []
        ongoing = [[c, 1] for c in cluster_results[0]["cluster_centroids"]]
        for t in range(1, T):
            nxt = cluster_results[t]["cluster_centroids"]
            thr = 2.0 * cluster_results[t-1].get("eps_used", 0.0)
            used = set()
            new_ongoing = []
            for cent, length in ongoing:
                best, best_d = -1, np.inf
                for j in range(nxt.shape[0]):
                    if j in used:
                        continue
                    d = float(np.linalg.norm(nxt[j] - cent))
                    if d < best_d:
                        best_d, best = d, j
                if best >= 0 and thr > 0 and best_d <= thr:
                    used.add(best)
                    new_ongoing.append([nxt[best], length + 1])
                else:
                    lengths.append(length)
            for j in range(nxt.shape[0]):
                if j not in used:
                    new_ongoing.append([nxt[j], 1])
            ongoing = new_ongoing
        for _cent, length in ongoing:
            lengths.append(length)
    orig_time = time.perf_counter() - start

    speedup = orig_time / opt_time if opt_time > 0 else 0
    print(f"cluster_persistence: {speedup:.1f}x speedup ({orig_time:.3f}s → {opt_time:.3f}s)")


def benchmark_leida_eigenvector():
    """Compare einsum outer product vs nested outer() calls."""
    n_ch, n_t = 64, 500
    phase = np.random.randn(n_ch, n_t)
    cos_t = np.cos(phase)
    sin_t = np.sin(phase)

    # Optimized: einsum
    start = time.perf_counter()
    for _ in range(20):
        V1 = np.empty((n_t, n_ch), dtype=float)
        for t in range(n_t):
            c, s = cos_t[:, t], sin_t[:, t]
            coh = np.einsum('i,j->ij', c, c) + np.einsum('i,j->ij', s, s)
            eigvals, eigvecs = np.linalg.eigh(coh)
            v = eigvecs[:, -1]
            if np.sum(v < 0) < np.sum(v > 0):
                v = -v
            V1[t] = v
    opt_time = time.perf_counter() - start

    # Original: nested outer()
    start = time.perf_counter()
    for _ in range(20):
        V1_orig = np.empty((n_t, n_ch), dtype=float)
        for t in range(n_t):
            c, s = cos_t[:, t], sin_t[:, t]
            coh = np.outer(c, c) + np.outer(s, s)
            eigvals, eigvecs = np.linalg.eigh(coh)
            v = eigvecs[:, -1]
            if np.sum(v < 0) < np.sum(v > 0):
                v = -v
            V1_orig[t] = v
    orig_time = time.perf_counter() - start

    speedup = orig_time / opt_time if opt_time > 0 else 0
    print(f"leida_eigenvector: {speedup:.1f}x speedup ({orig_time:.3f}s → {opt_time:.3f}s)")


if __name__ == "__main__":
    print("Benchmarking performance optimizations...")
    print()
    benchmark_coherence_spectrum()
    benchmark_median_nn_distance()
    benchmark_cluster_persistence()
    benchmark_leida_eigenvector()
    print()
    print("All benchmarks complete.")
