"""Core cache engine coordinating manifest, leases, eviction, and transfers.

Enforces:
- Manifest-first: metadata is registered/verified before transfers.
- Bounded cache budget and pre-flight disk headroom checks.
- Fail-closed network policy: network transfers require explicit opt-in.
- Lease-aware LRU eviction: locked/leased chunks are never evicted.
- Path security: strict containment within the cache root.
- Deterministic, tamper-evident inspection reports with SHA-256 digest.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.data_access.chunk_cache.bids_validator import (
    BIDSValidationError,
    normalize_bids_relative_path,
    validate_bids_path,
)
from tools.data_access.chunk_cache.eviction import (
    BoundedEvictionManager,
    EvictionSecurityError,
)
from tools.data_access.chunk_cache.lease_manager import LeaseManager
from tools.data_access.chunk_cache.transfer import (
    HTTPTransferAdapter,
    MockTransferAdapter,
    TransferAdapter,
    compute_file_sha256,
)
from tools.data_access.chunk_cache.types import (
    BIDSPathComponents,
    CacheBudget,
    CacheErrorCode,
    CacheItemStatus,
    CacheReport,
    ChunkRange,
    LeaseHandle,
    ManifestRecord,
    TransferPlan,
    TransferResult,
)


class BoundedChunkCache:
    """Manifest-first bounded cache for OpenNeuro/BIDS chunks and files."""

    def __init__(
        self,
        cache_root: str | Path,
        max_cache_bytes: int = 500 * 1024 * 1024,  # 500 MB default
        min_free_headroom_bytes: int = 50 * 1024 * 1024,  # 50 MB default
        transfer_adapter: Optional[TransferAdapter] = None,
    ) -> None:
        self.cache_root = Path(cache_root).resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)

        self.budget = CacheBudget(
            max_cache_bytes=max_cache_bytes,
            current_bytes=0,
            min_free_headroom_bytes=min_free_headroom_bytes,
        )

        self.lease_manager = LeaseManager()
        self.eviction_manager = BoundedEvictionManager(
            cache_root=self.cache_root,
            lease_manager=self.lease_manager,
        )

        self.transfer_adapter = transfer_adapter or HTTPTransferAdapter()
        self.manifest_path = self.cache_root / "manifest.json"
        self._records: Dict[Tuple[str, str, int], ManifestRecord] = {}

        self._load_manifest()
        self._recalculate_current_usage()

    # -------------------------------------------------------------------------
    # Manifest & Persistence
    # -------------------------------------------------------------------------

    def _load_manifest(self) -> None:
        """Load manifest from disk if it exists."""
        if not self.manifest_path.exists():
            return

        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            records = raw.get("records", [])
            for r in records:
                chunk_range = None
                if r.get("chunk_range"):
                    cr = r["chunk_range"]
                    chunk_range = ChunkRange(
                        start_byte=cr["start_byte"],
                        end_byte=cr["end_byte"],
                        total_file_size=cr.get("total_file_size"),
                    )

                rec = ManifestRecord(
                    dataset_id=r["dataset_id"],
                    bids_path=r["bids_path"],
                    source_uri=r["source_uri"],
                    size_bytes=r["size_bytes"],
                    expected_checksum=r.get("expected_checksum"),
                    actual_checksum=r.get("actual_checksum"),
                    chunk_index=r.get("chunk_index", 0),
                    chunk_range=chunk_range,
                    status=r.get("status", CacheItemStatus.UNCACHED.value),
                    cached_path=r.get("cached_path"),
                    last_accessed_at=r.get("last_accessed_at", ""),
                    last_evicted_at=r.get("last_evicted_at"),
                    lease_count=0,
                )

                # Verify file presence if marked CACHED
                if rec.status == CacheItemStatus.CACHED.value and rec.cached_path:
                    p = Path(rec.cached_path)
                    try:
                        contained = p.resolve().is_relative_to(self.cache_root)
                    except AttributeError:
                        contained = os.path.commonpath([str(p.resolve()), str(self.cache_root)]) == str(self.cache_root)
                    if not contained or not p.is_file():
                        rec.status = CacheItemStatus.UNCACHED.value
                        rec.cached_path = None

                key = (rec.dataset_id, rec.bids_path, rec.chunk_index)
                self._records[key] = rec
        except Exception:
            # Corrupted or unreadable manifest; start clean
            self._records = {}

    def _save_manifest(self) -> None:
        """Atomically persist manifest to disk."""
        records_list = []
        for rec in self._records.values():
            rec_dict = {
                "dataset_id": rec.dataset_id,
                "bids_path": rec.bids_path,
                "source_uri": rec.source_uri,
                "size_bytes": rec.size_bytes,
                "expected_checksum": rec.expected_checksum,
                "actual_checksum": rec.actual_checksum,
                "chunk_index": rec.chunk_index,
                "status": rec.status,
                "cached_path": rec.cached_path,
                "last_accessed_at": rec.last_accessed_at,
                "last_evicted_at": rec.last_evicted_at,
            }
            if rec.chunk_range:
                rec_dict["chunk_range"] = {
                    "start_byte": rec.chunk_range.start_byte,
                    "end_byte": rec.chunk_range.end_byte,
                    "total_file_size": rec.chunk_range.total_file_size,
                }
            else:
                rec_dict["chunk_range"] = None
            records_list.append(rec_dict)

        payload = {
            "schema_version": "v1.0.0",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "records": records_list,
        }

        tmp_file = self.cache_root / f"manifest.json.part.{os.getpid()}"
        tmp_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_file.replace(self.manifest_path)

    def _recalculate_current_usage(self) -> None:
        """Scan cached items and update budget.current_bytes."""
        total = 0
        for rec in self._records.values():
            if rec.status == CacheItemStatus.CACHED.value and rec.cached_path:
                p = Path(rec.cached_path)
                try:
                    contained = p.resolve().is_relative_to(self.cache_root)
                except AttributeError:
                    contained = os.path.commonpath([str(p.resolve()), str(self.cache_root)]) == str(self.cache_root)
                if contained and p.is_file():
                    total += p.stat().st_size
                else:
                    rec.status = CacheItemStatus.UNCACHED.value
                    rec.cached_path = None
        self.budget.current_bytes = total

    def _get_target_path(self, dataset_id: str, bids_path: str, chunk_index: int = 0) -> Path:
        """Resolve local file path for a dataset and relative BIDS path."""
        norm_bids = normalize_bids_relative_path(bids_path)
        posix_rel = PurePosixPath(norm_bids)
        if chunk_index > 0:
            target = self.cache_root / dataset_id / posix_rel.parent / f"{posix_rel.name}.chunk.{chunk_index}"
        else:
            target = self.cache_root / dataset_id / posix_rel
        return target

    # -------------------------------------------------------------------------
    # Manifest Registration
    # -------------------------------------------------------------------------

    def register_manifest_item(
        self,
        dataset_id: str,
        bids_path: str,
        source_uri: str,
        size_bytes: int,
        expected_checksum: Optional[str] = None,
        chunk_range: Optional[ChunkRange] = None,
        chunk_index: int = 0,
    ) -> ManifestRecord:
        """Register BIDS metadata in the cache manifest prior to any download."""
        # Enforce BIDS path validation & containment
        validate_bids_path(dataset_id, bids_path)

        norm_path = normalize_bids_relative_path(bids_path)
        key = (dataset_id, norm_path, chunk_index)

        target_path = self._get_target_path(dataset_id, norm_path, chunk_index)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Check if already present on disk
        status = CacheItemStatus.UNCACHED.value
        cached_path = None
        actual_checksum = None
        if target_path.exists():
            status = CacheItemStatus.CACHED.value
            cached_path = str(target_path)
            actual_checksum = compute_file_sha256(target_path)

        rec = ManifestRecord(
            dataset_id=dataset_id,
            bids_path=norm_path,
            source_uri=source_uri,
            size_bytes=size_bytes,
            expected_checksum=expected_checksum,
            actual_checksum=actual_checksum,
            chunk_index=chunk_index,
            chunk_range=chunk_range,
            status=status,
            cached_path=cached_path,
            last_accessed_at=now_iso if status == CacheItemStatus.CACHED.value else "",
        )

        self._records[key] = rec
        self._save_manifest()
        self._recalculate_current_usage()
        return rec

    # -------------------------------------------------------------------------
    # Dry-Run Planning (Zero Network Calls)
    # -------------------------------------------------------------------------

    def plan(
        self,
        dataset_id: str,
        requested_items: Optional[Sequence[Tuple[str, int] | dict]] = None,
    ) -> TransferPlan:
        """Evaluate dry-run execution plan with zero network access.

        Args:
            dataset_id: OpenNeuro dataset ID.
            requested_items: Sequence of (bids_path, chunk_index) or dicts with bids_path & chunk_index.
                             If None, evaluates all registered manifest items for dataset.

        Returns:
            TransferPlan with budget, disk space, and eviction requirements.
        """
        requested: List[dict] = []
        already_cached: List[dict] = []
        to_download: List[dict] = []
        total_download_bytes = 0

        # Build list of items to evaluate
        keys_to_eval: List[Tuple[str, str, int]] = []
        if requested_items is None:
            for k in self._records.keys():
                if k[0] == dataset_id:
                    keys_to_eval.append(k)
        else:
            for itm in requested_items:
                if isinstance(itm, dict):
                    bpath = itm["bids_path"]
                    cidx = itm.get("chunk_index", 0)
                else:
                    bpath, cidx = itm
                norm = normalize_bids_relative_path(bpath)
                keys_to_eval.append((dataset_id, norm, cidx))

        for k in keys_to_eval:
            ds, bp, ci = k
            rec = self._records.get(k)
            info = {
                "dataset_id": ds,
                "bids_path": bp,
                "chunk_index": ci,
                "size_bytes": rec.size_bytes if rec else 0,
                "status": rec.status if rec else CacheItemStatus.UNCACHED.value,
            }
            requested.append(info)

            if rec and rec.status == CacheItemStatus.CACHED.value and rec.cached_path and Path(rec.cached_path).exists():
                already_cached.append(info)
            else:
                to_download.append(info)
                total_download_bytes += rec.size_bytes if rec else 0

        # Disk space evaluation
        disk_usage = shutil.disk_usage(self.cache_root)
        available_disk = disk_usage.free

        # Eviction evaluation
        bytes_needed = total_download_bytes
        cache_headroom = max(0, self.budget.max_cache_bytes - self.budget.current_bytes)
        eviction_needed = max(0, bytes_needed - cache_headroom)

        # Find evictable items (unleased, cached)
        evictable: List[dict] = []
        potential_evict_bytes = 0
        for rec in self._records.values():
            if rec.status == CacheItemStatus.CACHED.value and rec.cached_path:
                if not self.lease_manager.is_leased(rec.dataset_id, rec.bids_path, rec.chunk_index):
                    evictable.append({
                        "dataset_id": rec.dataset_id,
                        "bids_path": rec.bids_path,
                        "chunk_index": rec.chunk_index,
                        "size_bytes": rec.size_bytes,
                        "last_accessed_at": rec.last_accessed_at,
                    })
                    potential_evict_bytes += rec.size_bytes

        # Check plan feasibility
        is_executable = True
        rejection_reason = None

        if total_download_bytes > self.budget.max_cache_bytes:
            is_executable = False
            rejection_reason = (
                f"Requested bytes ({total_download_bytes}) exceed total cache capacity "
                f"({self.budget.max_cache_bytes})"
            )
        elif eviction_needed > potential_evict_bytes:
            is_executable = False
            rejection_reason = (
                f"Eviction required ({eviction_needed} bytes) exceeds available unleased items "
                f"({potential_evict_bytes} bytes). Active leases are protecting occupied cache."
            )
        elif total_download_bytes > (available_disk - self.budget.min_free_headroom_bytes):
            is_executable = False
            rejection_reason = (
                f"Available disk space ({available_disk} bytes) minus headroom "
                f"({self.budget.min_free_headroom_bytes} bytes) is insufficient for "
                f"{total_download_bytes} bytes"
            )

        return TransferPlan(
            dataset_id=dataset_id,
            requested_items=requested,
            already_cached_items=already_cached,
            items_to_download=to_download,
            total_download_bytes=total_download_bytes,
            cache_bytes_used=self.budget.current_bytes,
            cache_bytes_max=self.budget.max_cache_bytes,
            available_disk_bytes=available_disk,
            eviction_required_bytes=eviction_needed,
            evictable_items=evictable,
            is_executable=is_executable,
            rejection_reason=rejection_reason,
        )

    # -------------------------------------------------------------------------
    # Chunk Fetching (Strict Fail-Closed, Pre-flight Checked)
    # -------------------------------------------------------------------------

    def fetch(
        self,
        dataset_id: str,
        bids_path: str,
        chunk_index: int = 0,
        allow_network: bool = False,
        max_retries: int = 3,
    ) -> TransferResult:
        """Fetch a BIDS object or chunk into the cache.

        Args:
            dataset_id: OpenNeuro dataset ID.
            bids_path: Validated BIDS relative path.
            chunk_index: Index of the chunk (0 for full file).
            allow_network: Explicit authorization for network downloads.
            max_retries: Retry limit for transient network errors.

        Returns:
            TransferResult summarizing outcome, error classification, and metrics.
        """
        # 1. Validate BIDS structure
        try:
            validate_bids_path(dataset_id, bids_path)
            norm_path = normalize_bids_relative_path(bids_path)
        except BIDSValidationError as exc:
            return TransferResult(
                success=False,
                dataset_id=dataset_id,
                bids_path=str(bids_path),
                chunk_index=chunk_index,
                bytes_transferred=0,
                error_code=CacheErrorCode.INVALID_BIDS_PATH.value,
                error_message=str(exc),
                attempts=0,
            )

        key = (dataset_id, norm_path, chunk_index)
        rec = self._records.get(key)
        if not rec:
            return TransferResult(
                success=False,
                dataset_id=dataset_id,
                bids_path=norm_path,
                chunk_index=chunk_index,
                bytes_transferred=0,
                error_code=CacheErrorCode.MISSING_OBJECT.value,
                error_message=f"No manifest entry for {key}. Manifest-first registration required.",
                attempts=0,
            )

        # 2. Check if already cached and intact
        target_path = self._get_target_path(dataset_id, norm_path, chunk_index)
        if rec.status == CacheItemStatus.CACHED.value and rec.cached_path and target_path.exists():
            if rec.expected_checksum:
                actual_checksum = compute_file_sha256(target_path)
                if actual_checksum.lower() != rec.expected_checksum.lower():
                    # A cached checksum mismatch is corruption, not a cache hit.
                    # Clear the stale entry and continue through the normal
                    # fail-closed/network admission path below.
                    rec.status = CacheItemStatus.CORRUPTED.value
                    rec.actual_checksum = actual_checksum
                    rec.cached_path = None
                    self._save_manifest()
                else:
                    rec.actual_checksum = actual_checksum
            if rec.status != CacheItemStatus.CORRUPTED.value:
                rec.last_accessed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self._save_manifest()
                return TransferResult(
                    success=True,
                    dataset_id=dataset_id,
                    bids_path=norm_path,
                    chunk_index=chunk_index,
                    bytes_transferred=target_path.stat().st_size,
                    cached_path=str(target_path),
                    checksum_verified=(rec.expected_checksum is not None),
                    attempts=0,
                )

        # 3. Fail-closed network check
        if not allow_network:
            return TransferResult(
                success=False,
                dataset_id=dataset_id,
                bids_path=norm_path,
                chunk_index=chunk_index,
                bytes_transferred=0,
                error_code=CacheErrorCode.NETWORK_DISABLED.value,
                error_message="Network access is disabled (fail-closed policy). Explicit opt-in required.",
                attempts=0,
            )

        # 4. Pre-flight disk space check
        disk_usage = shutil.disk_usage(self.cache_root)
        if disk_usage.free < (rec.size_bytes + self.budget.min_free_headroom_bytes):
            return TransferResult(
                success=False,
                dataset_id=dataset_id,
                bids_path=norm_path,
                chunk_index=chunk_index,
                bytes_transferred=0,
                error_code=CacheErrorCode.DISK_EXHAUSTION.value,
                error_message=(
                    f"Disk exhaustion detected: available {disk_usage.free} bytes is less than "
                    f"required {rec.size_bytes} bytes + headroom {self.budget.min_free_headroom_bytes} bytes."
                ),
                attempts=0,
            )

        # 5. Pre-flight cache budget & eviction
        bytes_needed = rec.size_bytes
        if bytes_needed > self.budget.max_cache_bytes:
            return TransferResult(
                success=False,
                dataset_id=dataset_id,
                bids_path=norm_path,
                chunk_index=chunk_index,
                bytes_transferred=0,
                error_code=CacheErrorCode.CACHE_BUDGET_EXCEEDED.value,
                error_message=f"Object size {bytes_needed} exceeds maximum cache budget {self.budget.max_cache_bytes}.",
                attempts=0,
            )

        cache_headroom = max(0, self.budget.max_cache_bytes - self.budget.current_bytes)
        if bytes_needed > cache_headroom:
            evict_target = bytes_needed - cache_headroom
            reclaimed, evicted = self.eviction_manager.evict_bytes(evict_target, self._records)
            self._recalculate_current_usage()
            if reclaimed < evict_target:
                return TransferResult(
                    success=False,
                    dataset_id=dataset_id,
                    bids_path=norm_path,
                    chunk_index=chunk_index,
                    bytes_transferred=0,
                    error_code=CacheErrorCode.ACTIVE_LEASE_LOCKED.value,
                    error_message=(
                        f"Cannot evict {evict_target} bytes to fit new chunk: only reclaimed {reclaimed} bytes. "
                        f"Remaining items are protected by active leases."
                    ),
                    attempts=0,
                )

        # 6. Execute atomic transfer
        rec.status = CacheItemStatus.DOWNLOADING.value
        self._save_manifest()

        res = self.transfer_adapter.transfer_chunk(
            source_uri=rec.source_uri,
            target_path=target_path,
            chunk_range=rec.chunk_range,
            expected_checksum=rec.expected_checksum,
            allow_network=allow_network,
            max_retries=max_retries,
        )

        res.dataset_id = dataset_id
        res.bids_path = norm_path
        res.chunk_index = chunk_index

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if res.success and target_path.exists():
            rec.status = CacheItemStatus.CACHED.value
            rec.cached_path = str(target_path)
            rec.last_accessed_at = now_iso
            rec.actual_checksum = compute_file_sha256(target_path)
            self._recalculate_current_usage()
        else:
            rec.status = CacheItemStatus.UNCACHED.value
            rec.cached_path = None

        self._save_manifest()
        return res

    # -------------------------------------------------------------------------
    # Leases
    # -------------------------------------------------------------------------

    def acquire_lease(
        self,
        dataset_id: str,
        bids_path: str,
        chunk_index: int = 0,
        ttl_seconds: Optional[float] = None,
    ) -> LeaseHandle:
        """Acquire a protective lease preventing eviction of a cached item."""
        norm_path = normalize_bids_relative_path(bids_path)
        handle = self.lease_manager.acquire_lease(
            dataset_id=dataset_id,
            bids_path=norm_path,
            chunk_index=chunk_index,
            ttl_seconds=ttl_seconds,
        )
        key = (dataset_id, norm_path, chunk_index)
        if key in self._records:
            self._records[key].lease_count = self.lease_manager.get_lease_count(dataset_id, norm_path, chunk_index)
        return handle

    def release_lease(self, handle_or_id: LeaseHandle | str) -> bool:
        """Release a previously acquired lease."""
        return self.lease_manager.release_lease(handle_or_id)

    # -------------------------------------------------------------------------
    # Eviction & Partial Cleanup
    # -------------------------------------------------------------------------

    def evict(self, target_bytes: int) -> Tuple[int, List[ManifestRecord]]:
        """Manually trigger LRU eviction of unleased chunks."""
        reclaimed, evicted = self.eviction_manager.evict_bytes(target_bytes, self._records)
        self._recalculate_current_usage()
        self._save_manifest()
        return reclaimed, evicted

    def cleanup_stale_partials(self, max_age_seconds: float = 0.0) -> Tuple[int, int]:
        """Scan and remove abandoned .part.* files strictly within cache root."""
        removed_count, reclaimed_bytes = self.eviction_manager.cleanup_stale_partials(max_age_seconds)
        self._recalculate_current_usage()
        return removed_count, reclaimed_bytes

    # -------------------------------------------------------------------------
    # Tamper-evident Audit Report
    # -------------------------------------------------------------------------

    def inspect(self) -> CacheReport:
        """Generate a tamper-evident audit report with cryptographic SHA-256."""
        self._recalculate_current_usage()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        items_list: List[dict] = []
        cached_count = 0
        evicted_count = 0

        for rec in self._records.values():
            active_leases = self.lease_manager.get_lease_count(rec.dataset_id, rec.bids_path, rec.chunk_index)
            if rec.status == CacheItemStatus.CACHED.value:
                cached_count += 1
            elif rec.status == CacheItemStatus.EVICTED.value:
                evicted_count += 1

            cr_dict = None
            if rec.chunk_range:
                cr_dict = {
                    "start_byte": rec.chunk_range.start_byte,
                    "end_byte": rec.chunk_range.end_byte,
                    "total_file_size": rec.chunk_range.total_file_size,
                }

            items_list.append({
                "dataset_id": rec.dataset_id,
                "bids_path": rec.bids_path,
                "chunk_index": rec.chunk_index,
                "size_bytes": rec.size_bytes,
                "status": rec.status,
                "source_uri": rec.source_uri,
                "expected_checksum": rec.expected_checksum,
                "actual_checksum": rec.actual_checksum,
                "cached_path": rec.cached_path,
                "active_leases": active_leases,
                "last_accessed_at": rec.last_accessed_at,
                "last_evicted_at": rec.last_evicted_at,
                "chunk_range": cr_dict,
            })

        budget_info = {
            "max_cache_bytes": self.budget.max_cache_bytes,
            "current_bytes": self.budget.current_bytes,
            "remaining_budget_bytes": self.budget.remaining_budget_bytes,
            "min_free_headroom_bytes": self.budget.min_free_headroom_bytes,
        }

        report = CacheReport(
            schema_version="v1.0.0",
            report_timestamp=now_iso,
            cache_root=str(self.cache_root),
            budget=budget_info,
            total_manifest_items=len(self._records),
            cached_items_count=cached_count,
            evicted_items_count=evicted_count,
            active_leases_count=self.lease_manager.total_active_leases(),
            items=items_list,
        )

        # Trigger cryptographic checksum calculation
        report.to_json()
        return report
