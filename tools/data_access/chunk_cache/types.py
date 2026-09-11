"""Typed data structures and contracts for OpenNeuro/BIDS bounded chunk cache.

Policies:
- No full-dataset download path by default.
- Network access must be explicit and fail-closed.
- Bounded cache root and maximum byte budget enforced.
- Manifest metadata fetched before data.
- Strict null-safe JSON serialization rejecting NaN and Infinity.
"""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence


class CacheItemStatus(str, Enum):
    """Lifecycle status of a cached BIDS file or chunk."""
    UNCACHED = "UNCACHED"
    CACHED = "CACHED"
    DOWNLOADING = "DOWNLOADING"
    EVICTED = "EVICTED"
    CORRUPTED = "CORRUPTED"
    STALE_PARTIAL = "STALE_PARTIAL"


class CacheErrorCode(str, Enum):
    """Granular error classifications for chunk cache operations."""
    MISSING_OBJECT = "MISSING_OBJECT"
    UNAVAILABLE = "UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NETWORK_ERROR = "NETWORK_ERROR"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    DISK_EXHAUSTION = "DISK_EXHAUSTION"
    CACHE_BUDGET_EXCEEDED = "CACHE_BUDGET_EXCEEDED"
    INVALID_BIDS_PATH = "INVALID_BIDS_PATH"
    ACTIVE_LEASE_LOCKED = "ACTIVE_LEASE_LOCKED"
    NETWORK_DISABLED = "NETWORK_DISABLED"


class TransferAdapterType(str, Enum):
    """Underlying transfer implementation."""
    HTTP = "HTTP"
    S3_BOTO3 = "S3_BOTO3"
    S3_AWSCLI = "S3_AWSCLI"
    MOCK = "MOCK"


@dataclass
class BIDSPathComponents:
    """Parsed and validated BIDS path components."""
    dataset_id: str
    subject: str
    session: str | None
    datatype: str | None
    task: str | None
    run: str | None
    acquisition: str | None
    suffix: str
    extension: str
    relative_path: str


@dataclass
class ChunkRange:
    """Byte range for sub-file or block downloads."""
    start_byte: int
    end_byte: int
    total_file_size: int | None = None

    @property
    def byte_count(self) -> int:
        if self.end_byte < self.start_byte:
            return 0
        return self.end_byte - self.start_byte + 1


@dataclass
class ManifestRecord:
    """Metadata record for a BIDS object or chunk in cache manifest."""
    dataset_id: str
    bids_path: str
    source_uri: str
    size_bytes: int
    expected_checksum: str | None = None
    actual_checksum: str | None = None
    chunk_index: int = 0
    chunk_range: ChunkRange | None = None
    status: str = CacheItemStatus.UNCACHED.value
    cached_path: str | None = None
    last_accessed_at: str = ""
    last_evicted_at: str | None = None
    lease_count: int = 0


@dataclass
class CacheBudget:
    """Cache storage budget and occupancy tracking."""
    max_cache_bytes: int
    current_bytes: int = 0
    min_free_headroom_bytes: int = 50 * 1024 * 1024  # 50 MB default headroom

    @property
    def remaining_budget_bytes(self) -> int:
        return max(0, self.max_cache_bytes - self.current_bytes)


@dataclass
class LeaseHandle:
    """Active lease token protecting a cached chunk from eviction."""
    lease_id: str
    dataset_id: str
    bids_path: str
    chunk_index: int
    acquired_at: str
    expires_at: str | None = None


@dataclass
class TransferPlan:
    """Dry-run execution plan evaluated before any network or disk transfer."""
    dataset_id: str
    requested_items: list[dict[str, Any]] = field(default_factory=list)
    already_cached_items: list[dict[str, Any]] = field(default_factory=list)
    items_to_download: list[dict[str, Any]] = field(default_factory=list)
    total_download_bytes: int = 0
    cache_bytes_used: int = 0
    cache_bytes_max: int = 0
    available_disk_bytes: int = 0
    eviction_required_bytes: int = 0
    evictable_items: list[dict[str, Any]] = field(default_factory=list)
    is_executable: bool = True
    rejection_reason: str | None = None


@dataclass
class TransferResult:
    """Outcome of a single chunk transfer attempt."""
    success: bool
    dataset_id: str
    bids_path: str
    chunk_index: int
    bytes_transferred: int
    cached_path: str | None = None
    checksum_verified: bool = False
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 1


@dataclass
class CacheReport:
    """Comprehensive, tamper-evident audit report of the chunk cache."""
    schema_version: str = "v1.0.0"
    report_timestamp: str = ""
    cache_root: str = ""
    budget: dict[str, Any] = field(default_factory=dict)
    total_manifest_items: int = 0
    cached_items_count: int = 0
    evicted_items_count: int = 0
    active_leases_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    report_checksum_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary rejecting non-finite floats."""
        def _sanitize(val: Any) -> Any:
            if isinstance(val, (str, int, bool)):
                return val
            if val is None:
                return None
            if isinstance(val, float):
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Non-compliant float in cache report: {val}")
                return val
            if isinstance(val, Enum):
                return val.value
            if isinstance(val, Path):
                return str(val)
            if isinstance(val, (list, tuple)):
                return [_sanitize(x) for x in val]
            if isinstance(val, dict):
                return {str(k): _sanitize(v) for k, v in val.items()}
            if hasattr(val, "__dataclass_fields__"):
                return {k: _sanitize(getattr(val, k)) for k in val.__dataclass_fields__}
            return str(val)

        return _sanitize(self)

    def to_json(self, indent: int = 2) -> str:
        """Produce deterministic JSON with SHA-256 digest."""
        d = self.to_dict()
        d_for_hash = dict(d)
        d_for_hash["report_checksum_sha256"] = ""
        canonical_bytes = json.dumps(
            d_for_hash,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        ).encode("utf-8")
        checksum = hashlib.sha256(canonical_bytes).hexdigest()
        d["report_checksum_sha256"] = checksum
        self.report_checksum_sha256 = checksum
        return json.dumps(d, indent=indent, sort_keys=True, allow_nan=False)


def verify_cache_report_checksum(report_dict: dict[str, Any]) -> bool:
    """Verify cryptographic SHA-256 integrity of a CacheReport dictionary."""
    reported = report_dict.get("report_checksum_sha256", "")
    if not reported:
        return False
    d = dict(report_dict)
    d["report_checksum_sha256"] = ""
    canonical_bytes = json.dumps(
        d,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")
    expected = hashlib.sha256(canonical_bytes).hexdigest()
    return reported == expected
