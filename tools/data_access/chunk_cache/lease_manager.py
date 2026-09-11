"""Thread-safe lease and reference-counting manager for cached chunks.

Ensures active chunks currently held by concurrent readers or pipelines
are never targeted for eviction.
"""
from __future__ import annotations

import datetime
import threading
import uuid
from typing import Dict, Optional, Tuple

from tools.data_access.chunk_cache.types import LeaseHandle


class LeaseManager:
    """Manages active leases on cached chunks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Map lease_id -> LeaseHandle
        self._leases: Dict[str, LeaseHandle] = {}
        # Map (dataset_id, bids_path, chunk_index) -> count of active leases
        self._refcounts: Dict[Tuple[str, str, int], int] = {}

    def acquire_lease(
        self,
        dataset_id: str,
        bids_path: str,
        chunk_index: int = 0,
        ttl_seconds: Optional[float] = None,
    ) -> LeaseHandle:
        """Acquire a protective lease on a cached chunk."""
        with self._lock:
            self._purge_expired()
            lease_id = str(uuid.uuid4())
            now = datetime.datetime.now(datetime.timezone.utc)
            expires_at = None
            if ttl_seconds is not None and ttl_seconds > 0:
                exp = now + datetime.timedelta(seconds=ttl_seconds)
                expires_at = exp.isoformat()

            handle = LeaseHandle(
                lease_id=lease_id,
                dataset_id=dataset_id,
                bids_path=bids_path,
                chunk_index=chunk_index,
                acquired_at=now.isoformat(),
                expires_at=expires_at,
            )

            key = (dataset_id, bids_path, chunk_index)
            self._leases[lease_id] = handle
            self._refcounts[key] = self._refcounts.get(key, 0) + 1
            return handle

    def release_lease(self, handle_or_id: LeaseHandle | str) -> bool:
        """Release a previously acquired lease."""
        lease_id = handle_or_id.lease_id if isinstance(handle_or_id, LeaseHandle) else str(handle_or_id)
        with self._lock:
            handle = self._leases.pop(lease_id, None)
            if handle is None:
                return False

            key = (handle.dataset_id, handle.bids_path, handle.chunk_index)
            curr = self._refcounts.get(key, 0)
            if curr <= 1:
                self._refcounts.pop(key, None)
            else:
                self._refcounts[key] = curr - 1
            return True

    def is_leased(self, dataset_id: str, bids_path: str, chunk_index: int = 0) -> bool:
        """Check whether a chunk currently has one or more active leases."""
        with self._lock:
            self._purge_expired()
            return self._refcounts.get((dataset_id, bids_path, chunk_index), 0) > 0

    def get_lease_count(self, dataset_id: str, bids_path: str, chunk_index: int = 0) -> int:
        """Return active lease reference count for a chunk."""
        with self._lock:
            self._purge_expired()
            return self._refcounts.get((dataset_id, bids_path, chunk_index), 0)

    def total_active_leases(self) -> int:
        """Return total count of active leases across all items."""
        with self._lock:
            self._purge_expired()
            return len(self._leases)

    def _purge_expired(self) -> None:
        """Internal helper to clean up expired leases (must be called with lock held)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        expired_ids = []
        for lid, handle in self._leases.items():
            if handle.expires_at:
                exp = datetime.datetime.fromisoformat(handle.expires_at)
                if now > exp:
                    expired_ids.append(lid)

        for lid in expired_ids:
            handle = self._leases.pop(lid)
            key = (handle.dataset_id, handle.bids_path, handle.chunk_index)
            curr = self._refcounts.get(key, 0)
            if curr <= 1:
                self._refcounts.pop(key, None)
            else:
                self._refcounts[key] = curr - 1
