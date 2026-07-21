"""Real BIDS EEG ingestion using mne-bids (leverages maintained OSS, no hand-rolled parsing).

Two responsibilities, kept explicit:

1. `discover_bids_eeg(root)` — enumerate EEG recordings via `mne_bids.find_matching_paths`,
   returning records in the same shape the existing `inspect_ds005620_bids` inventory emits,
   so downstream Level-M / Level-T consumers do not change.

2. `read_window_signal(path, start_s, end_s, ...)` — open a recording with MNE and return the
   REAL samples for one time window as a 1-D array, for feature extraction.

Provenance is explicit: every record carries `provenance="real_bids"`. Synthetic paths live
elsewhere and are labelled `synthetic_proxy`. This module never fabricates signal.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class BIDSEEGRecord:
    path: str
    relative_path: str
    subject_id: Optional[str]
    session_id: Optional[str]
    task_label: Optional[str]
    run_id: Optional[str]
    acq_label: Optional[str]
    extension: str
    is_eeg_candidate: bool
    provenance: str = "real_bids"


_EEG_EXTS = (".edf", ".bdf", ".set", ".vhdr", ".fif")


def discover_bids_eeg(root: str) -> list[BIDSEEGRecord]:
    """Discover EEG recordings under a BIDS root using mne-bids.

    Falls back to a filesystem glob only if mne-bids raises on a non-standard tree,
    so a slightly-off dataset still yields records instead of crashing the pipeline.
    """
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(
            f"BIDS root does not exist: {root}. Provide a local ds005620-style directory "
            f"(e.g. via `eegdash` cache or `aws s3 sync --no-sign-request s3://openneuro.org/ds005620`)."
        )

    records: list[BIDSEEGRecord] = []
    try:
        from mne_bids import find_matching_paths

        datatypes = ["eeg"]
        paths = find_matching_paths(root_path, datatypes=datatypes, extensions=list(_EEG_EXTS))
        for bp in paths:
            fpath = Path(bp.fpath)
            if fpath.suffix.lower() not in _EEG_EXTS:
                continue
            records.append(
                BIDSEEGRecord(
                    path=str(fpath),
                    relative_path=str(fpath.relative_to(root_path)),
                    subject_id=(f"sub-{bp.subject}" if bp.subject else None),
                    session_id=(f"ses-{bp.session}" if bp.session else None),
                    task_label=bp.task,
                    run_id=bp.run,
                    acq_label=getattr(bp, "acquisition", None),
                    extension=fpath.suffix.lower(),
                    provenance="real_bids",
                    is_eeg_candidate=True,
                )
            )
    except Exception:  # pragma: no cover - defensive fallback
        for fpath in sorted(root_path.rglob("*")):
            if fpath.suffix.lower() in _EEG_EXTS and fpath.is_file():
                rel = fpath.relative_to(root_path).as_posix()
                ents = {k: v for k, v in (part.split("-", 1) for part in fpath.stem.split("_") if "-" in part)}
                records.append(
                    BIDSEEGRecord(
                        path=str(fpath),
                        relative_path=rel,
                        subject_id=(f"sub-{ents['sub']}" if "sub" in ents else None),
                        session_id=(f"ses-{ents['ses']}" if "ses" in ents else None),
                        task_label=ents.get("task"),
                        run_id=ents.get("run"),
                        acq_label=ents.get("acq"),
                        extension=fpath.suffix.lower(),
                        provenance="real_bids",
                        is_eeg_candidate=True,
                    )
                )
    return records


def inventory_from_records(dataset_id: str, records: list[BIDSEEGRecord]) -> dict:
    """Emit the `file_inventory.json` shape the existing Level-M window builder consumes."""
    subjects = sorted({r.subject_id for r in records if r.subject_id})
    return {
        "dataset_id": dataset_id,
        "bids_root": None,
        "n_files": len(records),
        "n_subjects": len(subjects),
        "eeg_candidates": [asdict(r) for r in records],
        "provenance": "real_bids",
    }


def _read_raw(path: str):
    import mne

    p = Path(path)
    ext = p.suffix.lower()
    common = dict(preload=False, verbose="ERROR")
    if ext == ".fif":
        return mne.io.read_raw_fif(str(p), **common)
    if ext == ".edf":
        return mne.io.read_raw_edf(str(p), **common)
    if ext == ".bdf":
        return mne.io.read_raw_bdf(str(p), **common)
    if ext == ".set":
        return mne.io.read_raw_eeglab(str(p), **common)
    if ext == ".vhdr":
        return mne.io.read_raw_brainvision(str(p), **common)
    raise ValueError(f"Unsupported EEG extension for {path}: {ext}")


# ── Per-recording read cache (throughput) ─────────────────────────────────────
# Profiling a real streaming subject showed the recording's file header was
# re-parsed once PER WINDOW (mne's EEGLAB/BrainVision reader ~0.6s cumulative for
# a 10-window subject), because every read_window_signal / get_sample_rate /
# get_channel_names call did a fresh _read_raw. The same recording is read
# (max_windows_per_file) times on the Level-M pass and again on the Level-T pass
# -- so a single recording is parsed ~2*max_windows times. This bounded cache
# parses each recording once and hands the same preload=False raw to all
# non-mutating readers, keyed by (path, mtime, size) so a changed file is never
# served stale. It is byte-identical: get_data(picks, start, stop) on a
# preload=False raw reads the requested region deterministically from disk;
# nothing here changes the numbers, only how many times the header is parsed.
#
# CALLERS MUST NOT MUTATE a cached raw. The only in-place mutation in this module
# is preprocess_raw() in read_window_signal's `preprocess is not None` branch,
# which deliberately uses the UNCACHED _read_raw so it never corrupts a shared
# instance.
from collections import OrderedDict as _OrderedDict  # noqa: E402

_RAW_CACHE: "_OrderedDict[tuple, object]" = _OrderedDict()
_RAW_CACHE_MAXSIZE = 4


def _read_raw_cached(path: str):
    try:
        st = Path(path).stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return _read_raw(path)  # nonexistent/unreadable: let the real reader raise
    cached = _RAW_CACHE.get(key)
    if cached is not None:
        _RAW_CACHE.move_to_end(key)
        return cached
    raw = _read_raw(path)
    _RAW_CACHE[key] = raw
    _RAW_CACHE.move_to_end(key)
    while len(_RAW_CACHE) > _RAW_CACHE_MAXSIZE:
        _RAW_CACHE.popitem(last=False)
    return raw


def clear_raw_cache() -> None:
    """Drop all cached raws (frees the handful of parsed headers). Optional --
    the cache is bounded and holds preload=False raws (no signal data), so this
    is only needed to release file handles deterministically (e.g. right before
    deleting a subject's raw files in the streaming loop)."""
    _RAW_CACHE.clear()


def get_sample_rate(path: str) -> float:
    """Return the sampling rate (Hz) for an EEG recording without loading its data.

    `_read_raw` uses `preload=False`, so this only reads file metadata (header),
    not signal samples -- cheap enough to call once per window. Needed by any
    consumer that must know sfreq before filtering (e.g. band-specific
    Hilbert-phase extraction), which `read_window_signal` computes internally
    but does not expose.
    """
    raw = _read_raw_cached(path)
    return float(raw.info["sfreq"])


def get_channel_names(path: str, max_channels: int | None = None) -> list[str]:
    """Return real EEG channel names, in the same pick order
    `read_window_signal(pick="all")` uses -- needed by any consumer that must
    map channels to real electrode positions (e.g. montage-aware spatial
    topology), which `read_window_signal` does not expose (it returns bare
    sample arrays with no channel identity).
    """
    import mne

    raw = _read_raw_cached(path)
    picks = mne.pick_types(raw.info, eeg=True)
    if max_channels:
        picks = picks[:max_channels]
    return [raw.ch_names[i] for i in picks]


def get_recording_duration(path: str) -> float:
    """Return the full recording duration in seconds, without loading signal
    data (`_read_raw` uses `preload=False`). Needed by any consumer that
    operates on a full continuous recording rather than a fixed-length
    window (e.g. microstate segmentation, which needs a long enough stretch
    of data for modified K-means clustering to produce stable topographies).
    """
    raw = _read_raw_cached(path)
    return float(raw.n_times) / float(raw.info["sfreq"])


def read_window_signal(
    path: str,
    window_start_s: float,
    window_end_s: float,
    pick: str = "mean",
    max_channels: int | None = None,
    preprocess: dict | None = None,
) -> np.ndarray:
    """Return REAL samples for one window.

    pick="mean" averages across EEG channels (channel-agnostic Level-M proxy) and
    returns a 1-D array; pick="first" returns the first EEG channel, also 1-D.
    pick="all" returns every (up to max_channels) picked channel unreduced, as a 2-D
    (n_channels, n_samples) array, for consumers that need real per-channel structure
    (e.g. Level T topology, which needs inter-channel relationships that a channel-mean
    reduction destroys). Raises if the window is out of range.

    `preprocess`, if given, is a dict of kwargs forwarded to
    `data.preprocessing.preprocess_raw` (bandpass/notch/reference), applied to
    the FULL recording before this window is sliced out of it -- avoids the
    filter edge artifacts per-window filtering would introduce. Default
    `None` preserves this function's exact prior behavior (no filtering at
    all); every currently-published number was computed with `preprocess=None`.
    """
    if preprocess is not None:
        # Mutating path: preprocess_raw filters the raw in place, so it must NOT
        # share a cached instance -- read a fresh, uncached raw here.
        raw = _read_raw(path)
        from data.preprocessing import preprocess_raw

        preprocess_raw(raw, **preprocess)
    else:
        # Non-mutating path: reuse the per-recording cached raw (byte-identical;
        # only get_data/pick_types/info reads happen below).
        raw = _read_raw_cached(path)
    sfreq = float(raw.info["sfreq"])
    n_total = raw.n_times
    start = int(round(window_start_s * sfreq))
    stop = int(round(window_end_s * sfreq))
    if start < 0 or stop > n_total or stop <= start:
        raise ValueError(
            f"window [{window_start_s},{window_end_s}]s out of range for {Path(path).name} "
            f"(duration {n_total / sfreq:.2f}s)"
        )
    import mne

    try:
        picks = mne.pick_types(raw.info, eeg=True)
    except Exception as exc:  # pragma: no cover
        # Previously fell back to `picks = None`, which makes
        # `raw.get_data(picks=None)` return EVERY channel (EOG/ECG/stim/...),
        # silently blending non-EEG channels into what this function's
        # docstring promises are "REAL samples" of EEG signal -- and for
        # pick="mean" that contamination is invisible in the output. Found
        # during a repo-wide audit. Fail loudly instead (as a ValueError,
        # which every caller already handles via skip-and-report) rather
        # than return contaminated data disguised as clean EEG.
        raise ValueError(
            f"could not select EEG channels for {Path(path).name}: {exc}"
        ) from exc
    if max_channels:
        picks = picks[:max_channels]
    data = raw.get_data(picks=picks, start=start, stop=stop)  # (n_ch, n_samp), real load here
    if data.ndim == 1:
        data = data[None, :]
    if pick == "all":
        return np.asarray(data, dtype=float)
    if pick == "first":
        sig = data[0]
    else:
        sig = data.mean(axis=0)
    return np.asarray(sig, dtype=float)
