"""Data models, error taxonomy, and RFC 8259 serialization for Reviewed Exceptions.

Enforces:
- Schema versioning: NeuroTopology.DataAccessReviewedException.v1
- Rejection of wildcard, repository-wide, permanent, or ownerless exceptions.
- Strict rejection of forbidden behaviors (full-dataset downloads, unbounded reads,
  missing checksums, output-root escapes, network defaults, fabricated provenance).
- Strict expiry dates and fail-closed evaluation.
- Explicit migration issue references.
- Deterministic canonical SHA-256 digests and RFC 8259 finite JSON.
"""
from __future__ import annotations

import datetime
from enum import Enum
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Set

REVIEWED_EXCEPTION_SCHEMA = "NeuroTopology.DataAccessReviewedException.v1"
EXCEPTION_REGISTRY_SCHEMA = "NeuroTopology.DataAccessExceptionRegistry.v1"

MAX_EXCEPTION_LIFESPAN_DAYS = 90

# Standard ISO-8601 date regex (YYYY-MM-DD)
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISSUE_REF_REGEX = re.compile(r"^(#\d+|GH-\d+|issue-\d+|https?://.+)$", re.IGNORECASE)


class ExceptionRecordStatus(str, Enum):
    """Lifecycle state of an exception record."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    MALFORMED = "MALFORMED"
    UNSAFE_REJECTED = "UNSAFE_REJECTED"
    WILDCARD_REJECTED = "WILDCARD_REJECTED"
    PERMANENT_REJECTED = "PERMANENT_REJECTED"
    OWNERLESS_REJECTED = "OWNERLESS_REJECTED"
    REVOKED = "REVOKED"


class RejectionReasonCode(str, Enum):
    """Granular rejection codes for invalid exception records."""
    WILDCARD_FILE = "WILDCARD_FILE"
    REPOSITORY_WIDE_SCOPE = "REPOSITORY_WIDE_SCOPE"
    MISSING_EXACT_LOCATION = "MISSING_EXACT_LOCATION"
    WILDCARD_SYMBOL = "WILDCARD_SYMBOL"
    WILDCARD_RULE = "WILDCARD_RULE"
    OWNERLESS = "OWNERLESS"
    MISSING_REVIEWER = "MISSING_REVIEWER"
    SELF_REVIEW_PROHIBITED = "SELF_REVIEW_PROHIBITED"
    PERMANENT_EXCEPTION = "PERMANENT_EXCEPTION"
    EXCESSIVE_LIFESPAN = "EXCESSIVE_LIFESPAN"
    EXPIRED = "EXPIRED"
    INVALID_DATE_FORMAT = "INVALID_DATE_FORMAT"
    MISSING_MIGRATION_ISSUE = "MISSING_MIGRATION_ISSUE"
    INVALID_MIGRATION_ISSUE = "INVALID_MIGRATION_ISSUE"
    UNSAFE_BEHAVIOR_PERMITTED = "UNSAFE_BEHAVIOR_PERMITTED"
    MISSING_PROHIBITIONS = "MISSING_PROHIBITIONS"
    MALFORMED_RECORD = "MALFORMED_RECORD"


# Forbidden behaviors that must NEVER be permitted under any exception
FORBIDDEN_PERMITTED_BEHAVIORS: dict[str, list[str]] = {
    "full_dataset_download": [
        "full_dataset_download",
        "bulk_dataset_fetch",
        "download_entire_dataset",
        "full_dataset",
        "unfiltered_dataset_clone",
        "download_all_subjects",
    ],
    "unbounded_remote_read": [
        "unbounded_remote_read",
        "unbounded_read",
        "unbounded_stream",
        "read_all_bytes",
        "infinite_stream",
        "unbounded_fetch",
    ],
    "missing_checksum": [
        "missing_checksum",
        "skip_checksum",
        "disable_checksum",
        "no_checksum",
        "ignore_checksum_mismatch",
        "bypass_integrity",
    ],
    "output_root_escape": [
        "output_root_escape",
        "escape_cache_root",
        "path_traversal",
        "uncontained_write",
        "arbitrary_filesystem_write",
        "write_outside_root",
    ],
    "network_enabled_default": [
        "network_enabled_default",
        "default_allow_network",
        "implicit_network_access",
        "always_allow_network",
        "network_default_on",
    ],
    "fabricated_provenance": [
        "fabricated_provenance",
        "fake_provenance",
        "skip_provenance",
        "synthetic_manifest",
        "mock_provenance_bypass",
        "untracked_lineage",
    ],
}


class ExceptionContractError(ValueError):
    """Raised when an exception record violates the strict exception schema."""


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
            raise ExceptionContractError(f"{path} contains non-finite float: {value}")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Enum):
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
class ReviewedExceptionRecord:
    """A strictly versioned, temporary, expiring exception for a legacy data-access finding."""
    exception_id: str
    exact_file: str
    rule_identifier: str
    owner: str
    justification: str
    migration_issue: str
    created_date: str
    expiry_date: str
    reviewer: str
    permitted_behavior: list[str]
    prohibited_behavior: list[str]
    schema_version: str = REVIEWED_EXCEPTION_SCHEMA
    exact_line: Optional[int] = None
    exact_symbol: Optional[str] = None
    status: str = ExceptionRecordStatus.ACTIVE.value
    rejection_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = finite_value(self)
        if not self.checksum:
            d_for_hash = {k: v for k, v in d.items() if k != "checksum"}
            d["checksum"] = canonical_hash(d_for_hash)
            self.checksum = d["checksum"]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewedExceptionRecord:
        """Construct a ReviewedExceptionRecord from a dictionary."""
        # Clean null-safe and finite values
        safe_data = finite_value(data)
        return cls(
            schema_version=safe_data.get("schema_version", REVIEWED_EXCEPTION_SCHEMA),
            exception_id=safe_data.get("exception_id", ""),
            exact_file=safe_data.get("exact_file", ""),
            exact_line=safe_data.get("exact_line"),
            exact_symbol=safe_data.get("exact_symbol"),
            rule_identifier=safe_data.get("rule_identifier", ""),
            owner=safe_data.get("owner", ""),
            justification=safe_data.get("justification", ""),
            migration_issue=safe_data.get("migration_issue", ""),
            created_date=safe_data.get("created_date", ""),
            expiry_date=safe_data.get("expiry_date", ""),
            reviewer=safe_data.get("reviewer", ""),
            permitted_behavior=list(safe_data.get("permitted_behavior", []) or []),
            prohibited_behavior=list(safe_data.get("prohibited_behavior", []) or []),
            status=safe_data.get("status", ExceptionRecordStatus.ACTIVE.value),
            rejection_reasons=list(safe_data.get("rejection_reasons", []) or []),
            metadata=dict(safe_data.get("metadata", {}) or {}),
            checksum=safe_data.get("checksum", ""),
        )


@dataclass
class ExceptionValidationResult:
    """Outcome of validating an exception record."""
    exception_id: str
    is_valid: bool
    status: str
    rejection_codes: list[str] = field(default_factory=list)
    rejection_messages: list[str] = field(default_factory=list)
    expires_in_days: Optional[int] = None
    record: Optional[ReviewedExceptionRecord] = None

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class ExceptionMatchResult:
    """Result of matching a policy violation against the exception registry."""
    matched: bool
    exception_id: Optional[str] = None
    rule_identifier: Optional[str] = None
    owner: Optional[str] = None
    reviewer: Optional[str] = None
    migration_issue: Optional[str] = None
    expiry_date: Optional[str] = None
    is_active: bool = False
    status: str = ExceptionRecordStatus.ACTIVE.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


@dataclass
class RegistryAuditReport:
    """Comprehensive evaluation report of all reviewed exceptions.

    CRITICAL INVARIANT:
    `compliant` is NEVER set to True based on exceptions.
    Exceptions represent tracked technical debt under migration, not compliance.
    """
    schema_version: str = EXCEPTION_REGISTRY_SCHEMA
    generated_at: str = ""
    evaluation_as_of_date: str = ""
    total_records: int = 0
    valid_active_count: int = 0
    expired_count: int = 0
    rejected_count: int = 0
    all_exceptions_valid_and_active: bool = False
    repository_compliant: bool = False  # NEVER True due to exceptions!
    compliance_declaration: str = "NON_COMPLIANT_WITH_EXCEPTIONS"
    findings_suppressed_count: int = 0  # Always 0: exceptions do NOT suppress findings
    records: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = finite_value(self)
        if not self.checksum:
            d_for_hash = {k: v for k, v in d.items() if k != "checksum"}
            d["checksum"] = canonical_hash(d_for_hash)
            self.checksum = d["checksum"]
        return d
