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
    n_samples = phase.shape[1]
    z = np.exp(1j * phase)
    # |mean_t(exp(i*(phase_i - phase_j)))| = |(Z @ Z^H)[i, j]| / n_samples, since
    # (Z @ Z^H)[i, j] = sum_t exp(i*phase_i[t]) * exp(-i*phase_j[t]). A single
    # BLAS matmul replaces the O(n_channels^2) pairwise Python loop.
    plv = np.abs(z @ z.conj().T) / n_samples
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
    # sign(sin(.)) is nonlinear, so unlike PLV this can't collapse to one matmul;
    # instead the inner Python loop over j is vectorized per row, cutting the
    # O(n_channels^2) pairwise loop down to O(n_channels) without materializing
    # a full (n_channels, n_channels, n_samples) tensor.
    for i in range(n_ch - 1):
        diff = phase[i] - phase[i + 1:]
        v = np.abs(np.mean(np.sign(np.sin(diff)), axis=1))
        pli[i, i + 1:] = v
        pli[i + 1:, i] = v
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
    # Same row-at-a-time vectorization as compute_pli: O(n_channels) Python
    # iterations instead of O(n_channels^2), bounded (n_channels, n_samples)
    # memory per iteration.
    for i in range(n_ch - 1):
        cross_spectrum = analytic[i] * np.conj(analytic[i + 1:])
        imag_part = np.imag(cross_spectrum)
        numerator = np.abs(np.mean(imag_part, axis=1))
        denominator = np.mean(np.abs(imag_part), axis=1)
        v = np.where(denominator > 1e-12, numerator / np.where(denominator > 1e-12, denominator, 1.0), 0.0)
        wpli[i, i + 1:] = v
        wpli[i + 1:, i] = v
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
    """Graph ``beta_1`` (persistent H1 loop features) via real persistent
    homology (`ripser`), not a graph-theory cyclomatic-number proxy.

    PLV in [0, 1] is a similarity; `ripser` needs a distance matrix, so this
    uses 1-PLV. ``graph_beta1`` at a given ``threshold`` counts H1 features whose
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


# ---------------------------------------------------------------------------
# Explicit metric names and deterministic null controls
# ---------------------------------------------------------------------------

def compute_graph_beta1(plv: np.ndarray, threshold: float = 0.5) -> int:
    """Return graph-derived H1 only; this is never spatial winding or charge."""
    return compute_beta1(plv, threshold=threshold)


def topology_metric_record(
    *,
    graph_beta1: int | None = None,
    spatial_winding_q: float | None = None,
    spin_chain_winding: float | None = None,
    scalar_chirality: float | None = None,
    defect_density: float | None = None,
    persistence_landscape_area: float | None = None,
    provenance: dict | None = None,
) -> dict:
    """Build a topology payload with intentionally non-interchangeable fields.

    ``None`` means the quantity was not measured. In particular, this helper
    never derives a spatial charge from a graph cycle count or channel order.
    """
    values = {
        "graph_beta1": graph_beta1,
        "spatial_winding_q": spatial_winding_q,
        "spin_chain_winding": spin_chain_winding,
        "scalar_chirality": scalar_chirality,
        "defect_density": defect_density,
        "persistence_landscape_area": persistence_landscape_area,
    }
    if graph_beta1 is not None and (isinstance(graph_beta1, bool) or int(graph_beta1) < 0):
        raise ValueError("graph_beta1 must be a non-negative integer")
    for name, value in values.items():
        if value is not None and not np.isfinite(float(value)):
            raise ValueError(f"{name} must be finite when supplied")
    return {
        "metric_names": list(values),
        "metrics": values,
        "provenance": dict(provenance or {}),
        "separation": {
            "graph_beta1_is_spatial_charge": False,
            "spatial_winding_requires_coordinates": True,
        },
    }


def _validate_control_signals(signals: np.ndarray) -> np.ndarray:
    values = np.asarray(signals, dtype=float)
    if values.ndim != 2 or not values.size or not np.all(np.isfinite(values)):
        raise ValueError("signals must be a finite (channels, samples) array")
    return values


def phase_randomization(signals: np.ndarray, seed: int = 0) -> np.ndarray:
    """Phase-randomize each channel while retaining its Fourier magnitudes."""
    values = _validate_control_signals(signals)
    rng = np.random.default_rng(seed)
    spectrum = np.fft.rfft(values, axis=1)
    if spectrum.shape[1] > 2:
        phases = rng.uniform(-np.pi, np.pi, size=(values.shape[0], spectrum.shape[1] - 2))
        spectrum[:, 1:-1] = np.abs(spectrum[:, 1:-1]) * np.exp(1j * phases)
    return np.asarray(np.fft.irfft(spectrum, n=values.shape[1], axis=1), dtype=float)


def channel_shuffling(signals: np.ndarray, seed: int = 0) -> np.ndarray:
    """Shuffle channel identities with a deterministic seed."""
    values = _validate_control_signals(signals)
    return values[np.random.default_rng(seed).permutation(values.shape[0])]


def time_reversal(signals: np.ndarray, seed: int = 0) -> np.ndarray:
    """Reverse time without changing channel identities.

    ``seed`` is accepted for a uniform control API and recorded by the bundle;
    this null is deterministic without consuming randomness.
    """
    int(seed)  # validate that recorded control seeds remain integral
    return _validate_control_signals(signals)[:, ::-1].copy()


def coordinate_shuffling(coordinates: np.ndarray, seed: int = 0) -> np.ndarray:
    """Shuffle observed coordinates as a coordinate-label null."""
    values = np.asarray(coordinates, dtype=float)
    if values.ndim != 2 or values.shape[1] not in (2, 3) or not np.all(np.isfinite(values)):
        raise ValueError("coordinates must be finite with shape (n,2) or (n,3)")
    return values[np.random.default_rng(seed).permutation(values.shape[0])]


def block_permutation(signals: np.ndarray, block_size: int, seed: int = 0) -> np.ndarray:
    """Permute contiguous time blocks, preserving within-block structure."""
    values = _validate_control_signals(signals)
    if int(block_size) < 1:
        raise ValueError("block_size must be positive")
    blocks = [values[:, start : start + int(block_size)] for start in range(0, values.shape[1], int(block_size))]
    order = np.random.default_rng(seed).permutation(len(blocks))
    return np.concatenate([blocks[index] for index in order], axis=1)


def stationary_null(signals: np.ndarray, seed: int = 0) -> np.ndarray:
    """Create a stationary circular-shift null with one deterministic offset/channel."""
    values = _validate_control_signals(signals)
    rng = np.random.default_rng(seed)
    offsets = rng.integers(0, values.shape[1], size=values.shape[0])
    return np.stack([np.roll(row, int(offset)) for row, offset in zip(values, offsets)], axis=0)


def generate_null_controls(
    signals: np.ndarray,
    *,
    coordinates: np.ndarray | None = None,
    block_size: int | None = None,
    seed: int = 0,
) -> dict[str, dict[str, object]]:
    """Return deterministic null arrays with method and seed provenance."""
    values = _validate_control_signals(signals)
    size = int(block_size or max(1, values.shape[1] // 8))
    controls: dict[str, dict[str, object]] = {
        "phase_randomization": {
            "values": phase_randomization(values, seed=seed),
            "method": "fft_phase_randomization",
            "seed": int(seed),
        },
        "channel_shuffling": {
            "values": channel_shuffling(values, seed=seed),
            "method": "permutation_of_channel_identity",
            "seed": int(seed),
        },
        "time_reversal": {
            "values": time_reversal(values, seed=seed),
            "method": "reverse_time_axis",
            "seed": int(seed),
        },
        "block_permutation": {
            "values": block_permutation(values, size, seed=seed),
            "method": "contiguous_block_permutation",
            "seed": int(seed),
            "block_size": size,
        },
        "stationary_null": {
            "values": stationary_null(values, seed=seed),
            "method": "independent_circular_shift",
            "seed": int(seed),
        },
    }
    if coordinates is not None:
        controls["coordinate_shuffling"] = {
            "coordinates": coordinate_shuffling(coordinates, seed=seed),
            "method": "coordinate_label_permutation",
            "seed": int(seed),
        }
    return controls


# Descriptive aliases for callers using the terminology from the contract.
shuffle_channels = channel_shuffling
shuffle_coordinates = coordinate_shuffling
