"""Real microstate analysis via `pycrostates` -- canonical A/B/C/D-style EEG
microstate segmentation (modified K-means clustering of GFP-peak
topographies) plus summary measures (per-state mean spatial correlation,
global explained variance, occurrence rate, time coverage, mean duration).

Unlike every other Phase 0-4 addition in this pass, microstate analysis
operates on a FULL CONTINUOUS RECORDING, not a single short window: modified
K-means clustering needs enough GFP peaks across a reasonably long stretch
to produce stable cluster topographies -- the ~4-10s windows this repo's
Level M/T pipeline otherwise operates on are too short for reliable
microstate fitting. This module therefore groups by unique `source_file`
(recording), not by window `row_id`.

Uses `pycrostates` (BSD-3, Frindin et al., *JOSS* 2021), the maintained,
published implementation -- not a custom reimplementation of modified
K-means microstate clustering.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from sciencer_d.btc_icft.level_t.spatial_topology import (
    DEFAULT_CANDIDATE_MONTAGES,
    resolve_montage_positions,
)


def _build_raw(ch_names: list[str], positions: dict, signal: np.ndarray, sfreq: float):
    import mne

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(signal, info, verbose="ERROR")
    dig = mne.channels.make_dig_montage(ch_pos=positions, coord_frame="head")
    raw.set_montage(dig, verbose="ERROR", on_missing="raise")
    raw.set_eeg_reference("average", verbose="ERROR")
    return raw


def fit_microstates(
    ch_names: list[str], positions: dict, signal: np.ndarray, sfreq: float,
    n_clusters: int = 4, n_init: int = 50, random_state: int = 42,
) -> dict:
    """Fit modified K-means microstate clusters on real multi-channel signal
    and compute per-state summary parameters via `pycrostates`.

    Returns `global_explained_variance` (fraction of GFP-peak topography
    variance the `n_clusters` cluster maps explain -- the standard headline
    microstate-fit-quality number) and `parameters`, a flat dict with keys
    like `"0_mean_corr"`, `"0_gev"`, `"0_occurrences"` (per second),
    `"0_timecov"` (fraction of the recording), `"0_meandurs"` (seconds), one
    set per cluster index, plus `"unlabeled"` (fraction of samples pycrostates
    couldn't confidently assign to any state).
    """
    from pycrostates.cluster import ModKMeans

    raw = _build_raw(ch_names, positions, signal, sfreq)
    km = ModKMeans(n_clusters=n_clusters, n_init=n_init, random_state=random_state)
    km.fit(raw, n_jobs=1, verbose="ERROR")
    segmentation = km.predict(raw, verbose="ERROR")
    params = segmentation.compute_parameters()

    return {
        "n_clusters": n_clusters,
        "global_explained_variance": float(km.GEV_),
        "parameters": {k: float(v) for k, v in params.items()},
    }


def compute_microstates_for_recording(
    source_file: str, max_channels: int | None = 16, n_clusters: int = 4,
    max_duration_s: float | None = 120.0, n_init: int = 50, random_state: int = 42,
    candidate_montages: tuple[str, ...] = DEFAULT_CANDIDATE_MONTAGES,
) -> dict:
    """Real microstate segmentation for one full recording (not a window --
    see module docstring).

    `max_duration_s` bounds compute (ModKMeans fitting cost grows with
    recording length): the first `max_duration_s` seconds of the recording
    are used by default -- a deterministic, documented truncation, not a
    random subsample. `None` uses the full recording.

    Returns `{"status": "skipped", ...}` (not a raised exception) when the
    file can't be read, channel names don't match any known montage, or
    there are too few channels -- matching this repo's established
    skip-and-report convention.
    """
    from data.bids_ingest import get_channel_names, get_recording_duration, get_sample_rate, read_window_signal

    if not source_file or not Path(source_file).exists():
        return {"source_file": source_file, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        sfreq = get_sample_rate(source_file)
        ch_names = get_channel_names(source_file, max_channels=max_channels)
        duration = get_recording_duration(source_file)
    except Exception as exc:
        return {"source_file": source_file, "status": "skipped", "reason": f"metadata read failed: {exc}"}

    if len(ch_names) < 4:
        return {
            "source_file": source_file, "status": "skipped",
            "reason": f"need >=4 channels for microstate topographies, got {len(ch_names)}",
        }

    positions, montage_name = resolve_montage_positions(ch_names, candidate_montages)
    if positions is None:
        return {
            "source_file": source_file, "status": "skipped",
            "reason": f"no standard montage matched channel names (first few: {ch_names[:5]})",
        }

    window_end = duration if max_duration_s is None else min(duration, max_duration_s)
    try:
        signal = read_window_signal(source_file, 0.0, window_end, pick="all", max_channels=max_channels)
    except ValueError as exc:
        return {"source_file": source_file, "status": "skipped", "reason": f"signal read failed: {exc}"}

    if signal.shape[0] != len(ch_names):
        ch_names = ch_names[: signal.shape[0]]
        positions = {ch: positions[ch] for ch in ch_names}

    try:
        result = fit_microstates(
            ch_names, positions, signal, sfreq,
            n_clusters=n_clusters, n_init=n_init, random_state=random_state,
        )
    except Exception as exc:
        return {"source_file": source_file, "status": "skipped", "reason": f"microstate fit failed: {exc}"}

    return {
        "source_file": source_file, "status": "computed", "montage": montage_name,
        "n_channels": len(ch_names), "duration_used_s": window_end,
        **result,
    }


def build_microstate_report(
    m_rows: list[dict], sample_size: int | None = 5, seed: int = 0,
    max_channels: int | None = 16, n_clusters: int = 4, max_duration_s: float | None = 120.0,
) -> dict:
    """Aggregate `compute_microstates_for_recording` over unique recordings
    (`source_file` values) referenced by `m_rows` -- NOT per window row,
    unlike every other report in this pass (see module docstring).

    `sample_size` bounds the number of distinct RECORDINGS fit (ModKMeans
    fitting is the most compute-per-unit-of-data-fit instrument in this
    pass), default 5 -- matching the surrogate null gate's bounded-by-default
    pattern rather than Phase 0's gate-everything-by-default pattern.
    """
    unique_files = sorted({str(m.get("source_file")) for m in m_rows if m.get("source_file")})
    candidate_files = unique_files
    if sample_size is not None and len(candidate_files) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_files), size=sample_size, replace=False)
        candidate_files = [candidate_files[i] for i in sorted(idx)]

    results = [
        compute_microstates_for_recording(
            f, max_channels=max_channels, n_clusters=n_clusters, max_duration_s=max_duration_s,
        )
        for f in candidate_files
    ]
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    mean_gev = (
        float(np.mean([x["global_explained_variance"] for x in computed])) if computed else float("nan")
    )

    return {
        "status": "microstates_computed",
        "method": "pycrostates ModKMeans (modified K-means on GFP-peak topographies), per-recording not per-window",
        "n_clusters": n_clusters,
        "n_recordings_computed": len(computed),
        "n_recordings_skipped": len(skipped),
        "n_recordings_total_candidates": len(unique_files),
        "mean_global_explained_variance": mean_gev,
        "seed": seed,
        "sample_size": sample_size,
        "max_duration_s": max_duration_s,
        "results": results,
    }
