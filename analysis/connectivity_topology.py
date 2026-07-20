"""Real connectivity + persistent-homology instruments, factored out of
`analysis/itct/itct_cessation_protocol_v3_full_stack.py`.

That file's PLV (phase-locking value) computation and `ripser`-based persistent
H1 (loop) counting are real, established techniques -- and, before this module
existed, the *only* place in this repository that computed genuine phase
connectivity or real persistent homology from EEG signal. The three published
BTC/ICFT dataset reports (ds005620/ds003969/ds001787) never used them; they used
`sciencer_d/btc_icft/level_t/eeg_signal_topology.py::compute_topology_from_channels`,
a channel-mean/correlation-threshold heuristic with no phase or frequency
information at all.

This module is the factored, independently-tested core so that other pipelines
can reuse it directly, without depending on the ITCT file's more speculative
extras (`loschmidt_echo`, `exceptional_point_discriminant`, `tus_engaged`) --
those are non-standard, unestablished additions kept where they are, not
promoted into shared, reusable infrastructure.
"""
from __future__ import annotations

import numpy as np


def compute_plv(signals: np.ndarray) -> np.ndarray:
    """Phase-locking value matrix from real multi-channel signal data.

    Parameters
    ----------
    signals : ndarray, shape (n_channels, n_samples)

    Returns
    -------
    plv : ndarray, shape (n_channels, n_channels), symmetric, diagonal 1.0.
        PLV[i, j] = |mean(exp(i * (phase_i - phase_j)))| in [0, 1]; 1.0 means
        channels i and j maintain a constant phase relationship across the
        window (perfectly phase-locked), 0.0 means the phase difference is
        uniformly distributed (no consistent coupling).
    """
    from scipy.signal import hilbert

    arr = np.asarray(signals, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"signals must be 2D (channels x samples), got shape {arr.shape}")

    phase = np.angle(hilbert(arr, axis=1))
    n_ch = phase.shape[0]
    plv = np.ones((n_ch, n_ch), dtype=float)
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            v = np.abs(np.mean(np.exp(1j * (phase[i] - phase[j]))))
            plv[i, j] = plv[j, i] = float(v)
    return plv


def compute_beta1(plv: np.ndarray, threshold: float = 0.5) -> int:
    """First Betti number (count of persistent H1 loop features) via REAL
    persistent homology (`ripser`), not a graph-theory cyclomatic-number proxy.

    PLV in [0, 1] is a similarity; `ripser` needs a distance matrix, so this
    uses 1-PLV. `beta1` at a given `threshold` counts H1 features whose
    persistence interval [birth, death) contains the corresponding distance
    `1-threshold` -- i.e. loops alive at that similarity cutoff, not just
    "ever born" during the filtration.
    """
    import ripser

    D = 1.0 - np.clip(plv, 0.0, 1.0)
    np.fill_diagonal(D, 0.0)
    dgms = ripser.ripser(D, distance_matrix=True, maxdim=1)["dgms"]
    h1 = dgms[1] if len(dgms) > 1 else np.empty((0, 2))
    d_thresh = 1.0 - threshold
    alive = h1[(h1[:, 0] <= d_thresh) & (h1[:, 1] > d_thresh)]
    return int(alive.shape[0])


def compute_persistence_diagram(plv: np.ndarray) -> list:
    """Full H0/H1 persistence diagrams (`ripser`) for manuscript-grade figures
    via `persim`, or for downstream summary statistics beyond beta1 alone."""
    import ripser

    D = 1.0 - np.clip(plv, 0.0, 1.0)
    np.fill_diagonal(D, 0.0)
    return ripser.ripser(D, distance_matrix=True, maxdim=1)["dgms"]


def compute_spectral_dimension(plv: np.ndarray, threshold: float = 0.5) -> float:
    """Spectral dimension from the PLV-graph Laplacian eigenvalue staircase.

    Threshold `plv` into an unweighted graph (edge iff plv >= threshold), then
    fit the log(eigenvalue) vs log(rank) slope of the graph Laplacian spectrum
    -- a standard complex-network descriptor of a connectivity graph's
    effective dimensionality, independent of the persistent-homology beta1
    count above.
    """
    import networkx as nx

    n_ch = plv.shape[0]
    G = nx.Graph()
    G.add_nodes_from(range(n_ch))
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            if plv[i, j] >= threshold:
                G.add_edge(i, j)
    if G.number_of_edges() == 0:
        return 0.0
    L = nx.laplacian_matrix(G).toarray().astype(float)
    ev = np.sort(np.linalg.eigvalsh(L))
    ev = ev[ev > 1e-9]
    if len(ev) < 3:
        return 0.0
    k = np.arange(1, len(ev) + 1)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        slope = np.polyfit(np.log(ev), np.log(k), 1)[0]
    return float(2.0 * slope)
