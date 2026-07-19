from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


def pcist_proxy(epoch_2d):
    """Compute lightweight temporal complexity surrogate, not canonical PCIst.

    Sums sign-transition count and mean active fraction of the channel-mean
    z-scored signal. This is a cheap proxy used for dataset-level scaffolding;
    it is not the canonical PCIst measure and must not be reported as one.
    """
    x = np.mean(epoch_2d, axis=0)
    z = (x - np.mean(x)) / (np.std(x) + 1e-12)
    b = (z > 0).astype(np.int8)
    transitions = np.sum(np.abs(np.diff(b)))
    active = np.mean(b)
    return float(transitions + active)


def pcist_surrogate(epoch_2d):
    """Deprecated alias for :func:`pcist_proxy`. Kept for backward compatibility."""
    return pcist_proxy(epoch_2d)


def _time_index(times_ms: np.ndarray, onset: float) -> int:
    """Index of the first sample >= onset."""
    return int(np.searchsorted(times_ms, onset, side="left"))


def _max_components_for_variance(eigenvalues: np.ndarray, max_var_pct: float) -> int:
    """Smallest component count whose cumulative variance reaches max_var_pct%."""
    if max_var_pct >= 100:
        return len(eigenvalues)
    order = np.argsort(eigenvalues)[::-1]
    var = eigenvalues[order] ** 2
    total = np.sum(var)
    if total <= 0:
        return len(eigenvalues)
    var_pct = 100.0 * var / total
    cum = np.cumsum(var_pct)
    n = int(np.searchsorted(cum, max_var_pct) + 1)
    return max(1, min(n, len(eigenvalues)))


def _state_transition_count(pairwise_distance: np.ndarray, threshold: float) -> float:
    """Number of recurrence-state flips along each row of a thresholded pairwise
    distance matrix, summed over all rows. A row is a fixed sample's recurrence
    relationship to every other sample in temporal order; a "flip" is where that
    relationship crosses the within/outside-threshold boundary between adjacent
    samples in the row.
    """
    recurrence = (pairwise_distance <= threshold).astype(np.int8)
    flips = np.abs(np.diff(recurrence, axis=1))
    return float(np.sum(flips))


def pcist(
    signal_evk: np.ndarray,
    times_ms: np.ndarray,
    baseline_window: tuple[float, float] = (-400.0, -50.0),
    response_window: tuple[float, float] = (0.0, 300.0),
    k: float = 1.2,
    min_snr: float = 1.1,
    max_var_pct: float = 99.0,
    n_steps: int = 100,
) -> float:
    """Perturbational Complexity Index, state-transition variant (PCIst).

    Independent implementation written from the algorithm described in
    Comolatti et al. 2019, "A fast and general method to empirically estimate
    the complexity of brain responses to transcranial and intracranial
    stimulations", Brain Stimulation. https://doi.org/10.1016/j.brs.2019.05.013
    (Written from the published method description, not derived from or
    copied from the authors' GPLv3-licensed reference implementation, to avoid
    pulling a copyleft dependency into this repository.)

    Unlike the original Casali et al. 2013 PCI (Lempel-Ziv complexity of a
    binarized significance matrix -- NOT what this function computes, despite
    similar naming in the wider literature), PCIst: (1) reduces the perturbation
    response to its principal SVD components explaining `max_var_pct`% of
    variance, keeping only components whose response:baseline power ratio
    exceeds `min_snr`; (2) for each retained component, at a range of
    thresholds, counts how often a recurrence relationship between time points
    "flips" (state transitions) in the response vs. a noise-scaled baseline,
    and keeps the threshold that maximizes their difference; (3) sums that
    maximal baseline-corrected transition count (scaled by response length)
    across components. This requires a real perturbation-evoked recording
    (e.g. TMS-EEG) with a genuine pre-stimulus baseline -- it is not meaningful
    on resting-state EEG with no stimulus onset, unlike the topology metrics
    elsewhere in this repo.

    Parameters
    ----------
    signal_evk : (n_channels, n_times) real signal.
    times_ms : (n_times,) timepoints in milliseconds; negative = pre-stimulus.
    baseline_window, response_window : (start_ms, end_ms) analysis windows.
    k : noise-control parameter; baseline transitions are scaled by k before
        subtracting from response transitions (paper default 1.2).
    min_snr : minimum response:baseline power ratio (sqrt) for a component to
        be retained (paper default 1.1).
    max_var_pct : cumulative variance threshold (%) for SVD component retention
        (paper default 99).
    n_steps : number of thresholds searched between the baseline distance
        matrix's median and the response distance matrix's max (paper default 100).

    Returns
    -------
    float
        PCIst value (>= 0). 0.0 if the input contains non-finite values, the
        windows are degenerate, no component passes the SNR filter, or the
        response never exceeds baseline-scaled transition activity at any
        searched threshold.
    """
    signal_evk = np.asarray(signal_evk, dtype=float)
    times_ms = np.asarray(times_ms, dtype=float)
    if signal_evk.ndim != 2 or signal_evk.shape[1] != times_ms.shape[0]:
        raise ValueError("signal_evk must be (n_channels, n_times) matching len(times_ms)")
    if np.any(~np.isfinite(signal_evk)):
        return 0.0

    base_ini, base_end = (_time_index(times_ms, t) for t in baseline_window)
    resp_ini, resp_end = (_time_index(times_ms, t) for t in response_window)
    if resp_end - resp_ini < 2 or base_end - base_ini < 2:
        return 0.0

    # --- SVD dimensionality reduction, basis fit on the response window ---
    response_samples = signal_evk[:, resp_ini:resp_end].T  # (n_resp_samples, n_channels)
    try:
        _, singular_values, vt = np.linalg.svd(response_samples, full_matrices=False)
    except np.linalg.LinAlgError:
        return 0.0
    n_components = _max_components_for_variance(singular_values, max_var_pct)
    basis = vt[:n_components, :]  # (n_components, n_channels)
    components = basis @ signal_evk  # (n_components, n_times), projected across the FULL signal

    base_power = np.mean(components[:, base_ini:base_end] ** 2, axis=1)
    resp_power = np.mean(components[:, resp_ini:resp_end] ** 2, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        snr = np.sqrt(resp_power / base_power)
    keep = np.isfinite(snr) & (snr > min_snr)
    components = components[keep, :]
    if components.shape[0] == 0:
        return 0.0

    # --- state-transition quantification, per retained component ---
    total = 0.0
    for comp in components:
        base_seg = comp[base_ini:base_end]
        resp_seg = comp[resp_ini:resp_end]
        n_base, n_resp = len(base_seg), len(resp_seg)

        d_base = np.abs(base_seg[:, None] - base_seg[None, :])
        d_resp = np.abs(resp_seg[:, None] - resp_seg[None, :])

        low = np.median(d_base)
        high = np.max(d_resp)
        if not np.isfinite(high) or high <= low:
            continue
        thresholds = np.linspace(low, high, n_steps)

        best_diff = 0.0  # only positive diffs matter: a negative best is clipped to 0 either way
        for thr in thresholds:
            nst_base = _state_transition_count(d_base, thr) / (n_base ** 2)
            nst_resp = _state_transition_count(d_resp, thr) / (n_resp ** 2)
            diff = nst_resp - k * nst_base
            if diff > best_diff:
                best_diff = diff
        total += best_diff * n_resp

    return float(max(total, 0.0))


def q_pcist_correlation(df: pd.DataFrame):
    """Pearson r between Qabs and a PCI-like complexity column.

    Prefers the real ``pcist`` column (canonical, requires perturbation-evoked
    data), falls back to ``pcist_proxy`` (resting-state-safe surrogate), then
    legacy ``PCIst``. Returns NaNs when none of these columns are present.
    """
    if "Qabs" not in df.columns:
        return {"r": np.nan, "p": np.nan}
    if "pcist" in df.columns:
        col = "pcist"
    elif "pcist_proxy" in df.columns:
        col = "pcist_proxy"
    elif "PCIst" in df.columns:
        col = "PCIst"
    else:
        return {"r": np.nan, "p": np.nan}
    sub = df[["Qabs", col]].dropna()
    if len(sub) < 3:
        return {"r": np.nan, "p": np.nan, "n": int(len(sub))}
    r, p = pearsonr(sub["Qabs"], sub[col])
    return {"r": float(r), "p": float(p), "n": int(len(sub))}
