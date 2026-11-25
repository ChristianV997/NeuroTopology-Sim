"""Thread-safe bounded LRU cache for quantum operators and solver factorizations."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import threading
from typing import Any, Optional, Tuple

import numpy as np


class OperatorCache:
    """Thread-safe LRU cache with memory-bounded retention for expensive factorizations."""

    def __init__(self, max_entries: int = 32) -> None:
        """Initialize the operator cache.

        Args:
            max_entries: Maximum number of entries before LRU eviction.
        """
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        geometry_hash: str,
        bath_hash: str,
        method: str,
        sigma: float = 0.0,
        dimension: int = 0,
    ) -> str:
        """Construct a deterministic cache key string."""
        raw = f"{geometry_hash}|{bath_hash}|{method}|{sigma:.12g}|{dimension}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve an entry from cache, marking it most recently used."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        """Store an entry in cache, evicting oldest if capacity exceeded."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """Return cache hit/miss statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
            }

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# Global default operator cache instance
DEFAULT_OPERATOR_CACHE = OperatorCache(max_entries=32)
