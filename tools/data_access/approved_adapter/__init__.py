"""Approved Acquisition Adapter for OpenNeuro/BIDS/DANDI-style sources.

Provides:
- Metadata-first dry-run planning without data byte downloads.
- Bounded byte-range acquisition with explicit limits.
- Mandatory license gating (open_cc0, open_cc_by, open_access).
- Fail-closed network permission gate.
- Consumer-tracked checkout and delete_on_final_consumer eviction.
- Legacy acquisition caller scanning and migration reporting.
- Strict RFC 8259 finite JSON serialization and SHA-256 cryptographic verification.
"""
from __future__ import annotations

from tools.data_access.approved_adapter.adapter import (
    APPROVED_LICENSES,
    ApprovedAcquisitionAdapter,
)
from tools.data_access.approved_adapter.legacy_reporter import (
    LEGACY_REPORTER_SCHEMA,
    LegacyCallerScanner,
    scan_legacy_callers,
)
from tools.data_access.approved_adapter.models import (
    APPROVED_ACQUISITION_SCHEMA,
    AcquisitionContractError,
    AdapterErrorCode,
    BoundedAcquisitionPlan,
    BoundedAcquisitionRequest,
    BoundedAcquisitionResult,
    ChecksumPolicy,
    EvictionPolicy,
    LicenseAccessState,
    SourceCatalogType,
    canonical_hash,
    finite_value,
    verify_plan_checksum,
)

__all__ = [
    "APPROVED_ACQUISITION_SCHEMA",
    "APPROVED_LICENSES",
    "AcquisitionContractError",
    "AdapterErrorCode",
    "ApprovedAcquisitionAdapter",
    "BoundedAcquisitionPlan",
    "BoundedAcquisitionRequest",
    "BoundedAcquisitionResult",
    "ChecksumPolicy",
    "EvictionPolicy",
    "LEGACY_REPORTER_SCHEMA",
    "LegacyCallerScanner",
    "LicenseAccessState",
    "SourceCatalogType",
    "canonical_hash",
    "finite_value",
    "scan_legacy_callers",
    "verify_plan_checksum",
]
