"""Real Level M classical EEG features -- band-power (Welch PSD), nonlinear
complexity/entropy (antropy), and aperiodic 1/f spectral decomposition
(specparam) -- for the "beyond topology" instrumentation pass.

Additive, not a replacement: `sciencer_d/btc_icft/level_m/features.py`'s
`extract_level_m_features` computes `_proxy` metrics -- `spectral_power_proxy`
is raw time-domain mean-square amplitude (no FFT, no frequency decomposition
at all, despite the name); `entropy_proxy` is Shannon entropy of a histogram
of rounded raw amplitudes (not spectral or permutation entropy); `lzc_proxy`
is a nonstandard windowed-substring count over 1-4-sample windows (not real
Lempel-Ziv complexity). Those are kept as-is for traceability against the
three already-published dataset reports; this module adds real, textbook
implementations as new, clearly-named columns alongside them, following the
same additive pattern established for phase-based topology
(`sciencer_d/btc_icft/level_t/base_real_topology.py::compute_phase_based_topology_for_window`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

DEFAULT_BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma_low": (30.0, 45.0),
}


def compute_band_power(signal, sfreq: float, bands: dict | None = None) -> dict:
    """Real PSD-based absolute + relative band power via `scipy.signal.welch`
    -- the classic delta/theta/alpha/beta/gamma decomposition, absent from
    this repo's Level M features entirely before this module existed (no
    frequency-domain analysis of any kind was performed anywhere in the
    dataset-report pipeline).

    Returns `{"{band}_power_abs": ..., "{band}_power_rel": ...}` for each
    band whose upper edge is below Nyquist; a band that doesn't fit at this
    sfreq is silently omitted (not raised), matching this repo's existing
    per-band skip convention (`validation/analytic_phase.py`). Returns `{}`
    for a signal too short to estimate a PSD from at all.
    """
    from scipy.signal import welch

    bands = bands or DEFAULT_BANDS
    sig = np.asarray(signal, dtype=float)
    nperseg = min(len(sig), int(sfreq * 2))  # up to a 2s window for the PSD estimate
    if nperseg < 8:
        return {}

    freqs, psd = welch(sig, fs=sfreq, nperseg=nperseg)
    nyq = sfreq / 2.0
    total_power = float(np.trapezoid(psd, freqs)) if len(freqs) > 1 else 0.0

    result: dict[str, float] = {}
    for name, (lo, hi) in bands.items():
        if hi >= nyq:
            continue
        mask = (freqs >= lo) & (freqs < hi)
        band_power = float(np.trapezoid(psd[mask], freqs[mask])) if mask.sum() > 1 else 0.0
        result[f"{name}_power_abs"] = band_power
        result[f"{name}_power_rel"] = (band_power / total_power) if total_power > 0 else 0.0
    return result


def compute_complexity_features(signal) -> dict:
    """Real nonlinear complexity/entropy via `antropy`: normalized
    permutation entropy, sample entropy, Higuchi fractal dimension. Replaces
    nothing -- these are new columns alongside `entropy_proxy`/`lzc_proxy`.
    """
    import antropy as ant

    sig = np.asarray(signal, dtype=float)
    if len(sig) < 10:
        return {
            "permutation_entropy": float("nan"),
            "sample_entropy": float("nan"),
            "higuchi_fd": float("nan"),
        }
    return {
        "permutation_entropy": float(ant.perm_entropy(sig, normalize=True)),
        "sample_entropy": float(ant.sample_entropy(sig)),
        "higuchi_fd": float(ant.higuchi_fd(sig)),
    }


def compute_aperiodic_spectral_features(
    signal, sfreq: float, fit_range: tuple[float, float] = (1.0, 45.0),
) -> dict:
    """Real aperiodic (1/f) vs. oscillatory spectral decomposition via
    `specparam` (the current name for the tool historically called `fooof`).

    The aperiodic exponent tracks broadband "flattening" of the power
    spectrum -- increasingly used as an arousal/anesthesia-depth marker in
    the consciousness-state literature, directly relevant to ds005620's
    sedation question, and something this repo's Level M features never
    computed at all before this module (no frequency-domain decomposition of
    any kind existed).

    Returns NaN placeholders (not a raised exception) for a signal too short
    or too degenerate (e.g. all-constant, producing a non-fittable PSD) to
    fit reliably -- matches this repo's existing skip-and-report convention
    for unusable input.
    """
    from scipy.signal import welch
    from specparam import SpectralModel

    _nan_result = {
        "aperiodic_offset": float("nan"),
        "aperiodic_exponent": float("nan"),
        "aperiodic_r_squared": float("nan"),
    }

    sig = np.asarray(signal, dtype=float)
    nperseg = min(len(sig), int(sfreq * 2))
    if nperseg < 8:
        return _nan_result

    freqs, psd = welch(sig, fs=sfreq, nperseg=nperseg)
    nyq = sfreq / 2.0
    lo, hi = fit_range
    hi = min(hi, nyq - 1.0)
    mask = (freqs >= lo) & (freqs <= hi)
    if mask.sum() < 5 or not np.all(psd[mask] > 0):
        return _nan_result

    try:
        sm = SpectralModel(aperiodic_mode="fixed", verbose=False)
        sm.fit(freqs[mask], psd[mask])
        offset, exponent = sm.get_params("aperiodic")
        r_squared = float(sm.results.metrics.results.get("gof_rsquared", float("nan")))
    except Exception:
        return _nan_result

    return {
        "aperiodic_offset": float(offset),
        "aperiodic_exponent": float(exponent),
        "aperiodic_r_squared": r_squared,
    }


DFA_MIN_SAMPLES = 100
MFDFA_MIN_SAMPLES = 1000


def compute_dfa_features(signal) -> dict:
    """Real Detrended Fluctuation Analysis (DFA) scaling exponent (a Hurst-
    exponent proxy) via `antropy.detrended_fluctuation` -- long-range
    temporal correlation (LRTC), a genuine, published EEG-criticality
    measure (Hardstone et al. 2012, cited directly in `antropy`'s own
    docstring) with no prior instrument in this pipeline measuring temporal
    scaling at all (Phase 2's band power/complexity/aperiodic features are
    all frequency- or amplitude-domain, not scale-invariance measures).

    `antropy.detrended_fluctuation` does not raise on short input -- it
    silently returns exactly 0.0 below its effective minimum length
    (verified empirically: degenerate at n=50, recovers ~0.5 on random noise
    by n=100). This wrapper gates on `DFA_MIN_SAMPLES` explicitly rather than
    trusting that silent degenerate value, matching this repo's established
    skip-and-report convention.

    Report the raw `dfa_alpha` value only -- do not label any specific
    range "healthy," "critical," or a consciousness marker in report text;
    cite the literature's association and stop there.
    """
    import antropy as ant

    sig = np.asarray(signal, dtype=float)
    if len(sig) < DFA_MIN_SAMPLES:
        return {"dfa_alpha": float("nan")}
    return {"dfa_alpha": float(ant.detrended_fluctuation(sig))}


def compute_mfdfa_features(
    signal, q_range: tuple[float, float] = (-4.0, 4.0), n_q: int = 17,
) -> dict:
    """Real Multifractal Detrended Fluctuation Analysis via `MFDFA` -- the
    generalized Hurst exponent h(q) and the multifractal singularity
    spectrum width `Δα = α_max - α_min`, a measure of how much a signal's
    scaling behavior varies across large vs. small fluctuations (a single
    monofractal DFA exponent assumes uniform scaling; real neural signals
    often don't have it).

    Needs substantially more data than plain DFA to converge -- `MFDFA_MIN_SAMPLES`
    (1000) is a conservative floor, not a guarantee of a converged estimate;
    this repo's ~4-10s windows will mostly fail this gate at typical sample
    rates and return NaN-with-reason, which is the correct behavior, not a
    bug. Prefer running this against full-recording reads (the same pattern
    `sciencer_d/btc_icft/level_t/microstates.py::compute_microstates_for_recording`
    uses) rather than short windows where feasible.

    Returns NaN placeholders (not a raised exception) for input too short or
    too degenerate to fit -- matches this repo's established skip-and-report
    convention.
    """
    import MFDFA

    _nan_result = {"mfdfa_delta_alpha": float("nan"), "mfdfa_alpha_min": float("nan"), "mfdfa_alpha_max": float("nan")}

    sig = np.asarray(signal, dtype=float)
    if len(sig) < MFDFA_MIN_SAMPLES:
        return _nan_result

    q = np.linspace(q_range[0], q_range[1], n_q)
    q = q[q != 0]  # q=0 needs a separate log-averaging formula MFDFA doesn't take directly

    lag = np.unique(np.logspace(0.7, np.log10(len(sig) / 4), 30).astype(int))
    lag = lag[lag > 2]
    if len(lag) < 5:
        return _nan_result

    try:
        lag_out, fluctuation = MFDFA.MFDFA(sig, lag=lag, q=q)
        alpha, _f_alpha = MFDFA.singspect.singularity_spectrum(lag_out, fluctuation, q)
    except Exception:
        return _nan_result

    alpha = alpha[np.isfinite(alpha)]
    if len(alpha) < 2:
        return _nan_result

    return {
        "mfdfa_delta_alpha": float(alpha.max() - alpha.min()),
        "mfdfa_alpha_min": float(alpha.min()),
        "mfdfa_alpha_max": float(alpha.max()),
    }


def extract_real_level_m_features(signal, sfreq: float, bands: dict | None = None) -> dict:
    """All real Level M features for one window: band power, complexity,
    aperiodic spectral decomposition, DFA scaling exponent -- one call
    combining the helpers above, matching the single-dict shape callers
    expect from `sciencer_d/btc_icft/level_m/features.py::extract_level_m_features`
    while being entirely additive to it (new, separately-named keys; no
    overlap with the existing `_proxy` columns).

    `compute_mfdfa_features` is deliberately NOT included here -- its
    `MFDFA_MIN_SAMPLES` floor is far above what a single window typically
    provides, so bundling it into the default per-window call would return
    NaN in the overwhelming majority of cases. Call it directly on longer
    (ideally full-recording) signal instead.
    """
    result: dict[str, float] = {}
    result.update(compute_band_power(signal, sfreq, bands=bands))
    result.update(compute_complexity_features(signal))
    result.update(compute_aperiodic_spectral_features(signal, sfreq))
    result.update(compute_dfa_features(signal))
    return result


def compute_real_level_m_features_for_window(m_row: dict, bands: dict | None = None) -> dict:
    """Real Level M features (band power, complexity, aperiodic spectral
    decomposition) for one window, read from the actual per-channel signal
    (mean-reduced across channels, matching the existing `_proxy` convention
    in `sciencer_d/btc_icft/level_m/features.py`).

    Additive report function, not wired into any dataset's `LevelMWindowRow`
    dataclass/CSV -- keeps the three existing per-dataset row schemas, and
    every already-published report's columns, untouched (see this module's
    docstring). Returns a plain dict with `row_id`/`status`, matching the
    skip-and-report convention used throughout `level_t/base_real_topology.py`.
    """
    from data.bids_ingest import get_sample_rate, read_window_signal

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        sfreq = get_sample_rate(source_file)
        signal = read_window_signal(source_file, window_start_s, window_end_s, pick="mean")
    except ValueError as exc:
        return {"row_id": row_id, "status": "skipped", "reason": f"window skipped: {exc}"}

    feats = extract_real_level_m_features(signal, sfreq, bands=bands)
    return {"row_id": row_id, "status": "computed", "sfreq": sfreq, **feats}


def build_real_level_m_features_report(
    m_rows: list[dict], sample_size: int | None = None, seed: int = 0, bands: dict | None = None,
) -> dict:
    """Aggregate `compute_real_level_m_features_for_window` over (optionally
    a bounded sample of) `m_rows`. `sample_size=None` (default) gates every
    window -- this is a single Welch PSD + a handful of scalar fits per
    window, cheap enough not to need bounding by default, matching Phase 0's
    `build_phase_based_topology_report`.
    """
    candidate_rows = list(m_rows)
    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    results = [compute_real_level_m_features_for_window(r, bands=bands) for r in candidate_rows]
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    summary_keys: set[str] = set()
    for x in computed:
        summary_keys.update(k for k in x if k not in ("row_id", "status", "sfreq"))

    def _mean(key: str) -> float:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "status": "real_level_m_features_computed",
        "method": "welch_band_power + antropy_complexity + specparam_aperiodic + antropy_dfa",
        "n_windows_computed": len(computed),
        "n_windows_skipped": len(skipped),
        "n_windows_total_candidates": len(m_rows),
        "mean_by_feature": {k: _mean(k) for k in sorted(summary_keys)},
        "seed": seed,
        "sample_size": sample_size,
        "results": results,
    }


def compute_mfdfa_for_recording(
    source_file: str, max_channels: int | None = 16, max_duration_s: float | None = 120.0,
) -> dict:
    """Real multifractal DFA for one full recording (not a window -- see
    `compute_mfdfa_features`'s docstring: its minimum-sample floor is far
    above what a single window provides). Mirrors
    `sciencer_d/btc_icft/level_t/microstates.py::compute_microstates_for_recording`'s
    full-recording-read pattern (same rationale: this instrument needs a
    long, continuous stretch, not a short window).

    `max_duration_s` bounds compute cost the same way it does there --
    the first `max_duration_s` seconds of the recording are used by default
    (deterministic truncation, not a random subsample); `None` uses the full
    recording.
    """
    from data.bids_ingest import get_recording_duration, read_window_signal

    if not source_file or not Path(source_file).exists():
        return {"source_file": source_file, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        duration = get_recording_duration(source_file)
    except Exception as exc:
        return {"source_file": source_file, "status": "skipped", "reason": f"metadata read failed: {exc}"}

    window_end = duration if max_duration_s is None else min(duration, max_duration_s)
    try:
        signal = read_window_signal(source_file, 0.0, window_end, pick="mean", max_channels=max_channels)
    except ValueError as exc:
        return {"source_file": source_file, "status": "skipped", "reason": f"signal read failed: {exc}"}

    result = compute_mfdfa_features(signal)
    if not np.isfinite(result["mfdfa_delta_alpha"]):
        return {
            "source_file": source_file, "status": "skipped",
            "reason": f"too few samples for MFDFA (need >={MFDFA_MIN_SAMPLES}, "
                      f"got {len(np.asarray(signal))} at duration_used_s={window_end})",
        }

    return {"source_file": source_file, "status": "computed", "duration_used_s": window_end, **result}


def build_mfdfa_report(
    m_rows: list[dict], sample_size: int | None = 5, seed: int = 0,
    max_channels: int | None = 16, max_duration_s: float | None = 120.0,
) -> dict:
    """Aggregate `compute_mfdfa_for_recording` over unique recordings
    (`source_file` values) referenced by `m_rows` -- NOT per window row, same
    dedup convention as `microstates.py::build_microstate_report`.
    `sample_size` bounds the number of distinct RECORDINGS fit (real MFDFA is
    the most compute-heavy per-unit-of-data instrument this pipeline has,
    after microstate ModKMeans fitting), default 5.
    """
    unique_files = sorted({str(m.get("source_file")) for m in m_rows if m.get("source_file")})
    candidate_files = unique_files
    if sample_size is not None and len(candidate_files) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_files), size=sample_size, replace=False)
        candidate_files = [candidate_files[i] for i in sorted(idx)]

    results = [
        compute_mfdfa_for_recording(f, max_channels=max_channels, max_duration_s=max_duration_s)
        for f in candidate_files
    ]
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    def _mean(key: str) -> float:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "status": "mfdfa_computed",
        "method": "MFDFA singularity_spectrum (multifractal detrended fluctuation analysis), per-recording not per-window",
        "n_recordings_computed": len(computed),
        "n_recordings_skipped": len(skipped),
        "n_recordings_total_candidates": len(unique_files),
        "mean_delta_alpha": _mean("mfdfa_delta_alpha"),
        "seed": seed,
        "sample_size": sample_size,
        "max_duration_s": max_duration_s,
        "results": results,
    }
