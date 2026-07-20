"""EEG validation pipeline (analytic-phase proxies).

Outputs long-format rows (one per file × window × band) with metadata-rich
columns. Each row is tagged with a ``metric_kind`` that distinguishes:

* ``analytic_phase_proxy``  — Hilbert analytic phase per band, gradient over
  channel order. A proxy, not a true spatial topology.
* ``temporal_phase_proxy``  — legacy direct ``np.angle`` path. Retained for
  backward comparison; not a valid neural phase field.
* ``null_channel_shuffle``  — null control: channel order permuted.
* ``null_time_reverse``     — null control: samples reversed.
* ``null_phase_randomized`` — null control: spectrum-preserving phase randomization.

Null rows are only emitted when ``compute_nulls=True`` (default: False).
They are controls for artifact sensitivity, not proof of validity.
"""
from __future__ import annotations

import hashlib
import re
import warnings
from pathlib import Path
from typing import Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from validation.analytic_phase import (
    DEFAULT_EEG_BANDS,
    analytic_phase_amplitude_by_band,
    analytic_phases_by_band,
    channel_phase_gradient_metrics,
    temporal_phase_proxy_metrics,
)
from validation.montage_topology import (
    get_channel_xy,
    phase_grid_topology_from_band,
    triangulate_xy,
)
from validation.nulls import channel_shuffle, phase_randomize_time, time_reverse
from validation.pci_validation import pcist_proxy

try:
    import mne
    MNE_AVAILABLE = True
except Exception:
    MNE_AVAILABLE = False

NUMERICAL_STABILITY_EPSILON = 1e-12
MIN_SEGMENT_SAMPLES = 8


# ── path metadata inference ──────────────────────────────────────────────────

_BIDS_TOKENS = {
    "subject_id": re.compile(r"sub-([A-Za-z0-9]+)"),
    "session_id": re.compile(r"ses-([A-Za-z0-9]+)"),
    "task": re.compile(r"task-([A-Za-z0-9]+)"),
    "run": re.compile(r"run-([A-Za-z0-9]+)"),
}

_STATE_KEYWORDS = (
    "awake", "wake", "sleep", "anesthesia", "loc", "roc",
    "seizure", "meditation",
)


def _infer_metadata(path: Path, dataset: str) -> dict:
    """Best-effort BIDS-like metadata inference from file path tokens.

    Missing fields fall back to the string ``"unknown"`` rather than blank so
    downstream consumers can rely on stable column types.
    """
    parts = path.as_posix()
    out: dict = {
        "dataset": dataset,
        "dataset_id": dataset,
        "subject_id": "unknown",
        "session_id": "unknown",
        "condition": "unknown",
        "state_label": "unknown",
    }
    for key, pat in _BIDS_TOKENS.items():
        m = pat.search(parts)
        if m:
            if key == "task":
                out["condition"] = m.group(1)
            elif key == "run":
                # store run as session suffix when no ses- present
                if out["session_id"] == "unknown":
                    out["session_id"] = f"run-{m.group(1)}"
            else:
                out[key] = m.group(1)

    if out["condition"] == "unknown":
        # Fall back to immediate parent directory name when meaningful
        parent = path.parent.name
        if parent and parent.lower() not in {"eeg", "raw", ""}:
            out["condition"] = parent

    lowered = parts.lower()
    for kw in _STATE_KEYWORDS:
        if kw in lowered:
            out["state_label"] = kw
            break
    return out


# ── MNE loading ──────────────────────────────────────────────────────────────

def _load_raw(path: Path):
    if not MNE_AVAILABLE:
        return None
    sfx = "".join(path.suffixes).lower()
    try:
        if sfx.endswith(".fif") or sfx.endswith(".fif.gz"):
            return mne.io.read_raw_fif(path.as_posix(), preload=True, verbose="ERROR")
        if sfx.endswith(".edf"):
            return mne.io.read_raw_edf(path.as_posix(), preload=True, verbose="ERROR")
        if sfx.endswith(".bdf"):
            return mne.io.read_raw_bdf(path.as_posix(), preload=True, verbose="ERROR")
        if sfx.endswith(".set"):
            return mne.io.read_raw_eeglab(path.as_posix(), preload=True, verbose="ERROR")
        if sfx.endswith(".vhdr"):
            return mne.io.read_raw_brainvision(path.as_posix(), preload=True, verbose="ERROR")
    except Exception as exc:
        # Previously a silent `except Exception: return None` -- the caller's
        # `if raw is None: continue` then dropped this file from the output
        # CSV entirely with no trace of which file failed or why. Found
        # during a repo-wide audit; a dataset with several corrupt/unreadable
        # files would silently produce a smaller-than-expected, unflagged
        # output. Warn instead of silently dropping.
        warnings.warn(f"run_eeg: failed to load {path}: {exc}", RuntimeWarning)
        return None
    return None


def _preprocess(raw):
    if raw is None:
        return None
    raw = raw.copy()
    # Each step is independently best-effort (a later dataset's raw object
    # may already lack, e.g., a re-referenceable channel set), but a failure
    # must be visible -- previously each `except Exception: pass` silently
    # let the row proceed through the rest of the pipeline computed on
    # unfiltered and/or non-EEG-picked data, with no way for a downstream
    # consumer to know that file's numbers were computed under different
    # (degraded) preprocessing than every other file in the same CSV. Found
    # during a repo-wide audit.
    for step_name, step in (
        ("load_data", lambda: raw.load_data()),
        ("pick_types", lambda: raw.pick_types(eeg=True, exclude=[])),
        ("filter", lambda: raw.filter(1, 40, fir_design="firwin", verbose="ERROR")),
        ("notch_filter", lambda: raw.notch_filter([50, 60], verbose="ERROR")),
        ("set_eeg_reference", lambda: raw.set_eeg_reference("average", projection=False, verbose="ERROR")),
    ):
        try:
            step()
        except Exception as exc:
            warnings.warn(f"run_eeg: preprocessing step {step_name!r} failed, "
                           f"continuing with degraded preprocessing: {exc}", RuntimeWarning)
    return raw


# ── per-window helpers ───────────────────────────────────────────────────────

def _spectral_ratio(seg: np.ndarray, sfreq: float) -> float:
    mean_sig = np.mean(seg, axis=0)
    fft = np.fft.rfft(mean_sig)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(mean_sig.size, d=1.0 / sfreq)
    low = power[(freqs >= 1) & (freqs < 8)].sum()
    high = power[(freqs >= 12) & (freqs <= 40)].sum()
    return float(high / (low + NUMERICAL_STABILITY_EPSILON))


def _stable_window_seed(file_path: Path, start: int, stop: int, base_seed: int) -> int:
    """Deterministic per-window seed using hashlib (stable across processes)."""
    payload = f"{file_path.as_posix()}:{start}:{stop}:{base_seed}".encode()
    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def _null_variants(seg: np.ndarray, seed: int) -> dict[str, np.ndarray]:
    """Return three deterministic null-control versions of an EEG segment."""
    return {
        "channel_shuffle": channel_shuffle(seg, seed=seed),
        "time_reverse": time_reverse(seg),
        "phase_randomized": phase_randomize_time(seg, seed=seed),
    }


_BASE_COLS: Tuple[str, ...] = (
    "dataset", "dataset_id", "file",
    "subject_id", "session_id", "condition", "state_label",
    "window_id", "start_sample", "stop_sample", "sfreq",
    "band", "metric_kind",
    "Q", "Qabs", "phase_grad", "f_dress", "spectral_ratio",
    "n_triangles", "n_valid_triangles", "defect_density",
    "null_method", "null_seed", "window_null_seed",
)


def _row_template(meta: dict, file_str: str, sfreq: float,
                  start: int, stop: int) -> dict:
    return {
        **meta,
        "file": file_str,
        "window_id": f"{Path(file_str).stem}:{start}:{stop}",
        "start_sample": start,
        "stop_sample": stop,
        "sfreq": float(sfreq),
    }


# ── public API ───────────────────────────────────────────────────────────────

def run(
    input_dir: str | Path,
    output_csv: str | Path,
    dataset: str,
    compute_pci: bool = False,
    bands: Optional[Mapping[str, Tuple[float, float]]] = None,
    include_legacy_proxy: bool = True,
    window_seconds: float = 4.0,
    step_seconds: float = 2.0,
    compute_phase_grid_topology: bool = False,
    montage: str | None = "standard_1020",
    amp_quantile: float | None = 0.1,
    compute_nulls: bool = False,
    null_seed: int = 0,
):
    """Run EEG analytic-phase feature extraction and save per-window-per-band rows.

    Parameters
    ----------
    input_dir, output_csv, dataset : as before.
    compute_pci : if True, attach ``pcist_proxy`` to every row of a window.
        For null rows, ``pcist_proxy`` is computed from the null-transformed
        segment, not copied from the observed segment.
    bands : optional override for the analytic-phase band table.
    include_legacy_proxy : if True, also emit one ``temporal_phase_proxy`` row
        per window with ``band="broadband"`` for backward comparison.
    window_seconds, step_seconds : window length and stride.
    compute_phase_grid_topology : if True, emit additional
        ``phase_grid_topology`` rows using montage-aware sensor geometry.
    montage : MNE montage name used to derive channel XY coordinates for
        ``phase_grid_topology`` rows.
    amp_quantile : optional quantile threshold used to mask low-amplitude
        triangle windows for ``phase_grid_topology`` rows.
    compute_nulls : if True, emit ``null_channel_shuffle``, ``null_time_reverse``,
        and ``null_phase_randomized`` rows alongside each ``analytic_phase_proxy``
        row. Default False; existing callers are unaffected.
    null_seed : base seed for deterministic null transforms; combined with
        per-window content via hashlib so each window gets a unique but
        reproducible seed. Stored verbatim in the ``null_seed`` column of null
        rows; the derived per-window seed is stored in ``window_null_seed``.

    Note: ``compute_nulls=True`` increases row count approximately 4× (each
    ``analytic_phase_proxy`` row gets three matched null rows). This runner
    accumulates rows in memory before writing CSV; long recordings should be
    chunked externally or processed per subject/session until streaming export
    is implemented.
    """
    input_dir = Path(input_dir)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    eeg_files: list[Path] = []
    for ext in ("*.edf", "*.fif", "*.bdf", "*.set", "*.vhdr"):
        eeg_files.extend(sorted(input_dir.rglob(ext)))

    base_cols = list(_BASE_COLS)
    if compute_pci:
        base_cols.append("pcist_proxy")

    for f in eeg_files:
        raw = _preprocess(_load_raw(f))
        if raw is None:
            continue
        sfreq = float(raw.info["sfreq"])
        meta = _infer_metadata(f, dataset)
        topo_idx = None
        topo_xy = None
        topo_tri = None
        if compute_phase_grid_topology:
            try:
                topo_names, topo_xy = get_channel_xy(raw, montage=montage)
                topo_tri = triangulate_xy(topo_xy)
                raw_names_l = [c.lower() for c in raw.ch_names]
                topo_idx = [raw_names_l.index(n.lower()) for n in topo_names]
            except Exception:
                topo_idx = None
        win = max(int(round(window_seconds * sfreq)), MIN_SEGMENT_SAMPLES)
        step = max(int(round(step_seconds * sfreq)), 1)
        if raw.n_times < win:
            continue
        for s in range(0, raw.n_times - win + 1, step):
            seg = raw.get_data(start=s, stop=s + win)
            if seg.shape[1] < MIN_SEGMENT_SAMPLES:
                continue

            tmpl = _row_template(meta, str(f), sfreq, s, s + win)
            spectral = _spectral_ratio(seg, sfreq)
            pci_val = pcist_proxy(seg) if compute_pci else None
            w_seed = _stable_window_seed(f, s, s + win, null_seed) if compute_nulls else 0

            # Pre-compute null phases ONCE per window, outside the band loop.
            # This avoids O(n_bands × 3) recomputations of _null_variants and
            # analytic_phases_by_band on the same null segments.
            null_phase_cache: dict[str, dict] = {}
            null_pci_cache: dict[str, Optional[float]] = {}
            if compute_nulls:
                for method, null_seg in _null_variants(seg, seed=w_seed).items():
                    null_phase_cache[method] = analytic_phases_by_band(
                        null_seg, sfreq, bands=bands
                    )
                    if compute_pci:
                        null_pci_cache[method] = pcist_proxy(null_seg)

            band_phases = analytic_phases_by_band(seg, sfreq, bands=bands)
            band_phase_amp = (
                analytic_phase_amplitude_by_band(seg, sfreq, bands=bands)
                if compute_phase_grid_topology
                else {}
            )
            for band_name, phase in band_phases.items():
                metrics = channel_phase_gradient_metrics(phase)
                row: dict = {
                    **tmpl,
                    "band": band_name,
                    "metric_kind": metrics["metric_kind"],
                    "Q": metrics["Q"],
                    "Qabs": metrics["Qabs"],
                    "phase_grad": metrics["phase_grad"],
                    "f_dress": metrics["f_dress"],
                    "spectral_ratio": spectral,
                    "n_triangles": np.nan,
                    "n_valid_triangles": np.nan,
                    "defect_density": np.nan,
                    "null_method": "",
                    "null_seed": "",
                    "window_null_seed": "",
                }
                if compute_pci:
                    row["pcist_proxy"] = pci_val
                rows.append(row)

                if compute_phase_grid_topology and topo_idx is not None and topo_tri is not None and band_name in band_phase_amp:
                    phase_band, amp_band = band_phase_amp[band_name]
                    try:
                        topo_metrics = phase_grid_topology_from_band(
                            phase_band[topo_idx, :],
                            topo_xy,
                            topo_tri,
                            amplitude=amp_band[topo_idx, :],
                            amp_quantile=amp_quantile,
                        )
                        topo_row = {
                            **tmpl,
                            "band": band_name,
                            "metric_kind": "phase_grid_topology",
                            "Q": topo_metrics["Q"],
                            "Qabs": topo_metrics["Qabs"],
                            "phase_grad": topo_metrics["phase_grad"],
                            "f_dress": topo_metrics["f_dress"],
                            "spectral_ratio": spectral,
                            "n_triangles": topo_metrics["n_triangles"],
                            "n_valid_triangles": topo_metrics["n_valid_triangles"],
                            "defect_density": topo_metrics["defect_density"],
                            "null_method": "",
                            "null_seed": "",
                            "window_null_seed": "",
                        }
                        if compute_pci:
                            topo_row["pcist_proxy"] = pci_val
                        rows.append(topo_row)
                    except Exception:
                        pass
                for method, null_band_phases in null_phase_cache.items():
                    if band_name not in null_band_phases:
                        continue
                    null_metrics = channel_phase_gradient_metrics(
                        null_band_phases[band_name]
                    )
                    null_row: dict = {
                        **tmpl,
                        "band": band_name,
                        "metric_kind": f"null_{method}",
                        "Q": null_metrics["Q"],
                        "Qabs": null_metrics["Qabs"],
                        "phase_grad": null_metrics["phase_grad"],
                        "f_dress": null_metrics["f_dress"],
                        "spectral_ratio": spectral,
                        "null_method": method,
                        "null_seed": null_seed,       # base seed argument
                        "window_null_seed": w_seed,   # sha256-derived per-window seed
                    }
                    if compute_pci:
                        null_row["pcist_proxy"] = null_pci_cache.get(method)
                    rows.append(null_row)

            if include_legacy_proxy:
                legacy = temporal_phase_proxy_metrics(seg)
                row = {
                    **tmpl,
                    "band": "broadband",
                    "metric_kind": legacy["metric_kind"],
                    "Q": legacy["Q"],
                    "Qabs": legacy["Qabs"],
                    "phase_grad": legacy["phase_grad"],
                    "f_dress": legacy["f_dress"],
                    "spectral_ratio": spectral,
                    "n_triangles": np.nan,
                    "n_valid_triangles": np.nan,
                    "defect_density": np.nan,
                    "null_method": "",
                    "null_seed": "",
                    "window_null_seed": "",
                }
                if compute_pci:
                    row["pcist_proxy"] = pci_val
                rows.append(row)

    df = pd.DataFrame(rows, columns=base_cols)
    df.to_csv(output_csv, index=False)
    return df
