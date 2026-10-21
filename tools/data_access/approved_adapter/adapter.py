"""Approved Acquisition Adapter wrapping canonical BoundedChunkCache.

Enforces:
- Metadata-first planning without downloading data bytes.
- Strict validation: rejects unknown-size, full-object, and unapproved licenses by default.
- Fail-closed network permission gate (`allow_network=False` by default).
- Consumer lifecycle tracking with automatic deletion on final consumer (`delete_on_final_consumer`).
- Cache budget and disk headroom verification.
- Cryptographic deterministic plan generation and finite RFC 8259 JSON serialization.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

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
)
from tools.data_access.approved_adapter.policy_registration import (
    APPROVED_ADAPTER_REGISTRATION_SCHEMA,
    APPROVED_BOUNDED_ADAPTER_POLICY_RECORD,
    get_approved_adapter_policy_record,
)
from tools.data_access.chunk_cache import (
    BoundedChunkCache,
    CacheErrorCode,
    CacheItemStatus,
    ChunkRange,
    LeaseHandle,
    MockTransferAdapter,
    TransferAdapter,
    compute_file_sha256,
    normalize_bids_relative_path,
)

logger = logging.getLogger(__name__)

APPROVED_LICENSES = {
    LicenseAccessState.OPEN_CC0.value,
    LicenseAccessState.OPEN_CC_BY.value,
    LicenseAccessState.OPEN_ACCESS.value,
}


class ApprovedAcquisitionAdapter:
    """Additive, policy-enforcing acquisition adapter for OpenNeuro/BIDS/DANDI sources."""

    def __init__(
        self,
        cache_root: str | Path,
        max_cache_bytes: int = 500 * 1024 * 1024,
        min_free_headroom_bytes: int = 50 * 1024 * 1024,
        transfer_adapter: Optional[TransferAdapter] = None,
        chunk_cache: Optional[BoundedChunkCache] = None,
    ) -> None:
        """Initialize the approved acquisition adapter.

        Args:
            cache_root: Root directory for the underlying chunk cache.
            max_cache_bytes: Maximum total bytes permitted in cache.
            min_free_headroom_bytes: Minimum free disk space reserve.
            transfer_adapter: Custom or mock transfer adapter (default: HTTP).
            chunk_cache: Existing BoundedChunkCache instance to wrap (optional).
        """
        self.cache_root = Path(cache_root).resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)

        if chunk_cache is not None:
            self.cache = chunk_cache
        else:
            self.cache = BoundedChunkCache(
                cache_root=self.cache_root,
                max_cache_bytes=max_cache_bytes,
                min_free_headroom_bytes=min_free_headroom_bytes,
                transfer_adapter=transfer_adapter,
            )

        # Consumer tracking: maps chunk_key -> {
        #   "consumers": set of consumer_ids,
        #   "lease_handle": LeaseHandle,
        #   "eviction_policy": str,
        #   "cached_path": str,
        #   "dataset_id": str,
        #   "object_path": str,
        #   "chunk_index": int
        # }
        self._consumer_registry: Dict[Tuple[str, str, int], Dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # Path Sanitization & Catalog Normalization
    # -------------------------------------------------------------------------

    def _normalize_object_path(self, catalog_type: str, object_path: str) -> str:
        """Sanitize and normalize relative object path avoiding directory traversal and root escape."""
        raw = str(object_path or "").strip()
        if not raw or raw in {"*", "**", "**/*", ".", "/", "all"}:
            raise AcquisitionContractError(f"Target object path cannot be empty or wildcard dataset selector: '{object_path}'")
        if any(c in raw for c in ["*", "?", "[", "]"]):
            raise AcquisitionContractError(f"Target object path cannot contain wildcards: '{object_path}'")

        cleaned = raw.replace("\\", "/")
        if re.match(r"^[a-zA-Z]:", raw) or raw.startswith("/") or raw.startswith("\\"):
            raise AcquisitionContractError(f"Absolute paths prohibited; must be contained relative path: '{object_path}'")

        parts = [p for p in cleaned.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            raise AcquisitionContractError(f"Directory traversal detected in object path: '{object_path}'")
        if not parts:
            raise AcquisitionContractError(f"Invalid or empty object path: '{object_path}'")
        return "/".join(parts)

    def _make_chunk_key(self, dataset_id: str, object_path: str, chunk_index: int = 0) -> Tuple[str, str, int]:
        """Compute canonical internal dictionary key."""
        return (str(dataset_id).strip(), self._normalize_object_path("generic", object_path), int(chunk_index))

    # -------------------------------------------------------------------------
    # Metadata-First Dry-Run Planning (Zero Data Bytes)
    # -------------------------------------------------------------------------

    def plan(self, request: BoundedAcquisitionRequest) -> BoundedAcquisitionPlan:
        """Evaluate acquisition feasibility and emit a tamper-evident dry-run plan.

        Performs zero network data transfers. Verifies:
        - Metadata completeness.
        - Absolute rejection of full-dataset and full-object requests in production.
        - Non-zero expected size.
        - Mandatory cache budget, eviction policy, and checksum policy.
        - Contained relative object path.
        - Approved open-access license state.
        - Cache storage budget and disk headroom limits.
        """
        rejection_reasons: List[str] = []

        # 1. Incomplete metadata checks
        if not request.dataset_id or not request.dataset_id.strip():
            rejection_reasons.append(f"{AdapterErrorCode.INCOMPLETE_METADATA.value}: dataset_id must not be empty.")
        if not request.object_path or not request.object_path.strip():
            rejection_reasons.append(f"{AdapterErrorCode.INCOMPLETE_METADATA.value}: object_path must not be empty.")
        if not request.source_uri or not request.source_uri.strip():
            rejection_reasons.append(f"{AdapterErrorCode.INCOMPLETE_METADATA.value}: source_uri must not be empty.")

        # Full-dataset rejection
        raw_obj = str(request.object_path or "").strip()
        if raw_obj in {"*", "**", "**/*", ".", "/", "all"} or any(c in raw_obj for c in ["*", "?"]):
            rejection_reasons.append(
                f"{AdapterErrorCode.FULL_DATASET_REJECTED.value}: "
                f"Full-dataset acquisition plans are strictly prohibited. Target must specify an exact individual object path."
            )

        norm_path = ""
        try:
            norm_path = self._normalize_object_path(request.catalog_type, request.object_path)
        except Exception as exc:
            rejection_reasons.append(f"{AdapterErrorCode.UNRESTRICTED_PATH_REJECTED.value}: {exc}")

        # 2. Unknown size check
        if request.expected_size_bytes is None or request.expected_size_bytes <= 0:
            rejection_reasons.append(
                f"{AdapterErrorCode.UNKNOWN_SIZE_REJECTED.value}: "
                f"expected_size_bytes must be specified and > 0 (got {request.expected_size_bytes})."
            )

        # 3. Bounded byte range checks
        requested_bytes = 0
        if request.start_byte < 0:
            rejection_reasons.append(
                f"{AdapterErrorCode.INCOMPLETE_METADATA.value}: start_byte must be >= 0 (got {request.start_byte})."
            )
        if request.end_byte < request.start_byte:
            rejection_reasons.append(
                f"{AdapterErrorCode.INCOMPLETE_METADATA.value}: "
                f"end_byte ({request.end_byte}) cannot be less than start_byte ({request.start_byte})."
            )
        else:
            requested_bytes = request.end_byte - request.start_byte + 1

        # 4. Strict full-object rejection policy (no production escape hatch)
        if request.expected_size_bytes and request.expected_size_bytes > 0:
            is_full_range = (request.start_byte == 0 and request.end_byte >= (request.expected_size_bytes - 1))
            if is_full_range:
                test_override = (
                    getattr(request, "_test_only_allow_full_object", False)
                    and os.environ.get("NEUROTOPOLOGY_ALLOW_TEST_FULL_OBJECT") == "1"
                )
                if not test_override:
                    rejection_reasons.append(
                        f"{AdapterErrorCode.FULL_OBJECT_REJECTED.value}: "
                        f"Full-object acquisition is strictly prohibited by repository policy. "
                        f"No production API can bypass this requirement. Bounded byte-range slicing is mandatory."
                    )

        # 5. Missing cache budget check
        if request.cache_budget_bytes is None or request.cache_budget_bytes <= 0:
            rejection_reasons.append(
                f"{AdapterErrorCode.MISSING_CACHE_BUDGET.value}: "
                f"cache_budget_bytes must be explicitly specified and > 0 (got {request.cache_budget_bytes})."
            )

        # 6. Missing eviction policy check
        valid_eviction_policies = {e.value for e in EvictionPolicy}
        if not request.eviction_policy or request.eviction_policy not in valid_eviction_policies:
            rejection_reasons.append(
                f"{AdapterErrorCode.MISSING_EVICTION_POLICY.value}: "
                f"eviction_policy must be one of {sorted(list(valid_eviction_policies))} (got '{request.eviction_policy}')."
            )

        # 7. Missing checksum policy check
        valid_checksum_policies = {c.value for c in ChecksumPolicy}
        if not request.checksum_policy or request.checksum_policy not in valid_checksum_policies:
            rejection_reasons.append(
                f"{AdapterErrorCode.MISSING_CHECKSUM_POLICY.value}: "
                f"checksum_policy must be one of {sorted(list(valid_checksum_policies))} (got '{request.checksum_policy}')."
            )

        # 8. License access state check
        license_approved = request.license_state in APPROVED_LICENSES
        if not license_approved:
            rejection_reasons.append(
                f"{AdapterErrorCode.LICENSE_RESTRICTED.value}: "
                f"License '{request.license_state}' is not approved for automated acquisition. "
                f"Must be one of: {sorted(list(APPROVED_LICENSES))}."
            )

        # 9. Capacity and disk headroom checks
        self.cache._recalculate_current_usage()
        current_used = self.cache.budget.current_bytes
        budget_max = request.cache_budget_bytes or self.cache.budget.max_cache_bytes
        eviction_needed = max(0, (current_used + requested_bytes) - budget_max)

        # Disk space check
        total_disk, used_disk, free_disk = shutil.disk_usage(str(self.cache_root))
        min_headroom = request.min_headroom_bytes or self.cache.budget.min_free_headroom_bytes

        if requested_bytes > budget_max:
            rejection_reasons.append(
                f"{AdapterErrorCode.CACHE_BUDGET_EXCEEDED.value}: "
                f"Requested chunk ({requested_bytes} bytes) exceeds maximum cache budget ({budget_max} bytes)."
            )

        if requested_bytes > (free_disk - min_headroom):
            rejection_reasons.append(
                f"{AdapterErrorCode.DISK_EXHAUSTION.value}: "
                f"Available disk space ({free_disk} bytes) minus headroom ({min_headroom} bytes) "
                f"is insufficient for {requested_bytes} bytes."
            )

        # Deterministic plan ID
        plan_components = {
            "catalog_type": request.catalog_type,
            "dataset_id": request.dataset_id,
            "object_path": norm_path,
            "start_byte": request.start_byte,
            "end_byte": request.end_byte,
            "expected_size_bytes": request.expected_size_bytes,
        }
        plan_id = f"plan-{canonical_hash(plan_components)[:16]}"
        now_iso = datetime.timezone.utc and datetime.datetime.now(datetime.timezone.utc).isoformat()

        plan = BoundedAcquisitionPlan(
            schema_version=APPROVED_ACQUISITION_SCHEMA,
            plan_id=plan_id,
            dataset_id=request.dataset_id,
            object_path=norm_path,
            catalog_type=request.catalog_type,
            source_uri=request.source_uri,
            byte_range={"start_byte": request.start_byte, "end_byte": request.end_byte},
            expected_size_bytes=request.expected_size_bytes or 0,
            requested_bytes=requested_bytes,
            checksum_policy=request.checksum_policy,
            expected_checksum=request.expected_checksum,
            license_state=request.license_state,
            license_approved=license_approved,
            cache_budget_bytes=budget_max,
            cache_bytes_used=current_used,
            available_disk_bytes=free_disk,
            eviction_required_bytes=eviction_needed,
            is_executable=(len(rejection_reasons) == 0),
            rejection_reasons=rejection_reasons,
            created_at=now_iso,
        )
        # Compute self-checksum
        plan.to_dict()
        return plan

    # -------------------------------------------------------------------------
    # Execution & Chunk Fetching
    # -------------------------------------------------------------------------

    def acquire(
        self,
        request: BoundedAcquisitionRequest,
        chunk_index: int = 0,
        max_retries: int = 3,
    ) -> BoundedAcquisitionResult:
        """Execute an approved bounded acquisition request.

        Enforces:
        - Dry-run plan evaluation first.
        - Fail-closed network permission gate (`allow_network=False` fails immediately).
        - Manifest registration.
        - Protective lease acquisition for declared consumers.
        - Strict checksum verification if configured.
        """
        # 1. Evaluate plan
        plan = self.plan(request)
        if not plan.is_executable:
            first_err = plan.rejection_reasons[0] if plan.rejection_reasons else "Plan not executable"
            err_code = first_err.split(":")[0].strip()
            return BoundedAcquisitionResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_id=request.dataset_id,
                object_path=request.object_path,
                bytes_transferred=0,
                cached_path=None,
                checksum_verified=False,
                remaining_consumers=list(request.declared_consumers),
                error_code=err_code,
                error_message="; ".join(plan.rejection_reasons),
                attempts=0,
            )

        # 2. Fail-closed network permission gate
        if not request.allow_network:
            return BoundedAcquisitionResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_id=request.dataset_id,
                object_path=plan.object_path,
                bytes_transferred=0,
                cached_path=None,
                checksum_verified=False,
                remaining_consumers=list(request.declared_consumers),
                error_code=AdapterErrorCode.NETWORK_DISABLED.value,
                error_message="Network access is disabled (allow_network=False). Transfer aborted.",
                attempts=0,
            )

        # 3. Register manifest item
        chunk_range = ChunkRange(
            start_byte=request.start_byte,
            end_byte=request.end_byte,
            total_file_size=request.expected_size_bytes,
        )
        self.cache.register_manifest_item(
            dataset_id=request.dataset_id,
            bids_path=plan.object_path,
            source_uri=request.source_uri,
            size_bytes=plan.requested_bytes,
            expected_checksum=request.expected_checksum,
            chunk_range=chunk_range,
            chunk_index=chunk_index,
        )

        # 4. Acquire lease if consumers are declared
        lease_handle: Optional[LeaseHandle] = None
        key = self._make_chunk_key(request.dataset_id, plan.object_path, chunk_index)

        if request.declared_consumers:
            lease_handle = self.cache.acquire_lease(
                dataset_id=request.dataset_id,
                bids_path=plan.object_path,
                chunk_index=chunk_index,
            )
            self._consumer_registry[key] = {
                "consumers": set(request.declared_consumers),
                "lease_handle": lease_handle,
                "eviction_policy": request.eviction_policy,
                "dataset_id": request.dataset_id,
                "object_path": plan.object_path,
                "chunk_index": chunk_index,
                "cached_path": None,
            }

        # 5. Perform fetch via underlying cache engine
        res = self.cache.fetch(
            dataset_id=request.dataset_id,
            bids_path=plan.object_path,
            chunk_index=chunk_index,
            allow_network=True,
            max_retries=max_retries,
        )

        if not res.success:
            # Release lease on fetch failure
            if lease_handle:
                self.cache.release_lease(lease_handle)
                self._consumer_registry.pop(key, None)

            # Map chunk cache error code to adapter error code
            code_mapping = {
                CacheErrorCode.NETWORK_DISABLED.value: AdapterErrorCode.NETWORK_DISABLED.value,
                CacheErrorCode.CHECKSUM_MISMATCH.value: AdapterErrorCode.CHECKSUM_MISMATCH.value,
                CacheErrorCode.DISK_EXHAUSTION.value: AdapterErrorCode.DISK_EXHAUSTION.value,
                CacheErrorCode.CACHE_BUDGET_EXCEEDED.value: AdapterErrorCode.CACHE_BUDGET_EXCEEDED.value,
                CacheErrorCode.ACTIVE_LEASE_LOCKED.value: AdapterErrorCode.ACTIVE_LEASE_LOCKED.value,
                CacheErrorCode.NETWORK_ERROR.value: AdapterErrorCode.TRANSIENT_RETRY_EXHAUSTED.value,
            }
            err_code = code_mapping.get(res.error_code or "", res.error_code)

            return BoundedAcquisitionResult(
                success=False,
                plan_id=plan.plan_id,
                dataset_id=request.dataset_id,
                object_path=plan.object_path,
                bytes_transferred=res.bytes_transferred,
                cached_path=None,
                checksum_verified=False,
                remaining_consumers=list(request.declared_consumers),
                error_code=err_code,
                error_message=res.error_message,
                attempts=res.attempts,
            )

        # 6. Post-fetch checksum policy verification
        checksum_verified = False
        if res.cached_path and Path(res.cached_path).is_file():
            if request.expected_checksum:
                actual_cs = compute_file_sha256(Path(res.cached_path))
                if actual_cs.lower() == request.expected_checksum.lower():
                    checksum_verified = True
                else:
                    # Checksum mismatch!
                    if lease_handle:
                        self.cache.release_lease(lease_handle)
                        self._consumer_registry.pop(key, None)
                    return BoundedAcquisitionResult(
                        success=False,
                        plan_id=plan.plan_id,
                        dataset_id=request.dataset_id,
                        object_path=plan.object_path,
                        bytes_transferred=res.bytes_transferred,
                        cached_path=None,
                        checksum_verified=False,
                        remaining_consumers=list(request.declared_consumers),
                        error_code=AdapterErrorCode.CHECKSUM_MISMATCH.value,
                        error_message=(
                            f"Checksum mismatch for acquired chunk: "
                            f"expected {request.expected_checksum}, calculated {actual_cs}"
                        ),
                        attempts=res.attempts,
                    )
            elif request.checksum_policy == ChecksumPolicy.SHA256_STRICT.value:
                # Strict checksum requested but none provided
                if lease_handle:
                    self.cache.release_lease(lease_handle)
                    self._consumer_registry.pop(key, None)
                return BoundedAcquisitionResult(
                    success=False,
                    plan_id=plan.plan_id,
                    dataset_id=request.dataset_id,
                    object_path=plan.object_path,
                    bytes_transferred=res.bytes_transferred,
                    cached_path=None,
                    checksum_verified=False,
                    remaining_consumers=list(request.declared_consumers),
                    error_code=AdapterErrorCode.CHECKSUM_MISMATCH.value,
                    error_message="Strict checksum verification required but expected_checksum was not supplied.",
                    attempts=res.attempts,
                )

        if key in self._consumer_registry:
            self._consumer_registry[key]["cached_path"] = res.cached_path

        return BoundedAcquisitionResult(
            success=True,
            plan_id=plan.plan_id,
            dataset_id=request.dataset_id,
            object_path=plan.object_path,
            bytes_transferred=res.bytes_transferred,
            cached_path=res.cached_path,
            checksum_verified=checksum_verified or res.checksum_verified,
            remaining_consumers=list(request.declared_consumers),
            error_code=None,
            error_message=None,
            attempts=res.attempts,
        )

    # -------------------------------------------------------------------------
    # Consumer Lifecycle & Eviction on Final Consumer
    # -------------------------------------------------------------------------

    def consume(
        self,
        dataset_id: str,
        object_path: str,
        consumer_id: str,
        chunk_index: int = 0,
    ) -> Dict[str, Any]:
        """Acknowledge chunk consumption by a declared consumer.

        When the final consumer finishes processing:
        - The protective lease is released.
        - If eviction_policy is DELETE_ON_FINAL_CONSUMER, the chunk is unlinked
          and marked EVICTED in the cache manifest immediately.

        Returns:
            Dict containing remaining_consumers, lease_released (bool), and evicted (bool).
        """
        key = self._make_chunk_key(dataset_id, object_path, chunk_index)
        norm_path = key[1]
        manifest_key = (str(dataset_id).strip(), norm_path, int(chunk_index))

        entry = self._consumer_registry.get(key)
        if not entry:
            return {
                "remaining_consumers": [],
                "lease_released": False,
                "evicted": False,
                "message": f"No active consumer registry entry for {key}.",
            }

        consumers: Set[str] = entry["consumers"]
        consumers.discard(consumer_id)

        lease_released = False
        evicted = False

        if len(consumers) == 0:
            # All declared consumers have finished
            lease_handle = entry.get("lease_handle")
            if lease_handle:
                self.cache.release_lease(lease_handle)
                lease_released = True

            eviction_policy = entry.get("eviction_policy", EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value)
            if eviction_policy == EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value:
                # Evict file immediately
                rec = self.cache._records.get(manifest_key)
                if rec and rec.cached_path and Path(rec.cached_path).is_file():
                    try:
                        p = Path(rec.cached_path)
                        p.unlink(missing_ok=True)
                        evicted = True
                    except Exception as exc:
                        logger.warning("Failed to delete chunk file %s: %s", rec.cached_path, exc)

                if rec:
                    rec.status = CacheItemStatus.EVICTED.value
                    rec.cached_path = None
                    rec.last_evicted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    self.cache._save_manifest()
                    self.cache._recalculate_current_usage()

            self._consumer_registry.pop(key, None)

        return {
            "remaining_consumers": sorted(list(consumers)),
            "lease_released": lease_released,
            "evicted": evicted,
            "message": "Consumer acknowledged.",
        }

    def cleanup_stale_partials(self, max_age_seconds: float = 0.0) -> Tuple[int, int]:
        """Scan and remove abandoned partial files within cache root."""
        return self.cache.cleanup_stale_partials(max_age_seconds=max_age_seconds)

    def get_policy_registration(self) -> Dict[str, Any]:
        """Return machine-readable registration metadata for policy enforcement."""
        return get_approved_adapter_policy_record()
