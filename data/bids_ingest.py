"""Real BIDS EEG ingestion using mne-bids (leverages maintained OSS, no hand-rolled parsing).

Two responsibilities, kept explicit:

1. `discover_bids_eeg(root)` — enumerate EEG recordings via `mne_bids.find_matching_paths`,
   returning records in the same shape the existing `inspect_ds005620_bids` inventory emits,
   so downstream Level-M / Level-T consumers do not change.

2. `read_window_signal(path, start_s, end_s, ...)` — open a recording with MNE and return the
   REAL samples for one time window as a 1-D array, for feature extraction.

Provenance is explicit: records discovered through `mne-bids` carry
`provenance="real_bids"`; the constrained filesystem fallback carries
`provenance="unvalidated_filesystem_fallback"` and must not be treated as a
validated BIDS inventory. Synthetic paths live elsewhere and are labelled
`synthetic_proxy`. This module never fabricates signal.
"""
from __future__ import annotations

from collections import OrderedDict as _OrderedDict
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

    Falls back to a filesystem candidate scan only if mne-bids raises on a
    non-standard tree. Fallback records are explicitly marked
    `unvalidated_filesystem_fallback`; filename-shaped entities are structural
    hints only and do not establish BIDS validation.
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
        for fpath in _iter_eeg_candidate_files(root_path):
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
                    provenance="unvalidated_filesystem_fallback",
                    is_eeg_candidate=True,
                )
            )
    return records


def _iter_eeg_candidate_files(root_path: Path):
    """Yield EEG files without walking every non-EEG object in the tree.

    Prefer BIDS `eeg/` directories. Only if none exist, glob by known EEG
    extensions — never an unbounded star glob of every file in the tree.
    """
    eeg_dirs = list(root_path.glob("sub-*/eeg")) + list(root_path.glob("sub-*/ses-*/eeg"))
    found = False
    if eeg_dirs:
        for directory in sorted(eeg_dirs):
            if not directory.is_dir():
                continue
            for fpath in sorted(directory.iterdir()):
                if fpath.is_file() and fpath.suffix.lower() in _EEG_EXTS:
                    found = True
                    yield fpath
        if found:
            return
    seen: set[Path] = set()
    for ext in _EEG_EXTS:
        for fpath in sorted(root_path.rglob(f"*{ext}")):
            if fpath.is_file() and fpath not in seen:
                seen.add(fpath)
                yield fpath


def inventory_from_records(dataset_id: str, records: list[BIDSEEGRecord]) -> dict:
    """Emit the `file_inventory.json` shape the existing Level-M window builder consumes."""
    subjects = sorted({r.subject_id for r in records if r.subject_id})
    provenance = (
        "unvalidated_filesystem_fallback"
        if any(r.provenance == "unvalidated_filesystem_fallback" for r in records)
        else "real_bids"
    )
    return {
        "dataset_id": dataset_id,
        "bids_root": None,
        "n_files": len(records),
        "n_subjects": len(subjects),
        "eeg_candidates": [asdict(r) for r in records],
        "provenance": provenance,
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
# is preprocess_raw() on a dedicated maxsize-1 preprocess cache populated via
# UNCACHED `_read_raw`, so it never corrupts a shared `_RAW_CACHE` instance.
_RAW_CACHE: "_OrderedDict[tuple, object]" = _OrderedDict()
_RAW_CACHE_MAXSIZE = 4
_WINDOW_CACHE: "_OrderedDict[tuple, np.ndarray]" = _OrderedDict()
# The Level M and Level T passes consume the same windows. Keep only a small,
# bounded sample cache so a subject stays disk-bounded without retaining a
# whole recording in memory.
_WINDOW_CACHE_MAXSIZE = 64
# At most one fully-preprocessed (preload=True) recording. Filtering the full
# continuous file before windowing is the edge-effect contract; caching that
# object avoids repeating the same full-recording filter per window without
# mutating the shared preload=False `_RAW_CACHE` instances.
_PREPROCESS_CACHE: "_OrderedDict[tuple, object]" = _OrderedDict()
_PREPROCESS_CACHE_MAXSIZE = 1


def _close_raw(raw) -> None:
    closer = getattr(raw, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass


def _file_identity(path: str) -> tuple[str, int, int] | None:
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return (str(path), int(st.st_mtime_ns), int(st.st_size))


def _preprocess_cache_key(preprocess: dict | None) -> tuple:
    if not preprocess:
        return ()
    return tuple(sorted((str(key), repr(value)) for key, value in preprocess.items()))


def _evict_raw_lru(cache: "_OrderedDict[tuple, object]", maxsize: int) -> None:
    while len(cache) > maxsize:
        _, evicted = cache.popitem(last=False)
        _close_raw(evicted)


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
    _evict_raw_lru(_RAW_CACHE, _RAW_CACHE_MAXSIZE)
    return raw


def _read_preprocessed_raw(path: str, preprocess: dict):
    """Filter a FRESH raw (never `_read_raw_cached`) and reuse it within bound.

    `preprocess_raw` mutates in place on the full recording. A dedicated
    maxsize-1 cache keeps that contract while avoiding N full-file filters
    for N windows of the same file.
    """
    ident = _file_identity(path)
    key = (*ident, _preprocess_cache_key(preprocess)) if ident is not None else None
    if key is not None:
        cached = _PREPROCESS_CACHE.get(key)
        if cached is not None:
            _PREPROCESS_CACHE.move_to_end(key)
            return cached
    raw = _read_raw(path)
    from data.preprocessing import preprocess_raw

    preprocess_raw(raw, **preprocess)
    if key is not None:
        _PREPROCESS_CACHE[key] = raw
        _PREPROCESS_CACHE.move_to_end(key)
        _evict_raw_lru(_PREPROCESS_CACHE, _PREPROCESS_CACHE_MAXSIZE)
    return raw


def clear_raw_cache() -> None:
    """Drop cached raws, preprocessed recordings, and window samples.

    Closes MNE file handles so the streaming loop can delete subject
    directories (especially on Windows) after the final consumer.
    """
    for raw in list(_RAW_CACHE.values()):
        _close_raw(raw)
    _RAW_CACHE.clear()
    for raw in list(_PREPROCESS_CACHE.values()):
        _close_raw(raw)
    _PREPROCESS_CACHE.clear()
    _WINDOW_CACHE.clear()


def release_recording(path: str) -> None:
    """Release cached objects for one recording after its final consumer."""
    path_s = str(path)
    for cache in (_RAW_CACHE, _PREPROCESS_CACHE):
        for key in [k for k in cache if k and k[0] == path_s]:
            _close_raw(cache.pop(key))
    for key in [k for k in _WINDOW_CACHE if k and k[0] == path_s]:
        _WINDOW_CACHE.pop(key, None)


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
    ident = _file_identity(path)
    cache_key = None
    if ident is not None:
        # Key by seconds so a cache hit does not require loading/filtering
        # the recording just to recover sfreq. Pick reduction stays outside
        # the cache (same as before): the stored array is (n_ch, n_samp).
        cache_key = (
            *ident,
            float(window_start_s),
            float(window_end_s),
            max_channels or 0,
            _preprocess_cache_key(preprocess),
        )
        cached = _WINDOW_CACHE.get(cache_key)
        if cached is not None:
            _WINDOW_CACHE.move_to_end(cache_key)
            return _reduce_window_pick(cached, pick)

    if preprocess is not None:
        # Mutating path: never share `_RAW_CACHE` instances. A dedicated
        # preprocess cache (maxsize 1) still calls `_read_raw` on miss.
        raw = _read_preprocessed_raw(path, preprocess)
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
    data = np.asarray(data, dtype=float)
    if cache_key is not None:
        _WINDOW_CACHE[cache_key] = data
        _WINDOW_CACHE.move_to_end(cache_key)
        while len(_WINDOW_CACHE) > _WINDOW_CACHE_MAXSIZE:
            _WINDOW_CACHE.popitem(last=False)
    return _reduce_window_pick(data, pick)


def _reduce_window_pick(data: np.ndarray, pick: str) -> np.ndarray:
    if pick == "all":
        return np.array(data, dtype=float, copy=True)
    if pick == "first":
        sig = data[0]
    else:
        sig = data.mean(axis=0)
    return np.asarray(sig, dtype=float)
