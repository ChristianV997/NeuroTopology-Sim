"""Machine-readable policy registration for Approved Acquisition Adapter.

Provides declarative metadata describing the approved bounded adapter, its capabilities,
required invariants, and runtime constraints in a form compatible with the repository's
policy enforcement layer.
"""
from __future__ import annotations

from typing import Any, Dict

APPROVED_ADAPTER_REGISTRATION_SCHEMA = "NeuroTopology.ApprovedAdapterRegistration.v1"

APPROVED_BOUNDED_ADAPTER_POLICY_RECORD: Dict[str, Any] = {
    "schema_version": APPROVED_ADAPTER_REGISTRATION_SCHEMA,
    "path": "tools/data_access/approved_adapter/adapter.py",
    "symbols": [
        "ApprovedAcquisitionAdapter.plan",
        "ApprovedAcquisitionAdapter.acquire",
        "ApprovedAcquisitionAdapter.consume",
    ],
    "access_class": "approved_bounded_range_adapter",
    "requirements": [
        "explicit allow_network opt-in (fail-closed default)",
        "mandatory bounded byte ranges",
        "no full-dataset downloads",
        "no full-object downloads",
        "mandatory expected size > 0",
        "mandatory cache budget",
        "mandatory eviction policy",
        "mandatory checksum policy",
        "contained path validation",
        "consumer lease protection",
        "automatic deletion on final consumer (delete_on_final_consumer)",
        "deterministic RFC 8259 finite JSON",
    ],
    "invariants": {
        "network_enabled_by_default": False,
        "full_object_allowed_in_production": False,
        "full_dataset_allowed": False,
        "manifest_required_before_transfer": True,
        "bounded_transfer_required": True,
        "strict_finite_json_required": True,
        "lease_protection_required": True,
        "eviction_on_final_consumer_supported": True,
        "path_containment_enforced": True,
    },
}


def get_approved_adapter_policy_record() -> Dict[str, Any]:
    """Return machine-readable policy registration dictionary."""
    return dict(APPROVED_BOUNDED_ADAPTER_POLICY_RECORD)
