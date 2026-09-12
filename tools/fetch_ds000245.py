#!/usr/bin/env python3
"""Plan or execute explicitly bounded ds000245 BIDS byte-range requests.

This module is intentionally not a dataset downloader.  The historical
implementation enumerated the OpenNeuro bucket and downloaded every matching
NIfTI object.  That access pattern is rejected here.  Callers must provide a
manifest record, an explicit byte range, a source checksum, a cache budget,
and an eviction lifecycle before the canonical bounded cache is used.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.data_access.chunk_cache import (
    BoundedChunkCache,
    ChunkRange,
    TransferResult,
    validate_bids_path,
)

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_MAX_CHUNK_BYTES = 64 * 1024 * 1024


class BoundedAccessError(ValueError):
    """Raised when a legacy request cannot be admitted to bounded access."""


@dataclass(frozen=True)
class BoundedObjectRequest:
    """Complete admission contract for one non-full-object BIDS range."""

    dataset_id: str
    bids_path: str
    source_uri: str
    expected_size_bytes: int
    source_sha256: str
    cache_root: Path
    output_root: Path
    max_cache_bytes: int
    chunk_range: ChunkRange
    final_consumer: str
    eviction_metadata: Mapping[str, Any]
    allow_network: bool = False
    chunk_sha256: str | None = None
    chunk_index: int = 0

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise BoundedAccessError("dataset_id is required")
        try:
            validate_bids_path(self.dataset_id, self.bids_path)
        except ValueError as exc:
            raise BoundedAccessError(str(exc)) from exc
        if not self.source_uri.strip():
            raise BoundedAccessError("source_uri is required")
        if self.expected_size_bytes <= 0:
            raise BoundedAccessError("expected_size_bytes must be positive")
        if not _SHA256.fullmatch(self.source_sha256):
            raise BoundedAccessError("source_sha256 must be a 64-character SHA-256 digest")
        if self.chunk_sha256 is not None and not _SHA256.fullmatch(self.chunk_sha256):
            raise BoundedAccessError("chunk_sha256 must be a 64-character SHA-256 digest")
        if self.chunk_range.start_byte < 0 or self.chunk_range.end_byte < self.chunk_range.start_byte:
            raise BoundedAccessError("chunk_range must be a non-empty ascending byte range")
        if self.chunk_range.end_byte >= self.expected_size_bytes:
            raise BoundedAccessError("chunk_range exceeds expected object size")
        if self.chunk_range.byte_count > _MAX_CHUNK_BYTES:
            raise BoundedAccessError(f"chunk_range exceeds {_MAX_CHUNK_BYTES} byte bound")
        if self.chunk_range.start_byte == 0 and self.chunk_range.end_byte == self.expected_size_bytes - 1:
            raise BoundedAccessError("full-object requests are rejected; provide a bounded window")
        if self.chunk_index < 0:
            raise BoundedAccessError("chunk_index must be non-negative")
        if not str(self.cache_root).strip() or not str(self.output_root).strip():
            raise BoundedAccessError("cache_root and output_root are required")
        if self.max_cache_bytes < self.chunk_range.byte_count:
            raise BoundedAccessError("max_cache_bytes is smaller than the requested range")
        if not self.final_consumer.strip():
            raise BoundedAccessError("final_consumer is required")
        required_eviction = {"consumer_id", "final_consumer", "delete_after_final_consumer"}
        missing = sorted(required_eviction.difference(self.eviction_metadata))
        if missing:
            raise BoundedAccessError("eviction_metadata missing: " + ", ".join(missing))
        if self.eviction_metadata["final_consumer"] != self.final_consumer:
            raise BoundedAccessError("eviction metadata final_consumer does not match request")
        if self.eviction_metadata["delete_after_final_consumer"] is not True:
            raise BoundedAccessError("delete_after_final_consumer must be true")

    @property
    def normalized_bids_path(self) -> str:
        return validate_bids_path(self.dataset_id, self.bids_path).relative_path

    def to_dict(self) -> dict[str, Any]:
        """Return a finite, JSON-safe manifest request."""
        return {
            "dataset_id": self.dataset_id,
            "bids_path": self.normalized_bids_path,
            "source_uri": self.source_uri,
            "expected_size_bytes": self.expected_size_bytes,
            "source_sha256": self.source_sha256.lower(),
            "chunk_sha256": self.chunk_sha256.lower() if self.chunk_sha256 else None,
            "chunk_range": {
                "start_byte": self.chunk_range.start_byte,
                "end_byte": self.chunk_range.end_byte,
                "total_file_size": self.expected_size_bytes,
            },
            "chunk_index": self.chunk_index,
            "cache_root": str(Path(self.cache_root).resolve()),
            "output_root": str(Path(self.output_root).resolve()),
            "max_cache_bytes": self.max_cache_bytes,
            "allow_network": bool(self.allow_network),
            "final_consumer": self.final_consumer,
            "eviction_metadata": dict(self.eviction_metadata),
        }


def request_from_mapping(raw: Mapping[str, Any], *, defaults: Mapping[str, Any] | None = None) -> BoundedObjectRequest:
    """Parse a manifest mapping without guessing missing provenance or limits."""
    values = dict(defaults or {})
    values.update(raw)
    for required in ("dataset_id", "bids_path", "source_uri", "expected_size_bytes", "source_sha256", "cache_root", "output_root", "max_cache_bytes", "final_consumer", "eviction_metadata"):
        if required not in values or values[required] in (None, ""):
            raise BoundedAccessError(f"{required} is required in the manifest")
    range_raw = values.get("chunk_range")
    if not isinstance(range_raw, Mapping):
        raise BoundedAccessError("chunk_range is required in the manifest")
    return BoundedObjectRequest(
        dataset_id=str(values.get("dataset_id", "")),
        bids_path=str(values.get("bids_path", "")),
        source_uri=str(values.get("source_uri", "")),
        expected_size_bytes=int(values.get("expected_size_bytes", 0)),
        source_sha256=str(values.get("source_sha256", "")),
        chunk_sha256=values.get("chunk_sha256"),
        cache_root=Path(str(values.get("cache_root", ""))),
        output_root=Path(str(values.get("output_root", ""))),
        max_cache_bytes=int(values.get("max_cache_bytes", 0)),
        chunk_range=ChunkRange(
            start_byte=int(range_raw.get("start_byte", -1)),
            end_byte=int(range_raw.get("end_byte", -1)),
            total_file_size=int(range_raw.get("total_file_size", values.get("expected_size_bytes", 0))),
        ),
        final_consumer=str(values.get("final_consumer", "")),
        eviction_metadata=values.get("eviction_metadata", {}),
        allow_network=bool(values.get("allow_network", False)),
        chunk_index=int(values.get("chunk_index", 0)),
    )


def _cache_for(requests: list[BoundedObjectRequest], *, transfer_adapter: Any = None) -> BoundedChunkCache:
    """Create the bounded cache after checking cache_budget, sha256, and eviction metadata."""
    if not requests:
        raise BoundedAccessError("at least one bounded request is required")
    roots = {str(Path(item.cache_root).resolve()) for item in requests}
    budgets = {item.max_cache_bytes for item in requests}
    if len(roots) != 1 or len(budgets) != 1:
        raise BoundedAccessError("all requests in one execution must share cache_root and max_cache_bytes")
    return BoundedChunkCache(
        requests[0].cache_root,
        max_cache_bytes=requests[0].max_cache_bytes,
        transfer_adapter=transfer_adapter,
    )


def _register(cache: BoundedChunkCache, items: list[BoundedObjectRequest]) -> None:
    """Register checksum-bearing byte ranges before any transfer or eviction."""
    for item in items:
        cache.register_manifest_item(
            dataset_id=item.dataset_id,
            bids_path=item.normalized_bids_path,
            source_uri=item.source_uri,
            size_bytes=item.chunk_range.byte_count,
            expected_checksum=item.chunk_sha256,
            chunk_range=item.chunk_range,
            chunk_index=item.chunk_index,
        )


def _plan_with_cache(cache: BoundedChunkCache, items: list[BoundedObjectRequest]) -> dict[str, Any]:
    """Produce a cache-budget, sha256, and eviction plan without network access."""
    plans = [cache.plan(item.dataset_id, [(item.normalized_bids_path, item.chunk_index)]) for item in items]
    executable = all(item.is_executable for item in plans)
    return {
        "schema_version": "NeuroTopology.BoundedOpenNeuroRequest.v1",
        "network_accessed": False,
        "is_executable": executable,
        "requests": [item.to_dict() for item in items],
        "plans": [
            {
                "dataset_id": item.dataset_id,
                "items_to_download": item.items_to_download,
                "already_cached_items": item.already_cached_items,
                "total_download_bytes": item.total_download_bytes,
                "cache_bytes_used": item.cache_bytes_used,
                "cache_bytes_max": item.cache_bytes_max,
                "eviction_required_bytes": item.eviction_required_bytes,
                "rejection_reason": item.rejection_reason,
                "is_executable": item.is_executable,
            }
            for item in plans
        ],
    }


def plan(requests: Iterable[BoundedObjectRequest], *, transfer_adapter: Any = None) -> dict[str, Any]:
    """Register explicit manifest metadata and produce a zero-network plan."""
    items = list(requests)
    cache = _cache_for(items, transfer_adapter=transfer_adapter)
    _register(cache, items)
    return _plan_with_cache(cache, items)


def release_after_final_consumer(cache: BoundedChunkCache, request: BoundedObjectRequest, result: TransferResult) -> dict[str, Any]:
    """Release lifecycle ownership and evict only this chunk through the cache.

    The canonical cache exposes LRU eviction publicly, while final-consumer
    cleanup is target-specific.  Supplying a one-record view to its eviction
    manager preserves the canonical containment/manifest logic without
    deleting an unrelated unleased item.
    """
    if not result.success or not result.cached_path:
        return {"status": "not_deleted", "reason": "transfer_not_successful"}
    key = (request.dataset_id, request.normalized_bids_path, request.chunk_index)
    record = getattr(cache, "_records", {}).get(key)
    if record is None:
        return {"status": "retained", "reason": "manifest_record_missing", "target": request.normalized_bids_path}
    reclaimed, evicted = cache.eviction_manager.evict_bytes(result.bytes_transferred, {key: record})
    cache._recalculate_current_usage()
    cache._save_manifest()
    target = next(
        (entry for entry in evicted if entry.dataset_id == request.dataset_id
         and entry.bids_path == request.normalized_bids_path
         and entry.chunk_index == request.chunk_index),
        None,
    )
    return {
        "status": "deleted" if target is not None else "retained",
        "reclaimed_bytes": reclaimed,
        "target": request.normalized_bids_path,
        "eviction_pending": target is None,
    }


def fetch(
    requests: Iterable[BoundedObjectRequest] | Path | str | None = None,
    *,
    consume: Callable[[Path], Any] | None = None,
    transfer_adapter: Any = None,
    dest_root: Path | None = None,
    limit: int | None = None,
    subjects: list[str] | None = None,
    include_anat: bool = False,
) -> dict[str, Any]:
    """Fetch only declared ranges through ``BoundedChunkCache`` with sha256 and eviction metadata.

    ``dest_root``, ``limit``, ``subjects``, and ``include_anat`` are retained as
    named compatibility arguments solely to produce an explicit rejection for
    older full-dataset callers.  They never enumerate or transfer objects.
    """
    if isinstance(requests, (Path, str)) or any(
        value is not None and value is not False
        for value in (dest_root, limit, subjects, include_anat)
    ):
        raise BoundedAccessError(
            "legacy full-dataset fetch arguments are rejected; provide explicit BoundedObjectRequest ranges"
        )
    if requests is None:
        raise BoundedAccessError("explicit BoundedObjectRequest ranges are required")
    items = list(requests)
    cache = _cache_for(items, transfer_adapter=transfer_adapter)
    _register(cache, items)
    summary = _plan_with_cache(cache, items)
    results: list[dict[str, Any]] = []
    for item in items:
        if not summary["is_executable"]:
            results.append({"success": False, "error_code": "PLAN_REJECTED", "error_message": "bounded plan rejected"})
            continue
        result = cache.fetch(
            dataset_id=item.dataset_id,
            bids_path=item.normalized_bids_path,
            chunk_index=item.chunk_index,
            allow_network=item.allow_network,
        )
        cleanup: dict[str, Any] = {"status": "retained", "reason": "consumer_not_invoked"}
        if result.success and consume is not None:
            lease = cache.acquire_lease(item.dataset_id, item.normalized_bids_path, item.chunk_index)
            try:
                consume(Path(result.cached_path or ""))
            finally:
                cache.release_lease(lease)
            cleanup = release_after_final_consumer(cache, item, result)
        results.append({
            "success": result.success,
            "dataset_id": result.dataset_id,
            "bids_path": result.bids_path,
            "chunk_index": result.chunk_index,
            "bytes_transferred": result.bytes_transferred,
            "cached_path": result.cached_path,
            "checksum_verified": result.checksum_verified,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "attempts": result.attempts,
            "cleanup": cleanup,
        })
    return {"schema_version": "NeuroTopology.BoundedOpenNeuroFetch.v1", "plan": summary, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="JSON object or list of bounded requests")
    parser.add_argument("--execute", action="store_true", help="Execute declared ranges; otherwise only plan")
    args = parser.parse_args(argv)
    raw = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else raw.get("requests") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        parser.error("manifest must contain a request list")
    requests = [request_from_mapping(item) for item in records]
    payload = fetch(requests) if args.execute else plan(requests)
    print(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))
    return 0 if payload.get("is_executable", payload.get("plan", {}).get("is_executable", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
