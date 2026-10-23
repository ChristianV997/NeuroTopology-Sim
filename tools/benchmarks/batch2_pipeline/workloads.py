"""Seven synthetic Batch-2 targets modelling streaming/simulation bottlenecks.

Baseline = wasteful all-day pattern. Candidate = bounded strategy.
Both return the same deterministic checksum for a fixture. No production
modules are imported or patched.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .fixtures import make_fixture
from .telemetry import dir_size_bytes


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, allow_nan=False).encode("utf-8")
    ).hexdigest()[:16]


def _input_size(n_items: int, n_bytes: Optional[int] = None) -> Dict[str, Any]:
    return {"n_items": n_items, "bytes": n_bytes}


def _unpack(recording: bytes, n_channels: int) -> List[List[float]]:
    n_floats = len(recording) // 4
    values = list(struct.unpack(f"<{n_floats}f", recording))
    rows: List[List[float]] = []
    for i in range(0, n_floats, n_channels):
        rows.append(values[i : i + n_channels])
    return rows


def _window_checksum(rows: List[List[float]], start: int, stop: int) -> float:
    acc = 0.0
    for sample in rows[start:stop]:
        acc += sum(sample)
    return float(acc)


def _preprocess(rows: List[List[float]]) -> List[List[float]]:
    # Cheap deterministic "filter": scale + bias (models full-recording preprocess).
    return [[v * 0.5 + 0.01 for v in sample] for sample in rows]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    path_family: str
    make_fixture: Callable[[int, int], Dict[str, Any]]
    baseline: Callable[[Dict[str, Any]], Dict[str, Any]]
    candidate: Callable[[Dict[str, Any]], Dict[str, Any]]
    default_size: int = 16


# --------------------------------------------------------------------------- #
# 1. Full-recording re-read every window
# --------------------------------------------------------------------------- #
def _reread_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    recording = fx["recording"]
    n_channels = fx["n_channels"]
    digests = []
    read_counts = 0
    for win in fx["windows"]:
        # Re-unpack the entire recording for every window (all-day anti-pattern).
        rows = _unpack(recording, n_channels)
        read_counts += 1
        digests.append(_window_checksum(rows, win["start"], win["stop"]))
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": read_counts,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": len(fx["windows"]),
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(fx["n_windows"], len(recording)),
        "production_module": "synthetic.full_recording_reread",
        "production_available": False,
    }


def _reread_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    recording = fx["recording"]
    n_channels = fx["n_channels"]
    rows = _unpack(recording, n_channels)  # single materialization
    digests = []
    for win in fx["windows"]:
        digests.append(_window_checksum(rows, win["start"], win["stop"]))
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 1,
        "preprocess_calls": 0,
        "cache_hits": len(fx["windows"]) - 1,
        "cache_misses": 1,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(fx["n_windows"], len(recording)),
        "production_module": "synthetic.full_recording_reread",
        "production_available": False,
    }


# --------------------------------------------------------------------------- #
# 2. Preprocess-full-recording per window
# --------------------------------------------------------------------------- #
def _preprocess_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    rows = _unpack(fx["recording"], fx["n_channels"])
    digests = []
    preprocess_calls = 0
    for win in fx["windows"]:
        filtered = _preprocess(rows)  # full-recording filter every window
        preprocess_calls += 1
        digests.append(_window_checksum(filtered, win["start"], win["stop"]))
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 1,
        "preprocess_calls": preprocess_calls,
        "cache_hits": 0,
        "cache_misses": len(fx["windows"]),
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(fx["n_windows"], len(fx["recording"])),
        "production_module": "synthetic.preprocess_per_window",
        "production_available": False,
    }


def _preprocess_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    rows = _unpack(fx["recording"], fx["n_channels"])
    filtered = _preprocess(rows)  # once
    digests = [
        _window_checksum(filtered, win["start"], win["stop"]) for win in fx["windows"]
    ]
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 1,
        "preprocess_calls": 1,
        "cache_hits": len(fx["windows"]) - 1,
        "cache_misses": 1,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(fx["n_windows"], len(fx["recording"])),
        "production_module": "synthetic.preprocess_per_window",
        "production_available": False,
    }


# --------------------------------------------------------------------------- #
# 3. Checkpoint/fsync overhead separated from process work
# --------------------------------------------------------------------------- #
def _checkpoint_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    """Naive: fsync after every subject (checkpoint cost mixed into process)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = root / "manifest.json"
        digests = []
        fsync_calls = 0
        process_work = 0.0
        checkpoint = 0.0
        for subject in fx["subjects"]:
            t0 = time.perf_counter()
            payload = {"subject": subject, "seed": fx["seed"], "size": fx["size"]}
            digests.append(_stable_hash(payload))
            process_work += time.perf_counter() - t0
            t1 = time.perf_counter()
            text = json.dumps({"processed": digests}, allow_nan=False)
            with manifest.open("w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            fsync_calls += 1
            checkpoint += time.perf_counter() - t1
        disk = dir_size_bytes(root)
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 0,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": len(fx["subjects"]),
        "fsync_calls": fsync_calls,
        "process_work_s": process_work,
        "checkpoint_s": checkpoint,
        "worker_count": 1,
        "disk_bytes": disk,
        "input_size": _input_size(len(fx["subjects"])),
        "production_module": "synthetic.checkpoint_fsync_overhead",
        "production_available": False,
    }


def _checkpoint_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    """Bounded: process all subjects, then one atomic fsync checkpoint."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest = root / "manifest.json"
        digests = []
        process_work = 0.0
        for subject in fx["subjects"]:
            t0 = time.perf_counter()
            payload = {"subject": subject, "seed": fx["seed"], "size": fx["size"]}
            digests.append(_stable_hash(payload))
            process_work += time.perf_counter() - t0
        t1 = time.perf_counter()
        text = json.dumps({"processed": digests}, allow_nan=False)
        tmp_path = manifest.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, manifest)
        checkpoint = time.perf_counter() - t1
        disk = dir_size_bytes(root)
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 0,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": 1,
        "fsync_calls": 1,
        "process_work_s": process_work,
        "checkpoint_s": checkpoint,
        "worker_count": 1,
        "disk_bytes": disk,
        "input_size": _input_size(len(fx["subjects"])),
        "production_module": "synthetic.checkpoint_fsync_overhead",
        "production_available": False,
    }


# --------------------------------------------------------------------------- #
# 4. Manifest write amplification
# --------------------------------------------------------------------------- #
def _manifest_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "manifest.json"
        entries = []
        writes = 0
        fsync_calls = 0
        for item in fx["manifest_items"]:
            entries.append({"id": item["id"], "sha256": hashlib.sha256(item["payload"]).hexdigest()})
            with path.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(entries, allow_nan=False))
                handle.flush()
                os.fsync(handle.fileno())
            writes += 1
            fsync_calls += 1
        disk = dir_size_bytes(root)
        checksum = _stable_hash(entries)
    return {
        "checksum": checksum,
        "feature_count": len(entries),
        "read_counts": 0,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": writes,
        "fsync_calls": fsync_calls,
        "worker_count": 1,
        "disk_bytes": disk,
        "input_size": _input_size(len(fx["manifest_items"])),
        "production_module": "synthetic.manifest_write_amplification",
        "production_available": False,
    }


def _manifest_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "manifest.json"
        entries = [
            {"id": item["id"], "sha256": hashlib.sha256(item["payload"]).hexdigest()}
            for item in fx["manifest_items"]
        ]
        with path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(entries, allow_nan=False))
            handle.flush()
            os.fsync(handle.fileno())
        disk = dir_size_bytes(root)
        checksum = _stable_hash(entries)
    return {
        "checksum": checksum,
        "feature_count": len(entries),
        "read_counts": 0,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": 1,
        "fsync_calls": 1,
        "worker_count": 1,
        "disk_bytes": disk,
        "input_size": _input_size(len(fx["manifest_items"])),
        "production_module": "synthetic.manifest_write_amplification",
        "production_available": False,
    }


# --------------------------------------------------------------------------- #
# 5. Window cache hits vs always-miss
# --------------------------------------------------------------------------- #
def _cache_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    rows = _unpack(fx["recording"], fx["n_channels"])
    digests = []
    misses = 0
    # Visit windows twice; baseline never caches.
    for _pass in range(2):
        for win in fx["windows"]:
            digests.append(_window_checksum(rows, win["start"], win["stop"]))
            misses += 1
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 1,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": misses,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(fx["n_windows"] * 2, len(fx["recording"])),
        "production_module": "synthetic.window_cache_hits",
        "production_available": False,
    }


def _cache_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    rows = _unpack(fx["recording"], fx["n_channels"])
    cache: "OrderedDict[int, float]" = OrderedDict()
    digests = []
    hits = 0
    misses = 0
    for _pass in range(2):
        for win in fx["windows"]:
            key = int(win["index"])
            if key in cache:
                digests.append(cache[key])
                hits += 1
                cache.move_to_end(key)
            else:
                value = _window_checksum(rows, win["start"], win["stop"])
                digests.append(value)
                cache[key] = value
                misses += 1
                if len(cache) > fx["n_windows"]:
                    cache.popitem(last=False)
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 1,
        "preprocess_calls": 0,
        "cache_hits": hits,
        "cache_misses": misses,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(fx["n_windows"] * 2, len(fx["recording"])),
        "production_module": "synthetic.window_cache_hits",
        "production_available": False,
    }


# --------------------------------------------------------------------------- #
# 6. Subject-loop disk staging (.part growth)
# --------------------------------------------------------------------------- #
def _disk_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        digests = []
        for subject in fx["subjects"]:
            # Leave .part siblings behind (unbounded staging growth).
            part = root / f"{subject}.bin.part"
            final = root / f"{subject}.bin"
            payload = fx["recording"][: 256 + len(subject)]
            part.write_bytes(payload)
            final.write_bytes(payload)
            digests.append(hashlib.sha256(payload).hexdigest()[:16])
        disk = dir_size_bytes(root)
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": len(fx["subjects"]),
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": disk,
        "input_size": _input_size(len(fx["subjects"]), len(fx["recording"])),
        "production_module": "synthetic.subject_loop_disk_staging",
        "production_available": False,
    }


def _disk_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        digests = []
        for subject in fx["subjects"]:
            part = root / f"{subject}.bin.part"
            final = root / f"{subject}.bin"
            payload = fx["recording"][: 256 + len(subject)]
            part.write_bytes(payload)
            os.replace(part, final)  # atomic promote; no leftover .part
            digests.append(hashlib.sha256(payload).hexdigest()[:16])
        disk = dir_size_bytes(root)
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": len(fx["subjects"]),
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": disk,
        "input_size": _input_size(len(fx["subjects"]), len(fx["recording"])),
        "production_module": "synthetic.subject_loop_disk_staging",
        "production_available": False,
    }


# --------------------------------------------------------------------------- #
# 7. Worker-bound enforcement (candidate stays at 1)
# --------------------------------------------------------------------------- #
def _worker_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    # Models an unbounded fan-out plan (still executed serially here).
    planned_workers = max(8, len(fx["subjects"]) * 2)
    digests = [_stable_hash({"subject": s, "seed": fx["seed"]}) for s in fx["subjects"]]
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 0,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": planned_workers,
        "disk_bytes": None,
        "input_size": _input_size(len(fx["subjects"])),
        "production_module": "synthetic.worker_bound_enforcement",
        "production_available": False,
    }


def _worker_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    digests = [_stable_hash({"subject": s, "seed": fx["seed"]}) for s in fx["subjects"]]
    return {
        "checksum": _stable_hash(digests),
        "feature_count": len(digests),
        "read_counts": 0,
        "preprocess_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "manifest_writes": 0,
        "fsync_calls": 0,
        "worker_count": 1,
        "disk_bytes": None,
        "input_size": _input_size(len(fx["subjects"])),
        "production_module": "synthetic.worker_bound_enforcement",
        "production_available": False,
    }


TARGETS: Dict[str, TargetSpec] = {
    "full_recording_reread": TargetSpec(
        name="full_recording_reread",
        path_family="streaming_ingest",
        make_fixture=make_fixture,
        baseline=_reread_baseline,
        candidate=_reread_candidate,
        default_size=16,
    ),
    "preprocess_per_window": TargetSpec(
        name="preprocess_per_window",
        path_family="streaming_ingest",
        make_fixture=make_fixture,
        baseline=_preprocess_baseline,
        candidate=_preprocess_candidate,
        default_size=16,
    ),
    "checkpoint_fsync_overhead": TargetSpec(
        name="checkpoint_fsync_overhead",
        path_family="checkpointing",
        make_fixture=make_fixture,
        baseline=_checkpoint_baseline,
        candidate=_checkpoint_candidate,
        default_size=16,
    ),
    "manifest_write_amplification": TargetSpec(
        name="manifest_write_amplification",
        path_family="checkpointing",
        make_fixture=make_fixture,
        baseline=_manifest_baseline,
        candidate=_manifest_candidate,
        default_size=16,
    ),
    "window_cache_hits": TargetSpec(
        name="window_cache_hits",
        path_family="streaming_ingest",
        make_fixture=make_fixture,
        baseline=_cache_baseline,
        candidate=_cache_candidate,
        default_size=16,
    ),
    "subject_loop_disk_staging": TargetSpec(
        name="subject_loop_disk_staging",
        path_family="disk_staging",
        make_fixture=make_fixture,
        baseline=_disk_baseline,
        candidate=_disk_candidate,
        default_size=16,
    ),
    "worker_bound_enforcement": TargetSpec(
        name="worker_bound_enforcement",
        path_family="concurrency",
        make_fixture=make_fixture,
        baseline=_worker_baseline,
        candidate=_worker_candidate,
        default_size=16,
    ),
}
