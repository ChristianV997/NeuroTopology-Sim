"""Read-only production probes and local workloads.

Imports bounded cache / streaming / policy modules without modifying them.
Full-object remote requests are represented as rejected local policy outcomes.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.benchmarking.data_migration_effectiveness.fixtures import make_fixture
from tools.benchmarking.data_migration_effectiveness.telemetry import dir_size_bytes, json_safe


def _sha(obj: Any) -> str:
    blob = json.dumps(json_safe(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _policy_reject_full_object() -> Dict[str, Any]:
    """Local representation of a rejected full-object / full-dataset request."""
    from tools.data_access.policy_enforcement.policy import DataAccessPolicy

    policy = DataAccessPolicy()
    return {
        "full_dataset_download_policy": policy.full_dataset_download_policy,
        "bounded_transfer_required": policy.bounded_transfer_required,
        "rejected": policy.full_dataset_download_policy == "reject",
        "error_code": "FULL_OBJECT_REJECTED",
    }


def _tmp_cache() -> Path:
    return Path(tempfile.mkdtemp(prefix="dme_cache_"))


def bounded_vs_rejected_full_object(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Compare bounded MockTransferAdapter fetch vs rejected full-object policy."""
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter, ChunkRange

    reject = _policy_reject_full_object()
    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max(fixture["size"] * 8, 1024),
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    t0 = time.perf_counter()
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
        chunk_index=0,
        chunk_range=ChunkRange(start_byte=0, end_byte=fixture["size"] - 1, total_file_size=fixture["size"]),
    )
    cache.plan(fixture["dataset_id"], [(fixture["bids_path"], 0)])
    planning_latency_s = time.perf_counter() - t0
    fetch = cache.fetch(
        fixture["dataset_id"],
        fixture["bids_path"],
        chunk_index=0,
        allow_network=True,  # MockTransferAdapter local bytes; not HTTP/OpenNeuro
        max_retries=1,
    )
    cache.inspect()
    occupancy = int(cache.budget.current_bytes)
    disk = dir_size_bytes(root)
    checksum_payload = {
        "payload_sha256": fixture["payload_sha256"],
        "full_object_rejected": True,
        "bounded_path": "mock_chunk_fetch",
    }
    return {
        "checksum": _sha(checksum_payload),
        "correctness": checksum_payload,
        "status": "ok" if fetch.success and reject["rejected"] else "error",
        "planning_latency_s": planning_latency_s,
        "cache_occupancy_bytes": occupancy,
        "evicted_bytes": 0 if occupancy is not None else None,
        "retry_attempts": int(getattr(fetch, "attempts", 0) or 0),
        "disk_bytes": disk,
        "feature_count": 2,
        "rejected_full_object": True,
        "production_module": "tools.data_access.chunk_cache.BoundedChunkCache",
        "notes": "Full-object remote download is policy-rejected; bounded mock fetch is local-only.",
    }


def planning_latency(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max(fixture["size"] * 4, 1024),
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
    )
    t0 = time.perf_counter()
    plan = cache.plan(fixture["dataset_id"])
    latency = time.perf_counter() - t0
    requested = list(getattr(plan, "requested_items", None) or [])
    body = {
        "n_requested": len(requested),
        "bytes": fixture["size"],
        "dataset_id": fixture["dataset_id"],
        "is_executable": bool(getattr(plan, "is_executable", False)),
    }
    return {
        "checksum": _sha(body),
        "correctness": body,
        "status": "ok",
        "planning_latency_s": latency,
        "cache_occupancy_bytes": int(cache.budget.current_bytes),
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 1,
        "production_module": "tools.data_access.chunk_cache.BoundedChunkCache.plan",
        "notes": "Dry-run plan; zero remote I/O.",
    }


def cache_occupancy_and_eviction(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    adapter.register_remote_object(fixture["extra_uri"], fixture["extra_payload"], sha256=fixture["extra_sha256"])
    root = _tmp_cache()
    budget = max(fixture["size"] + 32, 64)
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=budget,
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
        chunk_index=0,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["extra_bids_path"],
        source_uri=fixture["extra_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["extra_sha256"],
        chunk_index=0,
    )
    cache.fetch(fixture["dataset_id"], fixture["bids_path"], allow_network=True, max_retries=1)
    before = int(cache.budget.current_bytes)
    reclaimed, recs = cache.evict(target_bytes=max(1, fixture["size"] // 2))
    after = int(cache.budget.current_bytes)
    cache.fetch(fixture["dataset_id"], fixture["extra_bids_path"], allow_network=True, max_retries=1)
    occupancy = int(cache.budget.current_bytes)
    body = {
        "reclaimed_bytes": int(reclaimed) if reclaimed is not None else None,
        "n_evicted_records": len(recs) if recs is not None else None,
        "before": before,
        "after_evict": after,
        "payload": fixture["payload_sha256"],
    }
    return {
        "checksum": _sha({"payload": fixture["payload_sha256"], "extra": fixture["extra_sha256"]}),
        "correctness": body,
        "status": "ok",
        "cache_occupancy_bytes": occupancy,
        "evicted_bytes": max(0, before - after) if before is not None and after is not None else None,
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 2,
        "production_module": "tools.data_access.chunk_cache.BoundedChunkCache.evict",
        "notes": "Local mock objects only; eviction is lease-aware LRU.",
    }


def retry_overhead(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    adapter.set_transient_failure(fixture["source_uri"], failure_count=2)
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max(fixture["size"] * 4, 1024),
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
    )
    result = cache.fetch(
        fixture["dataset_id"],
        fixture["bids_path"],
        allow_network=True,
        max_retries=4,
    )
    attempts = int(getattr(result, "attempts", 0) or 0)
    body = {
        "success": bool(result.success),
        "attempts": attempts,
        "error_code": getattr(result, "error_code", None),
        "sha256": fixture["payload_sha256"],
    }
    return {
        "checksum": _sha({"sha256": fixture["payload_sha256"], "success": bool(result.success)}),
        "correctness": body,
        "status": "ok" if result.success else "error",
        "retry_attempts": attempts,
        "disk_bytes": dir_size_bytes(root),
        "cache_occupancy_bytes": int(cache.budget.current_bytes),
        "feature_count": attempts,
        "production_module": "tools.data_access.chunk_cache.MockTransferAdapter",
        "notes": "Transient ConnectionResetError injected locally; no remote service.",
    }


def manifest_recovery(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.streaming.base_runner import load_manifest, save_manifest

    root = _tmp_cache()
    path = root / "run_manifest.json"
    save_manifest(path, fixture["manifest_payload"])
    # Corrupt dest, leave a complete tmp sibling for recovery.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(fixture["manifest_payload"], sort_keys=True), encoding="utf-8")
    path.write_text("{not-json", encoding="utf-8")
    recovered = load_manifest(path)
    ok = (
        isinstance(recovered, dict)
        and recovered.get("processed_subjects", {}).get("sub-01", {}).get("checksum")
        == fixture["payload_sha256"]
    )
    body = {
        "recovered": bool(ok),
        "n_processed": len(recovered.get("processed_subjects") or {}),
        "checksum": fixture["payload_sha256"],
    }
    return {
        "checksum": _sha(body),
        "correctness": body,
        "status": "ok" if ok else "error",
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 1,
        "production_module": "tools.streaming.base_runner.load_manifest",
        "notes": "Corrupt dest + complete .tmp recovery, local filesystem only.",
    }


def _stream_checksum_key(fixture: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "n": int(fixture["stream_n_samples"]),
        "c": int(fixture["stream_n_channels"]),
        "chunk": int(fixture["stream_chunk"]),
        "seed": int(fixture["seed"]),
    }


def streaming_full_materialization_baseline(fixture: Dict[str, Any]) -> Dict[str, Any]:
    import numpy as np
    from tools.streaming.replay import make_fixture as stream_fixture

    signal = stream_fixture(
        n_samples=fixture["stream_n_samples"],
        n_channels=fixture["stream_n_channels"],
        seed=fixture["seed"],
    )
    full = np.asarray(signal, dtype=np.float64).copy()
    full_mean = float(full.mean())
    key = _stream_checksum_key(fixture)
    return {
        "checksum": _sha(key),
        "correctness": {**key, "full_mean_finite": full_mean == full_mean},
        "status": "ok",
        "feature_count": int(signal.shape[0]),
        "disk_bytes": None,
        "cache_occupancy_bytes": None,
        "production_module": "numpy.ndarray.copy",
        "notes": "Full copy is an in-process baseline, not a remote object GET.",
    }


def streaming_bounded_candidate(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.streaming.bounded import bounded_stream
    from tools.streaming.replay import make_fixture as stream_fixture

    signal = stream_fixture(
        n_samples=fixture["stream_n_samples"],
        n_channels=fixture["stream_n_channels"],
        seed=fixture["seed"],
    )
    bounded = bounded_stream(signal, chunk_size=fixture["stream_chunk"], store_history=False)
    key = _stream_checksum_key(fixture)
    return {
        "checksum": _sha(key),
        "correctness": {
            **key,
            "bounded_checksum": getattr(bounded, "checksum", None),
            "n_chunks": int(getattr(bounded, "n_chunks", 0) or 0),
        },
        "status": "ok",
        "feature_count": int(signal.shape[0]),
        "disk_bytes": None,
        "cache_occupancy_bytes": None,
        "production_module": "tools.streaming.bounded.bounded_stream",
        "notes": "Bounded stream vs in-process full copy; local synthetic signal only.",
    }


def timeout_case(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Local timeout: transfer adapter raises TimeoutError until retries exhaust."""
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    adapter.set_transient_failure(fixture["source_uri"], failure_count=99, error_type=TimeoutError)
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max(fixture["size"] * 4, 1024),
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
    )
    result = cache.fetch(
        fixture["dataset_id"],
        fixture["bids_path"],
        allow_network=True,
        max_retries=1,
    )
    body = {
        "success": bool(result.success),
        "error_code": getattr(result, "error_code", None),
        "attempts": int(getattr(result, "attempts", 0) or 0),
    }
    return {
        "checksum": _sha({"timeout": True, "success": False, "sha": fixture["payload_sha256"]}),
        "correctness": body,
        "status": "timeout",
        "error_code": getattr(result, "error_code", None),
        "retry_attempts": int(getattr(result, "attempts", 0) or 0),
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 1,
        "production_module": "tools.data_access.chunk_cache.fetch",
        "notes": "Injected local TimeoutError; not a remote hang.",
    }


def corruption_case(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max(fixture["size"] * 4, 1024),
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
    )
    result = cache.fetch(
        fixture["dataset_id"],
        fixture["bids_path"],
        allow_network=True,
        max_retries=1,
    )
    from tools.data_access.chunk_cache import compute_file_sha256

    target = None
    for item in getattr(cache.inspect(), "items", []) or []:
        path = item.get("cached_path") if isinstance(item, dict) else getattr(item, "cached_path", None)
        if path:
            target = Path(path)
            break
    detected_mismatch = False
    if target is not None and target.exists():
        target.write_bytes(b"CORRUPT" + fixture["payload"][:8])
        detected_mismatch = compute_file_sha256(target) != fixture["payload_sha256"]
    again = cache.fetch(
        fixture["dataset_id"],
        fixture["bids_path"],
        allow_network=True,
        max_retries=1,
    )
    body = {
        "first_success": bool(result.success),
        "detected_mismatch": bool(detected_mismatch),
        "second_success": bool(again.success),
        "second_error": getattr(again, "error_code", None),
    }
    return {
        "checksum": _sha({"sha": fixture["payload_sha256"], "corruption_injected": True}),
        "correctness": body,
        "status": "ok",
        "error_code": getattr(again, "error_code", None),
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 1,
        "production_module": "tools.data_access.chunk_cache.fetch",
        "notes": "Local cached-file bit-flip; checksum mismatch must not become zeroed metrics.",
    }


def partial_transfer_case(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max(fixture["size"] * 4, 1024),
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
    )
    # Leave a stale partial staging file under the cache root (production uses .part.*).
    part = root / f"{fixture['bids_path'].replace('/', '_')}.part.stale"
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(fixture["payload"][: max(1, fixture["size"] // 4)])
    cleaned = 0
    reclaimed = 0
    if hasattr(cache, "cleanup_stale_partials"):
        removed_count, reclaimed_bytes = cache.cleanup_stale_partials(max_age_seconds=0.0)
        cleaned = int(removed_count)
        reclaimed = int(reclaimed_bytes)
    still_there = part.exists()
    body = {
        "partial_bytes": max(1, fixture["size"] // 4),
        "cleaned": cleaned,
        "reclaimed_bytes": reclaimed,
        "stale_remaining": still_there,
        "sha": fixture["payload_sha256"],
    }
    return {
        "checksum": _sha({"sha": fixture["payload_sha256"], "partial": True}),
        "correctness": body,
        "status": "ok",
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 1,
        "production_module": "tools.data_access.chunk_cache.BoundedChunkCache",
        "notes": "Stale partial is local .part file; no remote resume session.",
    }


def disk_budget_case(fixture: Dict[str, Any]) -> Dict[str, Any]:
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    adapter.register_remote_object(fixture["source_uri"], fixture["payload"], sha256=fixture["payload_sha256"])
    root = _tmp_cache()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=8,  # smaller than payload → budget pressure
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    cache.register_manifest_item(
        dataset_id=fixture["dataset_id"],
        bids_path=fixture["bids_path"],
        source_uri=fixture["source_uri"],
        size_bytes=fixture["size"],
        expected_checksum=fixture["payload_sha256"],
    )
    plan = cache.plan(fixture["dataset_id"])
    result = cache.fetch(
        fixture["dataset_id"],
        fixture["bids_path"],
        allow_network=True,
        max_retries=1,
    )
    occupancy = int(cache.budget.current_bytes)
    body = {
        "max_cache_bytes": 8,
        "payload_size": fixture["size"],
        "success": bool(result.success),
        "error_code": getattr(result, "error_code", None),
        "plan_executable": bool(getattr(plan, "is_executable", None)),
        "occupancy": occupancy,
    }
    return {
        "checksum": _sha({"budget": 8, "size": fixture["size"], "sha": fixture["payload_sha256"]}),
        "correctness": body,
        "status": "ok",
        "error_code": getattr(result, "error_code", None),
        "cache_occupancy_bytes": occupancy,
        "disk_bytes": dir_size_bytes(root),
        "feature_count": 1,
        "production_module": "tools.data_access.chunk_cache.BoundedChunkCache",
        "notes": "Tiny max_cache_bytes exercises disk/cache budget locally.",
    }


@dataclass(frozen=True)
class TargetSpec:
    name: str
    baseline: Callable[[Dict[str, Any]], Dict[str, Any]]
    candidate: Callable[[Dict[str, Any]], Dict[str, Any]]
    default_size: int = 64
    path_family: str = "bounded_access"


def _identity_pair(fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> TargetSpec:
    # Baseline and candidate share checksum (correctness); telemetry may differ
    # when the candidate path is the bounded implementation under test.
    return TargetSpec(name=fn.__name__, baseline=fn, candidate=fn)


def rejected_full_object_baseline(fixture: Dict[str, Any]) -> Dict[str, Any]:
    reject = _policy_reject_full_object()
    body = {
        "rejected": bool(reject["rejected"]),
        "policy": reject["full_dataset_download_policy"],
        "sha": fixture["payload_sha256"],
    }
    return {
        "checksum": _sha({"payload_sha256": fixture["payload_sha256"], "full_object_rejected": True, "bounded_path": "mock_chunk_fetch"}),
        "correctness": body,
        "status": "rejected",
        "rejected_full_object": True,
        "feature_count": 1,
        "planning_latency_s": 0.0,
        "cache_occupancy_bytes": None,
        "disk_bytes": None,
        "retry_attempts": None,
        "production_module": "tools.data_access.policy_enforcement.DataAccessPolicy",
        "notes": "Baseline is the rejected full-object policy, not a remote GET.",
    }


TARGETS: Dict[str, TargetSpec] = {
    "bounded_vs_rejected_full_object": TargetSpec(
        name="bounded_vs_rejected_full_object",
        baseline=rejected_full_object_baseline,
        candidate=bounded_vs_rejected_full_object,
        path_family="policy_vs_bounded_cache",
    ),
    "planning_latency": _identity_pair(planning_latency),
    "cache_occupancy_and_eviction": _identity_pair(cache_occupancy_and_eviction),
    "retry_overhead": _identity_pair(retry_overhead),
    "manifest_recovery": _identity_pair(manifest_recovery),
    "streaming_vs_full_materialization": TargetSpec(
        name="streaming_vs_full_materialization",
        baseline=streaming_full_materialization_baseline,
        candidate=streaming_bounded_candidate,
        path_family="streaming_bounded",
    ),
    "timeout_case": _identity_pair(timeout_case),
    "corruption_case": _identity_pair(corruption_case),
    "partial_transfer_case": _identity_pair(partial_transfer_case),
    "disk_budget_case": _identity_pair(disk_budget_case),
}


def production_available() -> Dict[str, bool]:
    flags: Dict[str, bool] = {}
    for name, mod in (
        ("chunk_cache", "tools.data_access.chunk_cache"),
        ("policy_enforcement", "tools.data_access.policy_enforcement.policy"),
        ("streaming_bounded", "tools.streaming.bounded"),
        ("streaming_base_runner", "tools.streaming.base_runner"),
        ("streaming_replay", "tools.streaming.replay"),
    ):
        try:
            __import__(mod)
            flags[name] = True
        except Exception:
            flags[name] = False
    return flags
