"""Declarative data-access policy and reviewed allowlists.

The allowlist names adapters and operations, not arbitrary files.  A caller
must still enforce the runtime properties recorded here: manifest-first
planning, bounded transfer, checksum verification, resumability, and an
observable cache lifecycle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

SCHEMA_VERSION = "NeuroTopology.DataAccessPolicy.v1"

# PR #346's bounded S3 adapter is intentionally registered here rather than
# by a filename-only exception.  The scanner matches the complete enclosing
# symbol and checks the declared controls structurally before allowing the
# transfer calls in those symbols.  The implementation is deliberately kept
# on PR #346's branch; registering it on main does not make the legacy
# callers in this checkout compliant.
PR346_BOUNDED_ADAPTER_REGISTRATIONS: tuple[dict[str, Any], ...] = (
    {
        "path": "validation/s3_fetchers.py",
        "symbols": [
            "BoundedS3ObjectStore.fetch_object",
            "BoundedS3ObjectStore.read_text_metadata",
        ],
        "access_class": "manifest_first_bounded_s3_range",
        "registration": "pr346",
        "control_profile": "s3_store",
        "requirements": [
            "explicit allow_network=False",
            "explicit source object identity",
            "head_object ContentLength expected size",
            "Range on every data get_object",
            "checksum state including unknown",
            "atomic partial staging",
            "explicit cache budget",
            "observable eviction",
            "contained output root",
        ],
    },
    {
        "path": "tools/stream_process_ds005917.py",
        "symbols": ["download_bold", "load_mdd_complete_subjects"],
        "access_class": "delegated_bounded_s3_range",
        "registration": "pr346",
        "control_profile": "delegated_s3_wrapper",
        "requirements": [
            "explicit allow_network=False",
            "explicit cache budget",
            "bounded chunk size for data or metadata_max_bytes for metadata",
            "delegation to BoundedS3ObjectStore",
        ],
    },
    {
        "path": "tools/stream_process_ds006644.py",
        "symbols": ["download_subject_bold", "load_group_labels"],
        "access_class": "delegated_bounded_s3_range",
        "registration": "pr346",
        "control_profile": "delegated_s3_wrapper",
        "requirements": [
            "explicit allow_network=False",
            "explicit cache budget",
            "bounded chunk size for data or metadata_max_bytes for metadata",
            "delegation to BoundedS3ObjectStore",
        ],
    },
)

POLICY_REGISTRATION_REQUIREMENTS: dict[str, Any] = {
    "schema_version": "NeuroTopology.DataAccessPolicyRegistration.v1",
    "owner": "tools/data_access/policy_enforcement",
    "registrations": [dict(item) for item in PR346_BOUNDED_ADAPTER_REGISTRATIONS],
}

APPROVED_ACQUISITION_ADAPTERS: tuple[dict[str, Any], ...] = (
    {
        "path": "tools/data_access/chunk_cache/transfer.py",
        "symbols": ["HTTPTransferAdapter.fetch_object_metadata", "HTTPTransferAdapter.transfer_chunk"],
        "access_class": "metadata_only_or_bounded_byte_range",
        "requirements": ["allow_network opt-in", "ChunkRange for data transfer", "partial staging", "checksum when declared"],
    },
    {
        "path": "tools/data_access/chunk_cache/cache_engine.py",
        "symbols": ["ChunkCacheEngine.plan", "ChunkCacheEngine.fetch_chunk"],
        "access_class": "manifest_first_bounded_cache",
        "requirements": ["explicit cache budget", "path containment", "lease-aware eviction", "manifest before transfer"],
    },
    {
        "path": "scripts/openneuro_chunk_fetch.py",
        "symbols": ["plan", "register", "fetch"],
        "access_class": "explicit_chunk_cache_cli",
        "requirements": ["network flag", "bounded chunk", "manifest record", "strict output"],
    },
    *PR346_BOUNDED_ADAPTER_REGISTRATIONS,
)

APPROVED_METADATA_OPERATIONS: tuple[dict[str, Any], ...] = (
    {
        "path": "tools/discover_openneuro_tasks.py",
        "symbol": "metadata_inventory",
        "operations": ["S3 list_objects_v2", "prefix discovery", "no object body transfer"],
    },
    {
        "path": "tools/streaming/base_runner.py",
        "symbols": ["list_s3_subjects", "list_s3_task_labels"],
        "operations": ["S3 list_objects_v2", "prefix discovery", "no object body transfer"],
    },
    {
        "path": "scripts/eeg_topology_ds005620.py",
        "symbol": "openneuro_file_inventory",
        "operations": ["OpenNeuro GraphQL inventory only", "no data transfer"],
    },
    {
        "path": "tools/data_access/chunk_cache/transfer.py",
        "symbols": ["HTTPTransferAdapter.fetch_object_metadata"],
        "operations": ["HTTP HEAD", "Content-Length/ETag metadata only"],
    },
    {
        "path": "data/dandi_nwb_ingest.py",
        "symbols": ["resolve_asset_blobs"],
        "operations": ["DANDI assets.yaml manifest metadata", "no NWB object body transfer"],
    },
)

APPROVED_LAZY_READERS: tuple[dict[str, Any], ...] = (
    {
        "path": "data/dandi_nwb_ingest.py",
        "symbols": ["open_nwb_lazy", "read_nwb_eeg_window"],
        "access_class": "lazy_remote_reader",
        "requirements": ["remfile range reads", "bounded EEG window", "explicit manifest/provenance"],
    },
)


@dataclass(frozen=True)
class DataAccessPolicy:
    """Runtime properties that every approved acquisition path must expose."""

    schema_version: str = SCHEMA_VERSION
    network_enabled_by_default: bool = False
    manifest_required_before_data: bool = True
    bounded_transfer_required: bool = True
    unknown_size_policy: str = "reject_unless_explicit_operator_override"
    checksum_policy: str = "checksum_required_when_source_provides_one; missing_is_unknown"
    partial_transfer_policy: str = "stage_as_partial_and_never_mark_complete"
    resumable_policy: str = "checkpoint_manifest_and_resume_only_verified_parts"
    retry_policy: str = "bounded_retry_count_with_observable_failures"
    eviction_policy: str = "eviction_budgeted_and_observable; never silently delete_active_lease"
    cache_root_policy: str = "explicit_and_contained"
    output_root_policy: str = "explicit_and_contained"
    full_dataset_download_policy: str = "reject"
    approved_adapters: tuple[dict[str, Any], ...] = APPROVED_ACQUISITION_ADAPTERS
    approved_metadata_operations: tuple[dict[str, Any], ...] = APPROVED_METADATA_OPERATIONS
    approved_lazy_readers: tuple[dict[str, Any], ...] = APPROVED_LAZY_READERS
    reviewed_exceptions: Mapping[str, Mapping[str, str]] = None  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["approved_adapters"] = [dict(item) for item in self.approved_adapters]
        data["approved_metadata_operations"] = [dict(item) for item in self.approved_metadata_operations]
        data["approved_lazy_readers"] = [dict(item) for item in self.approved_lazy_readers]
        data["reviewed_exceptions"] = {
            str(path): dict(value) for path, value in (self.reviewed_exceptions or {}).items()
        }
        return data


DEFAULT_POLICY = DataAccessPolicy(reviewed_exceptions={})
