"""Data contracts and finite JSON serialization for Approved Acquisition Adapter.

Enforces:
- Explicit dataset, object, byte range, expected size, checksum, and license.
- Rejection of unknown-size or full-object requests by default.
- Strict RFC 8259 finite JSON (NaN and Infinity rejected).
- Deterministic cryptographic SHA-256 integrity.
"""
from __future__ import annotations

import enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, List, Mapping, Optional, Sequence

APPROVED_ACQUISITION_SCHEMA = "ApprovedAcquisitionPlan.v1"


class SourceCatalogType(str, enum.Enum):
    """Supported source archives and catalog namespaces."""
    OPENNEURO = "openneuro"
    BIDS = "bids"
    DANDI = "dandi"
    CUSTOM = "custom"


class LicenseAccessState(str, enum.Enum):
    """Explicit license and access authorization state."""
    OPEN_CC0 = "open_cc0"
    OPEN_CC_BY = "open_cc_by"
    OPEN_ACCESS = "open_access"
    RESTRICTED = "restricted"
    UNKNOWN_BLOCKED = "unknown_blocked"


class ChecksumPolicy(str, enum.Enum):
    """Integrity verification policy."""
    SHA256_STRICT = "sha256_strict"
    SHA256_IF_AVAILABLE = "sha256_if_available"
    NO_CHECKSUM = "no_checksum"


class EvictionPolicy(str, enum.Enum):
    """Lifecycle and eviction policy for acquired chunks."""
    LRU_UNLEASED = "lru_unleased"
    DELETE_ON_FINAL_CONSUMER = "delete_on_final_consumer"
    MANUAL = "manual"


class AdapterErrorCode(str, enum.Enum):
    """Granular error classification for approved acquisition."""
    NETWORK_DISABLED = "NETWORK_DISABLED"
    FULL_OBJECT_REJECTED = "FULL_OBJECT_REJECTED"
    UNKNOWN_SIZE_REJECTED = "UNKNOWN_SIZE_REJECTED"
    LICENSE_RESTRICTED = "LICENSE_RESTRICTED"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    DISK_EXHAUSTION = "DISK_EXHAUSTION"
    CACHE_BUDGET_EXCEEDED = "CACHE_BUDGET_EXCEEDED"
    ACTIVE_LEASE_LOCKED = "ACTIVE_LEASE_LOCKED"
    INVALID_SOURCE_PATH = "INVALID_SOURCE_PATH"
    INCOMPLETE_METADATA = "INCOMPLETE_METADATA"
    TRANSIENT_RETRY_EXHAUSTED = "TRANSIENT_RETRY_EXHAUSTED"


class AcquisitionContractError(ValueError):
    """Raised when an acquisition request or plan violates contract constraints."""


def finite_value(value: Any, path: str = "$") -> Any:
    """Return JSON-safe values preserving nulls and rejecting non-finite floats."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AcquisitionContractError(f"{path} contains non-finite float: {value}")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [finite_value(item, f"{path}[{idx}]") for idx, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {str(k): finite_value(v, f"{path}.{k}") for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {k: finite_value(getattr(value, k), f"{path}.{k}") for k in value.__dataclass_fields__}
    return str(value)


def canonical_hash(value: Any) -> str:
    """Deterministic SHA-256 digest over canonical JSON representation."""
    safe_val = finite_value(value)
    payload = json.dumps(
        safe_val,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class BoundedAcquisitionRequest:
    """Explicit parameters required for approved acquisition."""
    dataset_id: str
    object_path: str
    source_uri: str
    expected_size_bytes: int
    start_byte: int
    end_byte: int
    catalog_type: str = SourceCatalogType.OPENNEURO.value
    checksum_policy: str = ChecksumPolicy.SHA256_IF_AVAILABLE.value
    expected_checksum: Optional[str] = None
    cache_budget_bytes: int = 500 * 1024 * 1024  # 500 MB default
    min_headroom_bytes: int = 50 * 1024 * 1024  # 50 MB default
    eviction_policy: str = EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value
    allow_network: bool = False
    allow_full_object: bool = False
    license_state: str = LicenseAccessState.UNKNOWN_BLOCKED.value
    declared_consumers: list[str] = field(default_factory=list)


@dataclass
class BoundedAcquisitionPlan:
    """Deterministic, dry-run plan evaluated before any network or disk transfer."""
    schema_version: str = APPROVED_ACQUISITION_SCHEMA
    plan_id: str = ""
    dataset_id: str = ""
    object_path: str = ""
    catalog_type: str = ""
    source_uri: str = ""
    byte_range: dict[str, int] = field(default_factory=dict)
    expected_size_bytes: int = 0
    requested_bytes: int = 0
    checksum_policy: str = ""
    expected_checksum: Optional[str] = None
    license_state: str = ""
    license_approved: bool = False
    cache_budget_bytes: int = 0
    cache_bytes_used: int = 0
    available_disk_bytes: int = 0
    eviction_required_bytes: int = 0
    is_executable: bool = True
    rejection_reasons: list[str] = field(default_factory=list)
    created_at: str = ""
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = finite_value(self)
        if not self.checksum:
            d_for_hash = {k: v for k, v in d.items() if k != "checksum"}
            d["checksum"] = canonical_hash(d_for_hash)
            self.checksum = d["checksum"]
        return d


@dataclass
class BoundedAcquisitionResult:
    """Outcome of an approved acquisition attempt."""
    success: bool
    plan_id: str
    dataset_id: str
    object_path: str
    bytes_transferred: int
    cached_path: Optional[str] = None
    checksum_verified: bool = False
    remaining_consumers: list[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


def verify_plan_checksum(plan_dict: dict[str, Any]) -> bool:
    """Verify cryptographic SHA-256 integrity of an acquisition plan dict."""
    reported = plan_dict.get("checksum", "")
    if not reported:
        return False
    d_for_hash = {k: v for k, v in plan_dict.items() if k != "checksum"}
    expected = canonical_hash(d_for_hash)
    return reported == expected
