"""OpenNeuro/BIDS bounded chunk-download cache package."""
from __future__ import annotations

from tools.data_access.chunk_cache.bids_validator import (
    BIDSValidationError,
    normalize_bids_relative_path,
    validate_bids_path,
)
from tools.data_access.chunk_cache.cache_engine import BoundedChunkCache
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
    TransferAdapterType,
    TransferPlan,
    TransferResult,
    verify_cache_report_checksum,
)

__all__ = [
    "BoundedChunkCache",
    "LeaseManager",
    "BoundedEvictionManager",
    "EvictionSecurityError",
    "TransferAdapter",
    "MockTransferAdapter",
    "HTTPTransferAdapter",
    "compute_file_sha256",
    "validate_bids_path",
    "normalize_bids_relative_path",
    "BIDSValidationError",
    "CacheItemStatus",
    "CacheErrorCode",
    "TransferAdapterType",
    "BIDSPathComponents",
    "ChunkRange",
    "ManifestRecord",
    "CacheBudget",
    "LeaseHandle",
    "TransferPlan",
    "TransferResult",
    "CacheReport",
    "verify_cache_report_checksum",
]
