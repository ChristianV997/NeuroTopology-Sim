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


def compute_pli(signals: np.ndarray) -> np.ndarray:
    """Phase Lag Index (PLI) matrix -- Stam et al. 2007.

    Unlike `compute_plv`, PLI measures the consistency of the SIGN of the
    instantaneous phase difference (not its magnitude/direction), which
    makes it insensitive to zero-lag coupling -- a real methodological
    advantage for scalp EEG, where zero-lag "connectivity" is often actually
    volume conduction from a shared source, not genuine neural coupling.

    Returns a symmetric matrix in [0, 1], diagonal 1.0 by convention (self-
    coupling is trivially maximal, matching `compute_plv`'s convention;
    computed literally it would be 0, since sin(0)=0 for every sample).
    """
    from scipy.signal import hilbert

    arr = np.asarray(signals, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"signals must be 2D (channels x samples), got shape {arr.shape}")

    phase = np.angle(hilbert(arr, axis=1))
    n_ch = phase.shape[0]
    pli = np.ones((n_ch, n_ch), dtype=float)
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            diff = phase[i] - phase[j]
            v = np.abs(np.mean(np.sign(np.sin(diff))))
            pli[i, j] = pli[j, i] = float(v)
    return pli


def compute_wpli(signals: np.ndarray) -> np.ndarray:
    """Weighted Phase Lag Index (wPLI) matrix -- Vinck et al. 2011.

    Debiased extension of PLI: weights each sample's contribution by the
    magnitude of the imaginary part of the analytic cross-spectrum, reducing
    sensitivity to noise compared to plain PLI while keeping the same
    zero-lag-insensitivity property. Computed here across TIME SAMPLES
    within one window (this repo's signals have no trial/epoch structure),
    the same single-window convention already used by `compute_plv`/
    `compute_pli` above -- the standard multi-trial formulation (as
    implemented by e.g. `mne-connectivity`) averages the cross-spectrum
    across repeated trials/epochs instead; the underlying formula (Vinck et
    al. 2011, Eq. 8) is the same, applied to whichever axis represents
    repeated observations for a given use case.

    Returns a symmetric matrix in [0, 1], diagonal 1.0 by convention.
    """
    from scipy.signal import hilbert

    arr = np.asarray(signals, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"signals must be 2D (channels x samples), got shape {arr.shape}")

    analytic = hilbert(arr, axis=1)
    n_ch = arr.shape[0]
    wpli = np.ones((n_ch, n_ch), dtype=float)
    for i in range(n_ch):
        for j in range(i + 1, n_ch):
            cross_spectrum = analytic[i] * np.conj(analytic[j])
            imag_part = np.imag(cross_spectrum)
            numerator = np.abs(np.mean(imag_part))
            denominator = np.mean(np.abs(imag_part))
            v = float(numerator / denominator) if denominator > 1e-12 else 0.0
            wpli[i, j] = wpli[j, i] = v
    return wpli


def compute_granger_causality(x: np.ndarray, y: np.ndarray, maxlag: int = 5) -> dict:
    """Test whether `y` Granger-causes `x` (past values of `y` improve
    prediction of `x` beyond `x`'s own past) via `statsmodels` (already a
    dependency) -- deliberately not IDTxl/JIDT (GPLv3), which this repo's
    tool-adoption policy excludes for transfer-entropy/directed-connectivity
    work.

    Returns the per-lag F-test p-values plus the minimum p-value across
    lags 1..maxlag (the standard "does Granger causality exist at any tested
    lag" summary statistic).
    """
    from statsmodels.tsa.stattools import grangercausalitytests

    data = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    results = grangercausalitytests(data, maxlag=maxlag)
    p_values = {lag: float(res[0]["ssr_ftest"][1]) for lag, res in results.items()}
    min_p_lag = min(p_values, key=p_values.get)
    return {
        "p_values_by_lag": p_values,
        "min_p_value": p_values[min_p_lag],
        "min_p_lag": min_p_lag,
        "maxlag": maxlag,
    }


def compute_granger_causality_matrix(signals: np.ndarray, maxlag: int = 5) -> dict:
    """Pairwise directed Granger causality across all channel pairs.

    Opt-in, compute-bounded addition (this repo's established pattern, e.g.
    `sciencer_d/btc_icft/level_t/base_real_topology.py`'s `--compute-nulls`):
    O(n_channels^2) directed Granger tests, each an O(maxlag) set of OLS
    fits -- meaningfully more expensive than PLV/PLI/wPLI's O(n_channels^2)
    simple phase comparisons, so callers should bound `n_channels` (via
    `max_channels` upstream) and/or `maxlag` for larger datasets.

    Returns `{"j->i": min_p_value, ...}` for every ordered pair -- a small
    p-value means channel j's past significantly improves prediction of
    channel i beyond i's own past (evidence of directed influence, not
    proof of causation in the everyday sense -- Granger causality is a
    predictive-improvement test, a standard caveat of the method itself).
    """
    arr = np.asarray(signals, dtype=float)
    n_ch = arr.shape[0]
    result: dict[str, float] = {}
    for i in range(n_ch):
        for j in range(n_ch):
            if i == j:
                continue
            key = f"{j}->{i}"
            try:
                gc = compute_granger_causality(arr[i], arr[j], maxlag=maxlag)
                result[key] = gc["min_p_value"]
            except Exception:
                result[key] = float("nan")
    return result


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
