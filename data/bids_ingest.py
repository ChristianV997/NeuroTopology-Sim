"""Real BIDS EEG ingestion using mne-bids (leverages maintained OSS, no hand-rolled parsing).

Two responsibilities, kept explicit:

1. `discover_bids_eeg(root)` — enumerate EEG recordings via `mne_bids.find_matching_paths`,
   returning records in the same shape the existing `inspect_ds005620_bids` inventory emits,
   so downstream Level-M / Level-T consumers do not change.

2. `read_window_signal(path, start_s, end_s, ...)` — open a recording with MNE and return the
   REAL samples for one time window as a 1-D array, for feature extraction.

Provenance is explicit: records discovered through `mne-bids` carry
`provenance="real_bids"`; the constrained filesystem fallback carries
`provenance="unvalidated_filesystem_fallback"` (or `local_bids_unvalidated`) and must not be treated as a
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
            "or an explicitly planned bounded-access materialization."
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
            ents = _parse_bids_filename_entities(fpath.stem)
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
    subjects = sorted({r.subject_id for r in records if r.subject_id})
    provenances = {r.provenance for r in records}
    if provenances == {"real_bids"}:
        provenance = "real_bids"
    elif "local_bids_unvalidated" in provenances:
        provenance = "unvalidated_or_mixed"
    else:
        provenance = "unvalidated_filesystem_fallback"
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
    max_bytes: int | None = None,
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

    `max_bytes`, when set, bounds the float64 sample buffer before signal data
    are read. `None` preserves the legacy behavior for existing callers.
    """
    if max_bytes is not None and (
        isinstance(max_bytes, (bool, np.bool_))
        or not isinstance(max_bytes, (int, np.integer))
        or int(max_bytes) <= 0
    ):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_WINDOW,
            "max_bytes must be a positive integer",
        )
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
            if max_bytes is not None and int(cached.nbytes) > int(max_bytes):
                raise BIDSAdapterError(
                    BIDSAdapterErrorCode.INVALID_WINDOW,
                    f"cached window requires {int(cached.nbytes)} bytes, exceeds max_bytes={int(max_bytes)}",
                )
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
    if max_bytes is not None:
        required_bytes = (stop - start) * len(picks) * np.dtype(float).itemsize
        if required_bytes > int(max_bytes):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_WINDOW,
                f"window requires {required_bytes} bytes, exceeds max_bytes={int(max_bytes)}",
            )
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


# ---------------------------------------------------------------------------
# Provenance-preserving BIDS adapter (Batch 2)
# Metadata-first index + bounded window gate. Structure validation only —
# this adapter does not validate scientific truth.
# ---------------------------------------------------------------------------

import hashlib as _hashlib  # noqa: E402
import json as _json  # noqa: E402
import math as _math  # noqa: E402
import re as _re  # noqa: E402
from enum import Enum as _Enum  # noqa: E402
from typing import Any as _Any  # noqa: E402
from typing import Mapping as _Mapping  # noqa: E402
from typing import Tuple as _Tuple  # noqa: E402
from urllib.parse import urlsplit as _urlsplit  # noqa: E402

BIDS_ADAPTER_SCHEMA = "BIDSAdapterManifest.v1"
MAX_BOUNDED_WINDOW_SECONDS = 600.0
MAX_BOUNDED_WINDOW_BYTES = 64 * 1024 * 1024
# Sidecars / dataset_description are metadata, not recordings — bound parse size.
MAX_METADATA_JSON_BYTES = 1 * 1024 * 1024
_SHA256_HEX = _re.compile(r"^[0-9a-fA-F]{64}$")
_DATASET_ID_RE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class BIDSAdapterErrorCode(str, _Enum):
    NETWORK_DISABLED = "NETWORK_DISABLED"
    FULL_DATASET_REJECTED = "FULL_DATASET_REJECTED"
    UNRESTRICTED_REMOTE_REJECTED = "UNRESTRICTED_REMOTE_REJECTED"
    MISSING_LOCAL_OR_BOUNDED_WINDOW = "MISSING_LOCAL_OR_BOUNDED_WINDOW"
    INVALID_WINDOW = "INVALID_WINDOW"
    MISSING_SUBJECT_SESSION_RUN = "MISSING_SUBJECT_SESSION_RUN"
    AMBIGUOUS_CONDITION_LABEL = "AMBIGUOUS_CONDITION_LABEL"
    LABEL_INFERENCE_FORBIDDEN = "LABEL_INFERENCE_FORBIDDEN"
    INVALID_BIDS_STRUCTURE = "INVALID_BIDS_STRUCTURE"
    OPTIONAL_DEPENDENCY_UNAVAILABLE = "OPTIONAL_DEPENDENCY_UNAVAILABLE"
    CHECKSUM_UNKNOWN = "CHECKSUM_UNKNOWN"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"


class BIDSAdapterError(ValueError):
    """Fail-closed contract error for the provenance-preserving BIDS adapter."""

    def __init__(self, code: BIDSAdapterErrorCode | str, message: str) -> None:
        self.code = code.value if isinstance(code, BIDSAdapterErrorCode) else str(code)
        super().__init__(f"{self.code}: {message}")


_ENTITY_VAL_RE = _re.compile(r"^[a-zA-Z0-9]+$")


def _parse_bids_filename_entities(stem: str) -> dict[str, str]:
    ents: dict[str, str] = {}
    for part in stem.split("_"):
        if "-" not in part:
            continue
        key, val = part.split("-", 1)
        key = key.strip()
        val = val.strip()
        if key and val and _ENTITY_VAL_RE.fullmatch(key) and _ENTITY_VAL_RE.fullmatch(val):
            ents[key] = val
    return ents


def _finite_json_value(value: _Any, path: str = "$") -> _Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        fval = float(value)
        if not _math.isfinite(fval):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.MALFORMED_REQUEST,
                f"non-finite float at {path}",
            )
        return fval
    if isinstance(value, _Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return [_finite_json_value(v, f"{path}[*]") for v in sorted(value)]
    if isinstance(value, _Mapping):
        return {str(k): _finite_json_value(v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json_value(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _finite_json_value(getattr(value, name), f"{path}.{name}")
            for name in value.__dataclass_fields__
        }
    raise BIDSAdapterError(
        BIDSAdapterErrorCode.MALFORMED_REQUEST,
        f"unsupported JSON type at {path}: {type(value).__name__}",
    )


def serialize_bids_manifest(payload: _Mapping[str, _Any] | dict) -> str:
    """Strict finite JSON serialization (allow_nan=False)."""
    safe = _finite_json_value(dict(payload))
    return _json.dumps(safe, sort_keys=True, indent=2, allow_nan=False) + "\n"


def optional_dependency_status() -> dict[str, bool]:
    """Report optional BIDS tooling availability without importing side effects beyond probes."""
    status = {"mne_bids": False, "pybids": False, "bids_validator": False}
    try:
        import mne_bids  # noqa: F401

        status["mne_bids"] = True
    except Exception:
        pass
    try:
        import bids  # noqa: F401

        status["pybids"] = True
    except Exception:
        pass
    try:
        import bids_validator  # noqa: F401

        status["bids_validator"] = True
    except Exception:
        try:
            from bids_validator import BIDSValidator  # noqa: F401

            status["bids_validator"] = True
        except Exception:
            pass
    return status


@dataclass(frozen=True)
class BoundedWindowRequest:
    """Explicit bounded time window. Full-recording reads are not implied."""

    start_s: float
    end_s: float
    max_duration_s: float = MAX_BOUNDED_WINDOW_SECONDS
    max_bytes: int = MAX_BOUNDED_WINDOW_BYTES

    def validate(self) -> None:
        if (
            isinstance(self.start_s, (bool, np.bool_))
            or isinstance(self.end_s, (bool, np.bool_))
            or not isinstance(self.start_s, (int, float, np.number))
            or not isinstance(self.end_s, (int, float, np.number))
        ):
            raise BIDSAdapterError(BIDSAdapterErrorCode.INVALID_WINDOW, "window bounds must be numeric")
        if not _math.isfinite(float(self.start_s)) or not _math.isfinite(float(self.end_s)):
            raise BIDSAdapterError(BIDSAdapterErrorCode.INVALID_WINDOW, "window bounds must be finite")
        if (
            isinstance(self.max_duration_s, (bool, np.bool_))
            or not isinstance(self.max_duration_s, (int, float, np.number))
            or not _math.isfinite(float(self.max_duration_s))
            or float(self.max_duration_s) <= 0
            or float(self.max_duration_s) > MAX_BOUNDED_WINDOW_SECONDS
        ):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_WINDOW,
                f"max_duration_s must be finite and in (0, {MAX_BOUNDED_WINDOW_SECONDS}]",
            )
        if float(self.start_s) < 0 or float(self.end_s) <= float(self.start_s):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_WINDOW,
                f"invalid window [{self.start_s}, {self.end_s})",
            )
        duration = float(self.end_s) - float(self.start_s)
        if duration > float(self.max_duration_s):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_WINDOW,
                f"window duration {duration}s exceeds max_duration_s={self.max_duration_s}",
            )
        if (
            isinstance(self.max_bytes, (bool, np.bool_))
            or not isinstance(self.max_bytes, (int, np.integer))
            or int(self.max_bytes) <= 0
            or int(self.max_bytes) > MAX_BOUNDED_WINDOW_BYTES
        ):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_WINDOW,
                f"max_bytes must be in (0, {MAX_BOUNDED_WINDOW_BYTES}]",
            )


@dataclass(frozen=True)
class BIDSAccessRequest:
    """Access contract for metadata indexing or a single bounded window.

    Network is disabled by default. Full-dataset materialization is always
    rejected. Condition labels are accepted only from ``condition_manifest``.
    """

    dataset_id: str
    local_root: Optional[str] = None
    remote_uri: Optional[str] = None
    relative_path: Optional[str] = None
    window: Optional[BoundedWindowRequest] = None
    allow_network: bool = False
    allow_full_dataset: bool = False
    condition_manifest: Optional[_Mapping[str, _Any]] = None
    expected_checksum: Optional[str] = None
    require_subject: bool = False
    require_session: bool = False
    require_run: bool = False


@dataclass(frozen=True)
class BIDSIndexedRecording:
    """Metadata-only recording descriptor. Never invents condition labels."""

    relative_path: str
    subject_id: Optional[str]
    session_id: Optional[str]
    task: Optional[str]
    run: Optional[str]
    acquisition: Optional[str]
    datatype: Optional[str]
    montage: Optional[str]
    sampling_frequency_hz: Optional[float]
    condition_label: Optional[str]
    condition_label_source: str
    source_checksum: Optional[str]
    checksum_state: str
    provenance: str


def _normalize_dataset_id(dataset_id: str) -> str:
    if not isinstance(dataset_id, str):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "dataset_id must be a non-empty identifier using letters, numbers, '.', '_' or '-'",
        )
    value = dataset_id.strip()
    if not value or not _DATASET_ID_RE.fullmatch(value):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "dataset_id must be a non-empty identifier using letters, numbers, '.', '_' or '-'",
        )
    return value


def _redact_remote_uri(remote_uri: Optional[str]) -> Optional[str]:
    """Keep only the remote origin; never serialize credentials or URI paths."""
    if remote_uri is None:
        return None
    try:
        parsed = _urlsplit(remote_uri)
        host = parsed.hostname
        if not parsed.scheme or not host:
            return "<redacted>"
        safe_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        port = parsed.port
        authority = f"{safe_host}:{port}" if port is not None else safe_host
        return f"{parsed.scheme.lower()}://{authority}"
    except (TypeError, ValueError):
        return "<redacted>"


def _normalize_checksum(value: Optional[str]) -> tuple[Optional[str], str]:
    if value is None or value == "":
        return None, "unknown"
    if not isinstance(value, str):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "expected_checksum must be a 64-char sha256 hex digest or unknown",
        )
    text = value.strip().lower()
    if text in {"unknown", "null", "none"}:
        return None, "unknown"
    if not _SHA256_HEX.fullmatch(text):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "expected_checksum must be a 64-char sha256 hex digest or unknown",
        )
    return text, "declared"


def _file_checksum_or_unknown(path: Path) -> tuple[Optional[str], str]:
    if not path.is_file():
        return None, "unknown"
    try:
        digest = _hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest(), "computed_local"
    except OSError:
        return None, "unknown"


def _read_json_object(path: Path) -> dict[str, _Any]:
    try:
        size = path.stat().st_size
    except OSError:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
            f"unreadable JSON at {path.name}",
        ) from None
    if size > MAX_METADATA_JSON_BYTES:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
            f"metadata JSON {path.name} is oversized (>{MAX_METADATA_JSON_BYTES} bytes)",
        )
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_METADATA_JSON_BYTES + 1)
        if len(raw) > MAX_METADATA_JSON_BYTES:
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
                f"metadata JSON {path.name} is oversized (>{MAX_METADATA_JSON_BYTES} bytes)",
            )
        payload = _json.loads(raw.decode("utf-8"))
    except BIDSAdapterError:
        raise
    except (OSError, UnicodeDecodeError, _json.JSONDecodeError):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
            f"unreadable JSON at {path.name}",
        ) from None
    if not isinstance(payload, dict):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
            f"{path.name} must be a JSON object",
        )
    return payload


def _validate_metadata_json_sizes(root: Path) -> None:
    """Bound every JSON sidecar before optional indexers can parse it."""
    resolved_root = root.resolve()
    try:
        metadata_paths = sorted(root.rglob("*.json"))
    except (OSError, RuntimeError):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
            "cannot enumerate BIDS metadata JSON files",
        ) from None
    for path in metadata_paths:
        if not path.is_file():
            continue
        try:
            if not path.resolve().is_relative_to(resolved_root):
                raise BIDSAdapterError(
                    BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
                    f"metadata JSON {path.name} escapes local_root",
                )
            size = path.stat().st_size
        except BIDSAdapterError:
            raise
        except (OSError, RuntimeError):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
                f"unreadable JSON at {path.name}",
            ) from None
        if size > MAX_METADATA_JSON_BYTES:
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
                f"metadata JSON {path.name} is oversized (>{MAX_METADATA_JSON_BYTES} bytes)",
            )


def _structural_bids_validation(root: Path) -> dict[str, _Any]:
    """Lightweight structural checks; optional bids-validator when installed."""
    _validate_metadata_json_sizes(root)
    issues: list[str] = []
    description_path = root / "dataset_description.json"
    if not description_path.is_file():
        issues.append("missing dataset_description.json")
        description: dict[str, _Any] = {}
    else:
        description = _read_json_object(description_path)
        name_val = description.get("Name") if "Name" in description else description.get("name")
        if not isinstance(name_val, str) or not name_val.strip():
            issues.append("dataset_description.json missing Name")
        ver_val = (
            description.get("BIDSVersion")
            if "BIDSVersion" in description
            else description.get("bids_version")
        )
        if not isinstance(ver_val, str) or not ver_val.strip():
            issues.append("dataset_description.json missing BIDSVersion")

    subjects = sorted(p.name for p in root.glob("sub-*") if p.is_dir() and len(p.name) > 4 and _ENTITY_VAL_RE.fullmatch(p.name[4:]))
    if not subjects:
        issues.append("no sub-* directories found")

    validator_backend = "structural"
    validator_available = False
    deps = optional_dependency_status()
    if deps["bids_validator"]:
        validator_available = True
        validator_backend = "bids_validator"
        # The Node/Python bids-validator APIs vary; treat availability as a
        # reported capability and keep structural findings authoritative here.
        try:
            import bids_validator as _bv  # noqa: F401
        except Exception:
            try:
                from bids_validator import BIDSValidator  # noqa: F401
            except Exception as exc:
                issues.append(f"bids_validator import failed: {exc}")
                validator_backend = "structural"

    status = "invalid" if issues else "valid_structure"
    return {
        "status": status,
        "backend": validator_backend,
        "validator_available": validator_available,
        "issues": issues,
        "n_subjects": len(subjects),
        "dataset_description_keys": sorted(description.keys()),
    }


def _pybids_query_index(root: Path) -> list[dict[str, _Any]] | None:
    """Query PyBIDS without materializing signal bytes. Returns None if unavailable."""
    try:
        from bids import BIDSLayout
    except Exception:
        return None
    layout = BIDSLayout(str(root), validate=False, index_metadata=False)
    rows: list[dict[str, _Any]] = []
    for entity in layout.get(datatype="eeg", return_type="object"):
        entities = getattr(entity, "entities", {}) or {}
        get_meta = getattr(entity, "get_metadata", None)
        meta = get_meta() if callable(get_meta) else {}
        if not isinstance(meta, dict):
            meta = {}
        rel = Path(entity.path).resolve().relative_to(root.resolve()).as_posix()
        rows.append(
            {
                "relative_path": rel,
                "subject_id": f"sub-{entities['subject']}" if entities.get("subject") else None,
                "session_id": f"ses-{entities['session']}" if entities.get("session") else None,
                "task": entities.get("task"),
                "run": str(entities["run"]) if entities.get("run") is not None else None,
                "acquisition": entities.get("acquisition"),
                "datatype": entities.get("datatype") or "eeg",
                "montage": meta.get("EEGReference") or meta.get("CapManufacturer"),
                "sampling_frequency_hz": meta.get("SamplingFrequency"),
                "provenance": "pybids_index",
            }
        )
    return rows


def _mne_bids_index(root: Path) -> list[dict[str, _Any]] | None:
    try:
        from mne_bids import find_matching_paths
    except Exception:
        return None
    rows: list[dict[str, _Any]] = []
    paths = find_matching_paths(root, datatypes=["eeg"], extensions=list(_EEG_EXTS))
    for bp in paths:
        fpath = Path(bp.fpath)
        if fpath.suffix.lower() not in _EEG_EXTS:
            continue
        rows.append(
            {
                "relative_path": fpath.resolve().relative_to(root.resolve()).as_posix(),
                "subject_id": f"sub-{bp.subject}" if bp.subject else None,
                "session_id": f"ses-{bp.session}" if bp.session else None,
                "task": bp.task,
                "run": str(bp.run) if bp.run is not None else None,
                "acquisition": getattr(bp, "acquisition", None),
                "datatype": "eeg",
                "montage": None,
                "sampling_frequency_hz": None,
                "provenance": "mne_bids_index",
            }
        )
    return rows


def _filesystem_metadata_index(root: Path) -> list[dict[str, _Any]]:
    """Structural index only. Filename entities are not condition labels."""
    rows: list[dict[str, _Any]] = []
    for fpath in _iter_eeg_candidate_files(root):
        rel = fpath.relative_to(root).as_posix()
        ents = _parse_bids_filename_entities(fpath.stem)
        rows.append(
            {
                "relative_path": rel,
                "subject_id": f"sub-{ents['sub']}" if "sub" in ents else None,
                "session_id": f"ses-{ents['ses']}" if "ses" in ents else None,
                "task": ents.get("task"),
                "run": ents.get("run"),
                "acquisition": ents.get("acq"),
                "datatype": "eeg",
                "montage": None,
                "sampling_frequency_hz": None,
                "provenance": "local_bids_unvalidated",
            }
        )
    return rows


def _condition_from_manifest(
    relative_path: str,
    *,
    subject_id: Optional[str],
    session_id: Optional[str],
    task: Optional[str],
    run: Optional[str],
    condition_manifest: Optional[_Mapping[str, _Any]],
) -> tuple[Optional[str], str]:
    """Return (label, source). Never infers from filenames alone."""
    if not condition_manifest:
        return None, "absent"
    recordings = condition_manifest.get("recordings")
    if recordings is None:
        if relative_path in condition_manifest:
            entry = condition_manifest[relative_path]
            if isinstance(entry, str):
                if not entry.strip():
                    return None, "absent"
                raise BIDSAdapterError(
                    BIDSAdapterErrorCode.LABEL_INFERENCE_FORBIDDEN,
                    f"flat condition label for {relative_path} lacks confirmed=true; use a recordings entry",
                )
            if not isinstance(entry, _Mapping):
                raise BIDSAdapterError(
                    BIDSAdapterErrorCode.AMBIGUOUS_CONDITION_LABEL,
                    f"condition entry for {relative_path} must be a string or object",
                )
            recordings = condition_manifest
        else:
            return None, "absent"
    elif not isinstance(recordings, _Mapping):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.AMBIGUOUS_CONDITION_LABEL,
            "condition_manifest.recordings must be an object keyed by relative_path",
        )
    if relative_path not in recordings:
        # Explicit confirmation required; missing entry is not filename inference.
        return None, "absent"
    entry = recordings[relative_path]
    if isinstance(entry, str):
        if not entry.strip():
            return None, "absent"
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.LABEL_INFERENCE_FORBIDDEN,
            f"condition label for {relative_path} lacks confirmed=true in manifest",
        )
    if not isinstance(entry, _Mapping):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.AMBIGUOUS_CONDITION_LABEL,
            f"condition entry for {relative_path} must be a string or object",
        )
    label = entry.get("condition_label") or entry.get("condition")
    if label is None or str(label).strip() == "":
        return None, "absent"
    confirmed = entry.get("confirmed")
    if confirmed is not True:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.LABEL_INFERENCE_FORBIDDEN,
            f"condition label for {relative_path} lacks confirmed=true in manifest",
        )
    # Optional consistency checks — reject ambiguous subject/session/run mismatches.
    for key, expected in (
        ("subject_id", subject_id),
        ("session_id", session_id),
        ("task", task),
        ("run", run),
    ):
        declared = entry.get(key)
        if declared is not None and expected is not None and str(declared) != str(expected):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.AMBIGUOUS_CONDITION_LABEL,
                f"condition manifest {key} mismatch for {relative_path}",
            )
    return str(label).strip(), "explicit_manifest"


def _validate_relative_path_lexical(relative_path: str) -> str:
    if not isinstance(relative_path, str):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "relative_path must be a string",
        )
    if "\x00" in relative_path:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "relative_path cannot contain null bytes",
        )
    rel_str = relative_path.strip().replace("\\", "/")
    if not rel_str or rel_str == ".":
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "relative_path cannot be empty or root",
        )
    if rel_str.startswith("/") or _re.match(r"^[A-Za-z]:", rel_str):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "relative_path must be a relative path inside the dataset root",
        )
    parts = [part for part in rel_str.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "relative_path must stay inside local_root",
        )
    return "/".join(parts)


def _require_contained_relative_path(local_root: str, relative_path: str) -> None:
    """Reject a relative_path that resolves outside local_root, symlinks included.

    Backslashes count as separators on every platform. resolve() reads path
    metadata only; no recording is opened here.
    """
    rel_str = _validate_relative_path_lexical(relative_path)
    root = Path(local_root).resolve()
    target = (root / rel_str).resolve()
    if target == root or not target.is_relative_to(root):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "relative_path must stay inside local_root",
        )


def enforce_bids_access_gate(request: BIDSAccessRequest) -> None:
    """Reject full-dataset and unrestricted remote requests before any I/O."""
    _normalize_dataset_id(request.dataset_id)
    if request.allow_full_dataset:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.FULL_DATASET_REJECTED,
            "full-dataset requests are rejected by the BIDS adapter contract",
        )
    if request.remote_uri and not request.allow_network:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.NETWORK_DISABLED,
            "network is disabled by default; pass allow_network=True only for an approved bounded window",
        )
    if request.remote_uri and request.window is None and not request.local_root:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.UNRESTRICTED_REMOTE_REJECTED,
            "remote access requires an explicit bounded window and relative_path",
        )
    if request.remote_uri and not request.relative_path:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.UNRESTRICTED_REMOTE_REJECTED,
            "remote access requires an explicit relative_path (no unrestricted listing/download)",
        )
    if not request.local_root and not (request.remote_uri and request.window and request.relative_path):
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MISSING_LOCAL_OR_BOUNDED_WINDOW,
            "provide an explicit local_root or a bounded approved remote window",
        )
    if request.relative_path is not None:
        if request.local_root:
            _require_contained_relative_path(request.local_root, request.relative_path)
        else:
            _validate_relative_path_lexical(request.relative_path)
    if request.window is not None:
        request.window.validate()
    if request.expected_checksum is not None:
        expected_checksum, _ = _normalize_checksum(request.expected_checksum)
        if expected_checksum is not None and not request.relative_path:
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.MALFORMED_REQUEST,
                "expected_checksum requires an explicit relative_path",
            )


def index_bids_metadata(request: BIDSAccessRequest) -> dict[str, _Any]:
    """Metadata-first BIDS index. Does not download datasets or load signal bytes."""
    enforce_bids_access_gate(request)
    if not request.local_root:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MISSING_LOCAL_OR_BOUNDED_WINDOW,
            "metadata indexing requires an explicit local_root (no remote full-tree crawl)",
        )
    root = Path(request.local_root)
    if not root.exists() or not root.is_dir():
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_BIDS_STRUCTURE,
            "local_root does not exist or is not a directory",
        )

    validation = _structural_bids_validation(root)
    deps = optional_dependency_status()
    rows = _pybids_query_index(root)
    index_backend = "pybids"
    if rows is None:
        rows = _mne_bids_index(root)
        index_backend = "mne_bids"
    if rows is None:
        rows = _filesystem_metadata_index(root)
        index_backend = "filesystem_structural"
        deps_missing = [name for name, ok in deps.items() if not ok]
        if deps_missing:
            # Optional deps absent is allowed; recorded explicitly.
            validation = dict(validation)
            validation = {
                **validation,
                "optional_dependency_note": (
                    "mne_bids/pybids unavailable; using structural filesystem index"
                ),
                "missing_optional_dependencies": deps_missing,
            }

    if validation["status"] == "invalid":
        # Still emit a deterministic manifest, but mark blocked.
        recordings: list[dict[str, _Any]] = []
        manifest = {
            "schema_version": BIDS_ADAPTER_SCHEMA,
            "dataset_id": _normalize_dataset_id(request.dataset_id),
            "local_root": "<redacted>",
            "access_mode": "metadata_only",
            "allow_network": False,
            "network_actions": [],
            "index_backend": index_backend,
            "optional_dependencies": deps,
            "bids_validation": validation,
            "recordings": recordings,
            "n_recordings": 0,
            "state": "BLOCKED_INVALID_BIDS",
            "scientific_pass": False,
            "limitation": (
                "This adapter validates BIDS structure; it does not validate scientific truth."
            ),
        }
        manifest["manifest_checksum"] = _hashlib.sha256(
            serialize_bids_manifest({k: v for k, v in manifest.items() if k != "manifest_checksum"}).encode("utf-8")
        ).hexdigest()
        return manifest

    recordings_out: list[BIDSIndexedRecording] = []
    matched_expected_checksum = False
    expected_checksum, _ = _normalize_checksum(request.expected_checksum)
    for row in sorted(rows, key=lambda item: item["relative_path"]):
        _require_contained_relative_path(str(root), row["relative_path"])
        if request.require_subject and not row.get("subject_id"):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.MISSING_SUBJECT_SESSION_RUN,
                f"missing subject_id for {row['relative_path']}",
            )
        if request.require_session and not row.get("session_id"):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.MISSING_SUBJECT_SESSION_RUN,
                f"missing session_id for {row['relative_path']}",
            )
        if request.require_run and not row.get("run"):
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.MISSING_SUBJECT_SESSION_RUN,
                f"missing run for {row['relative_path']}",
            )
        label, label_source = _condition_from_manifest(
            row["relative_path"],
            subject_id=row.get("subject_id"),
            session_id=row.get("session_id"),
            task=row.get("task"),
            run=row.get("run"),
            condition_manifest=request.condition_manifest,
        )
        abs_path = root / row["relative_path"]
        checksum: Optional[str] = None
        checksum_state = "unknown"
        if expected_checksum is not None and request.relative_path == row["relative_path"]:
            checksum, checksum_state = _file_checksum_or_unknown(abs_path)
            if checksum is None:
                raise BIDSAdapterError(
                    BIDSAdapterErrorCode.CHECKSUM_UNKNOWN,
                    f"cannot verify expected_checksum for {row['relative_path']}: file unreadable",
                )
            if expected_checksum.lower() != checksum.lower():
                raise BIDSAdapterError(
                    BIDSAdapterErrorCode.MALFORMED_REQUEST,
                    f"declared checksum does not match computed checksum for {row['relative_path']}",
                )
            matched_expected_checksum = True
        sfreq = row.get("sampling_frequency_hz")
        if isinstance(sfreq, (int, float)) and not _math.isfinite(float(sfreq)):
            sfreq = None
        recordings_out.append(
            BIDSIndexedRecording(
                relative_path=row["relative_path"],
                subject_id=row.get("subject_id"),
                session_id=row.get("session_id"),
                task=row.get("task"),
                run=row.get("run"),
                acquisition=row.get("acquisition"),
                datatype=row.get("datatype"),
                montage=row.get("montage"),
                sampling_frequency_hz=float(sfreq) if isinstance(sfreq, (int, float)) else None,
                condition_label=label,
                condition_label_source=label_source,
                source_checksum=checksum,
                checksum_state=checksum_state,
                provenance=str(row.get("provenance") or "local_bids_unvalidated"),
            )
        )

    if expected_checksum is not None and request.relative_path:
        if not matched_expected_checksum:
            raise BIDSAdapterError(
                BIDSAdapterErrorCode.MALFORMED_REQUEST,
                f"relative_path not found in indexed recordings: {request.relative_path}",
            )

    payload = {
        "schema_version": BIDS_ADAPTER_SCHEMA,
        "dataset_id": _normalize_dataset_id(request.dataset_id),
        "local_root": "<redacted>",
        "access_mode": "metadata_only",
        "allow_network": bool(request.allow_network),
        "network_actions": [],
        "index_backend": index_backend,
        "optional_dependencies": deps,
        "bids_validation": validation,
        "recordings": [asdict(item) for item in recordings_out],
        "n_recordings": len(recordings_out),
        "state": "METADATA_INDEXED",
        "scientific_pass": False,
        "limitation": (
            "This adapter validates BIDS structure; it does not validate scientific truth."
        ),
    }
    payload["manifest_checksum"] = _hashlib.sha256(
        serialize_bids_manifest({k: v for k, v in payload.items() if k != "manifest_checksum"}).encode("utf-8")
    ).hexdigest()
    return payload


def _verify_local_expected_checksum(request: BIDSAccessRequest) -> None:
    """When a local file is present, declared checksums must match before plan/read."""
    if (
        request.expected_checksum is None
        or not request.local_root
        or not request.relative_path
    ):
        return
    declared, _ = _normalize_checksum(request.expected_checksum)
    if declared is None:
        return
    _require_contained_relative_path(request.local_root, request.relative_path)
    path = Path(request.local_root) / request.relative_path
    if not path.is_file():
        return
    actual, _ = _file_checksum_or_unknown(path)
    if actual is None:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.CHECKSUM_UNKNOWN,
            f"cannot verify expected_checksum for {request.relative_path}: file unreadable",
        )
    if actual.lower() != declared.lower():
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            f"checksum mismatch for {request.relative_path}",
        )


def plan_bounded_window_access(request: BIDSAccessRequest) -> dict[str, _Any]:
    """Plan a single bounded window read. Never downloads a full dataset."""
    enforce_bids_access_gate(request)
    if request.window is None:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_WINDOW,
            "bounded window access requires an explicit window",
        )
    if not request.relative_path:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            "bounded window access requires relative_path",
        )
    _verify_local_expected_checksum(request)
    if request.remote_uri and request.allow_network:
        # Planning only — no network call is performed here.
        mode = "bounded_remote_plan"
        network_actions = [
            {
                "action": "planned_only",
                "uri": _redact_remote_uri(request.remote_uri),
                "relative_path": request.relative_path,
                "executed": False,
            }
        ]
    else:
        mode = "bounded_local"
        network_actions = []

    checksum, checksum_state = _normalize_checksum(request.expected_checksum)
    plan = {
        "schema_version": BIDS_ADAPTER_SCHEMA,
        "dataset_id": _normalize_dataset_id(request.dataset_id),
        "access_mode": mode,
        "local_root": "<redacted>" if request.local_root else None,
        "remote_uri": _redact_remote_uri(request.remote_uri),
        "relative_path": request.relative_path,
        "window": {
            "start_s": float(request.window.start_s),
            "end_s": float(request.window.end_s),
            "max_duration_s": float(request.window.max_duration_s),
            "max_bytes": int(request.window.max_bytes),
        },
        "allow_network": bool(request.allow_network),
        "network_actions": network_actions,
        "source_checksum": checksum,
        "checksum_state": checksum_state,
        "state": "WINDOW_PLANNED",
        "scientific_pass": False,
        "limitation": (
            "This adapter validates BIDS structure; it does not validate scientific truth."
        ),
    }
    plan["manifest_checksum"] = _hashlib.sha256(
        serialize_bids_manifest({k: v for k, v in plan.items() if k != "manifest_checksum"}).encode("utf-8")
    ).hexdigest()
    return plan


def read_bounded_window_lazy(
    request: BIDSAccessRequest, *, pick: str = "mean"
) -> _Tuple[dict[str, _Any], np.ndarray]:
    """Lazy local window read when a bounded window and local path are provided."""
    plan = plan_bounded_window_access(request)
    if not request.local_root:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MISSING_LOCAL_OR_BOUNDED_WINDOW,
            "lazy window read requires local_root; remote execution is plan-only in this adapter",
        )
    if request.window is None or request.relative_path is None:
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.INVALID_WINDOW,
            "bounded window and relative_path are required",
        )
    path = Path(request.local_root) / request.relative_path
    if not path.is_file():
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.MALFORMED_REQUEST,
            f"local recording not found: {request.relative_path}",
        )
    _verify_local_expected_checksum(request)
    samples = read_window_signal(
        str(path),
        float(request.window.start_s),
        float(request.window.end_s),
        pick=pick,
        max_bytes=int(request.window.max_bytes),
    )
    result = {
        **plan,
        "state": "WINDOW_READ_LOCAL",
        "n_samples": int(samples.shape[-1]) if hasattr(samples, "shape") else None,
        "sample_dtype": str(getattr(samples, "dtype", "unknown")),
        "signal_materialized": True,
        "scientific_pass": False,
    }
    # Do not embed raw samples in the manifest (provenance report only).
    result["manifest_checksum"] = _hashlib.sha256(
        serialize_bids_manifest({k: v for k, v in result.items() if k != "manifest_checksum"}).encode("utf-8")
    ).hexdigest()
    return result, samples
