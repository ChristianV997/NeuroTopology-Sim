"""Montage-aware spatial topology: real winding-number defects on a genuine
2D phase field built from real electrode positions.

This is the closest thing to what this repo's "q_net"/"q_abs"/"f_dress"
metrics have been named as if they meant all along. Neither
`sciencer_d/btc_icft/level_t/eeg_signal_topology.py::compute_topology_from_channels`
(channel-mean/correlation heuristic, Phase 2b's consolidation target) nor
Phase 0's `compute_phase_based_topology_for_window` (real band-specific
Hilbert phase, but treats channel order as an arbitrary 1D sequence via
`validation/analytic_phase.py::channel_phase_gradient_metrics` -- "not a
spatial topology", per that function's own docstring) compute topology on an
actual SPATIAL field. `validation/analytic_phase.py::phase_grid_topology_metrics`
already existed to do exactly this (real winding number via
`core.topology.plaquette_charge` on a true 2D grid) but was unusable on real
multi-channel EEG because nothing built the montage-interpolated grid it
needs. This module is that missing piece.

Circular interpolation, not linear: phase is an angle -- interpolating raw
angle values directly across the -pi/pi wraparound discontinuity would
create spurious gradients wherever the interpolation grid straddles that
boundary. This module interpolates cos(phase)/sin(phase) separately (both
continuous, no wraparound) and recovers the angle via atan2 -- the standard,
correct way to interpolate circular data.

2D projection caveat: electrode positions come from MNE's 3D montage
coordinates, projected here by simply dropping the z-axis (not MNE's own
azimuthal-equidistant topomap projection) -- a documented simplification,
not a claim of anatomical precision; adequate for detecting whether a
genuine spatial winding structure exists at all, which is the question this
module answers that the channel-order-only functions above cannot.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

DEFAULT_CANDIDATE_MONTAGES = ("standard_1020", "standard_1005", "biosemi64", "biosemi128", "biosemi32", "biosemi16")


def resolve_montage_positions(
    ch_names: list[str], candidate_montages: tuple[str, ...] = DEFAULT_CANDIDATE_MONTAGES,
) -> tuple[dict | None, str | None]:
    """Try each candidate montage in turn (case-insensitive channel-name
    match); return `(position_dict, montage_name)` for the first montage
    whose channel set is a superset of `ch_names`, or `(None, None)` if none
    match.

    Real BIDS EEG files read via `mne.io.read_raw_edf`/`read_raw_bdf`/etc
    (this repo's `data/bids_ingest.py::_read_raw`, not `mne_bids.read_raw_bids`)
    do not carry embedded 3D electrode coordinates even when a dataset's own
    `_electrodes.tsv` BIDS sidecar has them -- this function's fallback (match
    channel names against known standard layouts) is a deliberate, documented
    simplification: it assumes standard-compliant channel naming and returns
    `(None, None)` rather than guessing when that assumption doesn't hold.
    """
    import mne

    lower_ch = [c.lower() for c in ch_names]
    for name in candidate_montages:
        try:
            montage = mne.channels.make_standard_montage(name)
        except Exception:
            continue
        pos = montage.get_positions()["ch_pos"]
        lower_pos = {k.lower(): v for k, v in pos.items()}
        if all(c in lower_pos for c in lower_ch):
            return {ch: lower_pos[ch.lower()] for ch in ch_names}, name
    return None, None


def build_montage_phase_grid(
    ch_names: list[str], positions: dict, phase_values: np.ndarray, grid_size: int = 32,
) -> np.ndarray:
    """Interpolate per-channel phase values onto a regular 2D grid using real
    electrode positions.

    Parameters
    ----------
    ch_names : channel names, defining the row order of `phase_values`.
    positions : `{ch_name: (x, y, z)}`, e.g. from `resolve_montage_positions`.
    phase_values : shape `(n_channels,)` for a single time sample, or
        `(n_channels, n_samples)` for multiple.
    grid_size : the interpolation grid's side length (grid has
        `(grid_size-1) x (grid_size-1)` plaquettes once passed to
        `core.topology.plaquette_charge`).

    Returns
    -------
    `theta2d` of shape `(grid_size, grid_size)` for one sample, or
    `(n_samples, grid_size, grid_size)` for multiple -- directly consumable
    by `core.topology.plaquette_charge`/`compute_Q_slice`/`compute_Qabs_slice`
    (via `validation.analytic_phase.phase_grid_topology_metrics`).
    """
    from scipy.interpolate import griddata

    xy = np.array([positions[ch][:2] for ch in ch_names])  # drop z (see module docstring)

    xi = np.linspace(xy[:, 0].min(), xy[:, 0].max(), grid_size)
    yi = np.linspace(xy[:, 1].min(), xy[:, 1].max(), grid_size)
    grid_x, grid_y = np.meshgrid(xi, yi)

    def _interp_component(component_values: np.ndarray) -> np.ndarray:
        # Cubic interpolation is undefined (NaN) outside the convex hull of a
        # sparse electrode array -- with typical 10-20-style layouts, roughly
        # a quarter to a third of the rectangular bounding-box grid falls
        # outside that hull. A blind fill_value (e.g. 0.0) would silently
        # plant a fake "phase = 0 exactly" patch across that entire region,
        # which corrupts genuine winding structure whenever it lands near a
        # feature's core (verified empirically: it collapsed a real +1
        # vortex's detected charge to 0). Nearest-neighbor extrapolation for
        # exactly the NaN cells is the standard, defensible fix.
        cubic = griddata(xy, component_values, (grid_x, grid_y), method="cubic")
        nearest = griddata(xy, component_values, (grid_x, grid_y), method="nearest")
        return np.where(np.isnan(cubic), nearest, cubic)

    values = np.asarray(phase_values, dtype=float)
    single_sample = values.ndim == 1
    if single_sample:
        values = values[:, None]

    n_samples = values.shape[1]
    grids = np.zeros((n_samples, grid_size, grid_size))
    for t in range(n_samples):
        cos_interp = _interp_component(np.cos(values[:, t]))
        sin_interp = _interp_component(np.sin(values[:, t]))
        grids[t] = np.arctan2(sin_interp, cos_interp)

    return grids[0] if single_sample else grids


def compute_spatial_topology_for_window(
    m_row: dict, band: str = "alpha", max_channels: int | None = 16,
    grid_size: int = 24, n_time_samples: int = 10,
    candidate_montages: tuple[str, ...] = DEFAULT_CANDIDATE_MONTAGES,
) -> dict:
    """Real montage-aware spatial topology for one window: interpolates
    band-specific Hilbert phase onto a genuine 2D grid using real (or
    standard-matched) electrode positions, then computes winding-number
    Q/Qabs/f_dress via the canonical `core.topology.plaquette_charge`.

    `n_time_samples` bounds compute cost: interpolating a `grid_size x
    grid_size` grid via `griddata` for every sample in a window (often
    hundreds to thousands) would be far more expensive than any other
    instrument in this pipeline. Evenly-spaced subsampling within the window
    keeps this bounded and deterministic; results are averaged across the
    sampled time points (mean Q/Qabs/f_dress), not concatenated.

    Returns `{"status": "skipped", ...}` (not a raised exception) when the
    channel names don't match any known montage, there are too few channels
    for a meaningful 2x2+ plaquette grid, or the window can't be read --
    matching this repo's established skip-and-report convention.
    """
    from data.bids_ingest import get_channel_names, get_sample_rate, read_window_signal
    from validation.analytic_phase import DEFAULT_EEG_BANDS, bandpass_hilbert_phase, phase_grid_topology_metrics

    row_id = str(m_row.get("row_id"))
    source_file = str(m_row.get("source_file") or "")
    window_start_s = float(m_row.get("window_start_s") or 0.0)
    window_end_s = float(m_row.get("window_end_s") or 0.0)

    if band not in DEFAULT_EEG_BANDS:
        raise ValueError(f"Unknown band {band!r}; choose from {sorted(DEFAULT_EEG_BANDS)}")

    if not source_file or not Path(source_file).exists():
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"source file not found: {source_file!r}"}

    try:
        sfreq = get_sample_rate(source_file)
        ch_names = get_channel_names(source_file, max_channels=max_channels)
        channels = read_window_signal(
            source_file, window_start_s, window_end_s, pick="all", max_channels=max_channels
        )
    except (ValueError, OSError) as exc:
        # OSError: a companion file for a multi-file format (e.g. BrainVision
        # .vhdr/.eeg/.vmrk) can be genuinely missing even though the .vhdr
        # itself exists -- see level_t/base_real_topology.py's
        # compute_real_topology_for_window docstring for the real case this
        # was found on (ds003816).
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"window skipped: {exc}"}

    if channels.shape[0] != len(ch_names):
        ch_names = ch_names[: channels.shape[0]]

    positions, montage_name = resolve_montage_positions(ch_names, candidate_montages)
    if positions is None:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"no standard montage matched channel names (first few: {ch_names[:5]})",
        }

    if channels.shape[0] < 4:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"need >=4 channels for a meaningful spatial grid, got {channels.shape[0]}",
        }

    lo, hi = DEFAULT_EEG_BANDS[band]
    nyq = sfreq / 2.0
    if hi >= nyq:
        return {
            "row_id": row_id, "band": band, "status": "skipped",
            "reason": f"band {band} upper edge {hi} Hz >= Nyquist {nyq} Hz at sfreq={sfreq}",
        }

    try:
        phase = bandpass_hilbert_phase(channels, sfreq, lo, hi)  # (n_channels, n_samples)
    except ValueError as exc:
        return {"row_id": row_id, "band": band, "status": "skipped", "reason": f"phase extraction failed: {exc}"}

    n_available = phase.shape[1]
    n_take = min(n_time_samples, n_available)
    sample_idx = np.linspace(0, n_available - 1, n_take).round().astype(int)
    sampled_phase = phase[:, sample_idx]  # (n_channels, n_take)

    grids = build_montage_phase_grid(ch_names, positions, sampled_phase, grid_size=grid_size)  # (n_take, grid, grid)
    per_sample = [phase_grid_topology_metrics(grids[t]) for t in range(n_take)]

    def _mean(key: str) -> float:
        vals = [m[key] for m in per_sample if np.isfinite(m[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "row_id": row_id, "band": band, "status": "computed",
        "montage": montage_name, "n_channels": int(channels.shape[0]),
        "n_time_samples": n_take, "grid_size": grid_size,
        "Q": _mean("Q"), "Qabs": _mean("Qabs"),
        "phase_grad": _mean("phase_grad"), "f_dress": _mean("f_dress"),
    }


def build_spatial_topology_report(
    rows, m_rows: list[dict], band: str = "alpha", sample_size: int | None = 20, seed: int = 0,
    max_channels: int | None = 16, grid_size: int = 24, n_time_samples: int = 10,
) -> dict:
    """Aggregate `compute_spatial_topology_for_window` over (optionally a
    bounded sample of) rows.

    `sample_size` defaults to 20 (unlike Phase 0's phase-based topology
    report, which defaults to gating every window): montage resolution +
    per-time-sample `griddata` interpolation is meaningfully more expensive
    than a single bandpass+Hilbert transform, so this follows the surrogate
    null gate's bounded-by-default pattern instead.
    """
    by_id = {str(m.get("row_id")): m for m in m_rows}
    candidate_rows = [r for r in rows if r.row_id in by_id]

    if sample_size is not None and len(candidate_rows) > sample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(candidate_rows), size=sample_size, replace=False)
        candidate_rows = [candidate_rows[i] for i in sorted(idx)]

    results = [
        compute_spatial_topology_for_window(
            by_id[r.row_id], band=band, max_channels=max_channels,
            grid_size=grid_size, n_time_samples=n_time_samples,
        )
        for r in candidate_rows
    ]
    computed = [x for x in results if x["status"] == "computed"]
    skipped = [x for x in results if x["status"] != "computed"]

    def _mean(key: str) -> float:
        vals = [x[key] for x in computed if key in x and np.isfinite(x[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "status": "spatial_topology_computed",
        "band": band,
        "method": "montage_phase_grid (circular interpolation of real electrode positions) + core.topology.plaquette_charge",
        "n_windows_computed": len(computed),
        "n_windows_skipped": len(skipped),
        "n_windows_total_candidates": len(rows),
        "mean_Q": _mean("Q"),
        "mean_Qabs": _mean("Qabs"),
        "mean_phase_grad": _mean("phase_grad"),
        "mean_f_dress": _mean("f_dress"),
        "seed": seed,
        "sample_size": sample_size,
        "results": results,
    }
