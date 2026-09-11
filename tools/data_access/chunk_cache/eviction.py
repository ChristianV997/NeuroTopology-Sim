"""Bounded eviction and stale partial cleanup manager.

Enforces LRU eviction over unleased chunks, guarantees zero deletion outside
the configured cache root, and preserves metadata manifest entries post-eviction.
"""
from __future__ import annotations

import datetime
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

from tools.data_access.chunk_cache.lease_manager import LeaseManager
from tools.data_access.chunk_cache.types import CacheItemStatus, ManifestRecord


class EvictionSecurityError(RuntimeError):
    """Raised if a file deletion targets a path outside the configured cache root."""


class BoundedEvictionManager:
    """Handles bounded LRU eviction and atomic partial cleanup."""

    def __init__(self, cache_root: Path, lease_manager: LeaseManager) -> None:
        self.cache_root = Path(cache_root).resolve()
        self.lease_manager = lease_manager

    def _verify_containment(self, target_path: Path) -> Path:
        """Verify that target_path is strictly inside cache_root."""
        resolved = Path(target_path).resolve()
        try:
            # Python 3.9+ is_relative_to
            if not resolved.is_relative_to(self.cache_root):
                raise EvictionSecurityError(
                    f"Security violation: path {resolved} is outside cache root {self.cache_root}"
                )
        except AttributeError:
            # Fallback for older python
            common = os.path.commonpath([str(resolved), str(self.cache_root)])
            if common != str(self.cache_root):
                raise EvictionSecurityError(
                    f"Security violation: path {resolved} is outside cache root {self.cache_root}"
                )
        return resolved

    def evict_bytes(
        self,
        target_bytes_to_reclaim: int,
        manifest_records: Dict[Tuple[str, str, int], ManifestRecord],
    ) -> Tuple[int, List[ManifestRecord]]:
        """Evict unleased chunks in LRU order until target_bytes_to_reclaim is satisfied.
        
        Args:
            target_bytes_to_reclaim: Number of bytes that must be freed.
            manifest_records: Mutable dictionary of manifest items.
            
        Returns:
            Tuple of (total_bytes_evicted, list of evicted ManifestRecords).
        """
        if target_bytes_to_reclaim <= 0:
            return 0, []

        # Find all unleased, cached chunks
        candidates: List[ManifestRecord] = []
        for key, rec in manifest_records.items():
            if rec.status == CacheItemStatus.CACHED.value and rec.cached_path:
                if not self.lease_manager.is_leased(rec.dataset_id, rec.bids_path, rec.chunk_index):
                    candidates.append(rec)

        # Sort by last_accessed_at ascending (LRU)
        candidates.sort(key=lambda r: r.last_accessed_at or "")

        reclaimed_bytes = 0
        evicted_records: List[ManifestRecord] = []
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for rec in candidates:
            if reclaimed_bytes >= target_bytes_to_reclaim:
                break

            if rec.cached_path:
                file_path = self._verify_containment(Path(rec.cached_path))
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    try:
                        file_path.unlink()
                    except OSError:
                        continue
                    reclaimed_bytes += file_size
                else:
                    reclaimed_bytes += rec.size_bytes

                # Update manifest entry without removing metadata
                rec.status = CacheItemStatus.EVICTED.value
                rec.cached_path = None
                rec.last_evicted_at = now_iso
                evicted_records.append(rec)

        return reclaimed_bytes, evicted_records

    def cleanup_stale_partials(self, max_age_seconds: float = 0.0) -> Tuple[int, int]:
        """Scan and remove abandoned .part.* files strictly within cache_root.
        
        Args:
            max_age_seconds: Minimum age in seconds before a partial is considered stale.
                            If 0.0, cleans up all partial files.
                            
        Returns:
            Tuple of (removed_files_count, reclaimed_bytes).
        """
        if not self.cache_root.exists():
            return 0, 0

        now = time.time()
        removed_count = 0
        reclaimed_bytes = 0

        for root, _, files in os.walk(self.cache_root):
            for fname in files:
                if ".part" in fname:
                    file_path = self._verify_containment(Path(root) / fname)
                    try:
                        st = file_path.stat()
                        age = now - st.st_mtime
                        if age >= max_age_seconds:
                            file_size = st.st_size
                            file_path.unlink()
                            removed_count += 1
                            reclaimed_bytes += file_size
                    except OSError:
                        pass

        return removed_count, reclaimed_bytes
