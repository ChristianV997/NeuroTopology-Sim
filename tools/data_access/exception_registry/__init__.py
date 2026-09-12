"""Strict, Expiring Exception Registry for Data-Access Findings.

Enforces:
- Exact file and line/symbol targeting (no wildcards or repo-wide scope).
- Mandatory independent reviewer (no self-review).
- Mandatory migration issue tracking.
- Strict expiration date (fail-closed when expired, max 90-day lifespan).
- Strict rejection of forbidden unsafe behaviors (full-dataset downloads,
  unbounded remote reads, missing checksums, output-root escapes,
  network defaults, fabricated provenance).
- Complete separation from policy scanner (zero suppression of findings).
- Invariant: repository compliance is NEVER declared merely because an exception exists.
"""
from __future__ import annotations

from tools.data_access.exception_registry.models import (
    EXCEPTION_REGISTRY_SCHEMA,
    FORBIDDEN_PERMITTED_BEHAVIORS,
    MAX_EXCEPTION_LIFESPAN_DAYS,
    REVIEWED_EXCEPTION_SCHEMA,
    ExceptionContractError,
    ExceptionMatchResult,
    ExceptionRecordStatus,
    ExceptionValidationResult,
    RegistryAuditReport,
    RejectionReasonCode,
    ReviewedExceptionRecord,
    canonical_hash,
    finite_value,
)
from tools.data_access.exception_registry.registry import ExceptionRegistry
from tools.data_access.exception_registry.validator import validate_exception_record

__all__ = [
    "EXCEPTION_REGISTRY_SCHEMA",
    "FORBIDDEN_PERMITTED_BEHAVIORS",
    "MAX_EXCEPTION_LIFESPAN_DAYS",
    "REVIEWED_EXCEPTION_SCHEMA",
    "ExceptionContractError",
    "ExceptionMatchResult",
    "ExceptionRecordStatus",
    "ExceptionRegistry",
    "ExceptionValidationResult",
    "RegistryAuditReport",
    "RejectionReasonCode",
    "ReviewedExceptionRecord",
    "canonical_hash",
    "finite_value",
    "validate_exception_record",
]
