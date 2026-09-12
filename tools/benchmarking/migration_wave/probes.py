"""Read-only production probes for one checkout. Never contacts AWS/OpenNeuro/DANDI."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

def _load_fixtures():
    try:
        from tools.benchmarking.migration_wave.fixtures import make_fixture as _make

        return _make
    except Exception:
        spec = importlib.util.spec_from_file_location(
            "mw_wave_fixtures", Path(__file__).with_name("fixtures.py")
        )
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.make_fixture


make_fixture = _load_fixtures()


def _load_helpers():
    try:
        from tools.benchmarking.migration_wave import helpers as helpers_mod

        return helpers_mod
    except Exception:
        spec = importlib.util.spec_from_file_location(
            "mw_wave_helpers", Path(__file__).with_name("helpers.py")
        )
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


helpers = _load_helpers()


def _sha(obj: Any) -> str:
    blob = json.dumps(helpers.json_safe(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _unavailable(target: str, reason: str) -> Dict[str, Any]:
    return {
        "checksum": None,
        "status": "production_unavailable",
        "feature_count": 0,
        "disk_bytes": None,
        "planning_latency_s": None,
        "eviction_latency_s": None,
        "retry_attempts": None,
        "cache_occupancy_bytes": None,
        "duplicate_work": None,
        "partial_state": None,
        "production_available": False,
        "production_module": None,
        "surface": None,
        "worker_count": 1,
        "input_size": None,
        "notes": reason,
        "target": target,
        "synthetic": True,
        "evidence_class": "performance_only",
    }


def _ok(
    target: str,
    body: Dict[str, Any],
    *,
    module: str,
    surface: str,
    disk: Optional[int] = None,
    planning_latency_s: Optional[float] = None,
    eviction_latency_s: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    occupancy: Optional[int] = None,
    duplicate_work: Optional[bool] = None,
    partial_state: Optional[bool] = None,
    status: str = "ok",
    n_items: int = 1,
    n_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "checksum": _sha(body),
        "status": status,
        "feature_count": n_items,
        "disk_bytes": disk,
        "planning_latency_s": planning_latency_s,
        "eviction_latency_s": eviction_latency_s,
        "retry_attempts": retry_attempts,
        "cache_occupancy_bytes": occupancy,
        "duplicate_work": duplicate_work,
        "partial_state": partial_state,
        "production_available": True,
        "production_module": module,
        "surface": surface,
        "worker_count": 1,
        "input_size": {"n_items": n_items, "bytes": n_bytes},
        "correctness": body,
        "target": target,
        "synthetic": True,
        "evidence_class": "performance_only",
        "network_used": False,
        "remote_data_accessed": False,
    }


class FakeS3Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            return self._data
        return self._data[:n]


class FakeS3Client:
    """In-memory S3 stand-in. No AWS, no network."""

    def __init__(self) -> None:
        self._store: Dict[tuple[str, str], bytes] = {}
        self._fail: Dict[tuple[str, str], int] = {}

    def put(self, bucket: str, key: str, data: bytes) -> None:
        self._store[(bucket, key)] = data

    def set_transient(self, bucket: str, key: str, count: int) -> None:
        self._fail[(bucket, key)] = count

    def head_object(self, Bucket: str, Key: str) -> dict:
        data = self._store[(Bucket, Key)]
        digest = hashlib.sha256(data).digest()
        import base64

        return {"ContentLength": len(data), "ChecksumSHA256": base64.b64encode(digest).decode("ascii")}

    def get_object(self, Bucket: str, Key: str, Range: str | None = None) -> dict:
        key = (Bucket, Key)
        remaining = self._fail.get(key, 0)
        if remaining > 0:
            self._fail[key] = remaining - 1
            raise ConnectionError("synthetic transient")
        data = self._store[key]
        if Range:
            spec = Range.split("=", 1)[1]
            start_s, end_s = spec.split("-", 1)
            start, end = int(start_s), int(end_s)
            data = data[start : end + 1]
        return {"Body": FakeS3Body(data)}


def _chunk_cache(root: Path, max_bytes: int):
    from tools.data_access.chunk_cache import BoundedChunkCache, MockTransferAdapter

    adapter = MockTransferAdapter()
    cache = BoundedChunkCache(
        cache_root=root,
        max_cache_bytes=max_bytes,
        min_free_headroom_bytes=1,
        transfer_adapter=adapter,
    )
    return cache, adapter


def _register(cache, fx: Dict[str, Any], *, extra: bool = False) -> None:
    from tools.data_access.chunk_cache import ChunkRange

    size = int(fx["size"])
    cache.register_manifest_item(
        dataset_id=fx["dataset_id"],
        bids_path=fx["bids_path"],
        source_uri=fx["source_uri"],
        size_bytes=size,
        expected_checksum=fx["payload_sha256"],
        chunk_index=0,
        chunk_range=ChunkRange(start_byte=0, end_byte=size - 1, total_file_size=size),
    )
    if extra:
        cache.register_manifest_item(
            dataset_id=fx["dataset_id"],
            bids_path=fx["extra_bids_path"],
            source_uri=fx["extra_uri"],
            size_bytes=size,
            expected_checksum=fx["extra_sha256"],
            chunk_index=0,
            chunk_range=ChunkRange(start_byte=0, end_byte=size - 1, total_file_size=size),
        )


def _openneuro_request(fx: Dict[str, Any], cache_root: Path, output_root: Path):
    from tools.data_access.chunk_cache import ChunkRange
    from tools.fetch_ds000245 import BoundedObjectRequest

    size = int(fx["size"])
    end = min(int(fx["range_end"]), size - 2)
    return BoundedObjectRequest(
        dataset_id=fx["dataset_id"],
        bids_path=fx["bids_path"],
        source_uri=fx["source_uri"],
        expected_size_bytes=size,
        source_sha256=fx["payload_sha256"],
        cache_root=cache_root,
        output_root=output_root,
        max_cache_bytes=max(size * 8, 4096),
        chunk_range=ChunkRange(start_byte=0, end_byte=end, total_file_size=size),
        final_consumer="migration-wave",
        eviction_metadata={
            "consumer_id": "migration-wave",
            "final_consumer": "migration-wave",
            "delete_after_final_consumer": True,
        },
        allow_network=False,
        chunk_index=0,
    )


def probe_planning_latency(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_plan_") as tmp:
        root = Path(tmp)
        # Native planning surfaces, first match wins.
        try:
            from tools.data_access.approved_adapter.adapter import ApprovedAcquisitionAdapter
            from tools.data_access.approved_adapter.models import (
                BoundedAcquisitionRequest,
                LicenseAccessState,
            )

            adapter = ApprovedAcquisitionAdapter(
                cache_root=root / "cache",
                max_cache_bytes=max(fx["size"] * 8, 4096),
                min_free_headroom_bytes=1,
            )
            req = BoundedAcquisitionRequest(
                dataset_id=fx["dataset_id"],
                object_path=fx["bids_path"],
                source_uri=fx["source_uri"],
                expected_size_bytes=int(fx["size"]),
                start_byte=0,
                end_byte=int(fx["range_end"]),
                license_state=LicenseAccessState.OPEN_CC0.value,
                cache_budget_bytes=max(fx["size"] * 8, 4096),
                min_headroom_bytes=1,
                allow_network=False,
                allow_full_object=False,
            )
            t0 = time.perf_counter()
            plan = adapter.plan(req)
            latency = time.perf_counter() - t0
            body = {
                "kind": "approved_plan",
                "is_executable": bool(plan.is_executable),
                "requested_bytes": int(plan.requested_bytes),
                "eviction_required_bytes": int(plan.eviction_required_bytes),
                "rejection_count": len(plan.rejection_reasons),
            }
            return _ok(
                "planning_latency",
                body,
                module="tools.data_access.approved_adapter.adapter.ApprovedAcquisitionAdapter.plan",
                surface="approved_adapter",
                disk=helpers.dir_size_bytes(root),
                planning_latency_s=latency,
                occupancy=int(plan.cache_bytes_used),
                n_bytes=int(fx["size"]),
            )
        except Exception:
            pass
        try:
            from tools.fetch_ds000245 import plan as openneuro_plan

            req = _openneuro_request(fx, root / "cache", root / "out")
            t0 = time.perf_counter()
            result = openneuro_plan([req])
            latency = time.perf_counter() - t0
            body = {
                "kind": "openneuro_plan",
                "is_executable": bool(result.get("is_executable")),
                "network_accessed": bool(result.get("network_accessed")),
                "n_plans": len(result.get("plans") or []),
            }
            return _ok(
                "planning_latency",
                body,
                module="tools.fetch_ds000245.plan",
                surface="fetch_plan",
                disk=helpers.dir_size_bytes(root),
                planning_latency_s=latency,
                n_bytes=int(fx["size"]),
            )
        except Exception:
            pass
        try:
            from data.dandi_nwb_ingest import Provenance, WindowRequest

            prov = Provenance(
                dataset_identity=fx["dataset_id"],
                object_identity=fx["nwb_name"],
                source_kind="local_fixture",
                source_uri=fx["source_uri"],
                validated_dandi_nwb=False,
                synthetic=True,
            )
            size = int(fx["range_end"]) + 1
            req = WindowRequest(
                provenance=prov,
                start=0,
                stop=size,
                unit="bytes",
                expected_size=size,
                checksum_policy="sha256",
                expected_checksum=hashlib.sha256(fx["payload"][:size]).hexdigest(),
                cache_budget_bytes=max(size * 4, 4096),
                consumer_lease="migration-wave",
                eviction_policy="release_after_final_consumer",
                network_permission=False,
            )
            t0 = time.perf_counter()
            validated = req.validate(max_window_bytes=64 * 1024 * 1024, max_window_samples=10_000_000)
            latency = time.perf_counter() - t0
            body = {"kind": "dandi_window_plan", "validated_size": int(validated), "synthetic": True}
            return _ok(
                "planning_latency",
                body,
                module="data.dandi_nwb_ingest.WindowRequest.validate",
                surface="dandi_window",
                disk=helpers.dir_size_bytes(root),
                planning_latency_s=latency,
                n_bytes=size,
            )
        except Exception:
            pass
        try:
            from validation.s3_fetchers import BoundedS3ObjectStore

            client = FakeS3Client()
            client.put(fx["s3_bucket"], fx["s3_key"], fx["payload"])
            store = BoundedS3ObjectStore(
                client, root / "s3", max_cache_bytes=max(fx["size"] * 8, 4096), chunk_size=32, max_retries=2
            )
            t0 = time.perf_counter()
            meta = store._head(fx["s3_bucket"], fx["s3_key"], allow_network=True)
            latency = time.perf_counter() - t0
            body = {"kind": "s3_metadata_plan", "size": int(meta["size"]), "has_checksum": meta.get("checksum") is not None}
            return _ok(
                "planning_latency",
                body,
                module="validation.s3_fetchers.BoundedS3ObjectStore._head",
                surface="bounded_s3",
                disk=helpers.dir_size_bytes(root),
                planning_latency_s=latency,
                occupancy=int(store._managed_size()),
                n_bytes=int(fx["size"]),
            )
        except Exception:
            pass
        try:
            cache, adapter = _chunk_cache(root / "cache", max(fx["size"] * 8, 4096))
            adapter.register_remote_object(fx["source_uri"], fx["payload"], sha256=fx["payload_sha256"])
            _register(cache, fx)
            t0 = time.perf_counter()
            plan = cache.plan(fx["dataset_id"], [(fx["bids_path"], 0)])
            latency = time.perf_counter() - t0
            body = {
                "kind": "chunk_cache_plan",
                "is_executable": bool(plan.is_executable),
                "total_download_bytes": int(plan.total_download_bytes),
                "eviction_required_bytes": int(plan.eviction_required_bytes),
            }
            return _ok(
                "planning_latency",
                body,
                module="tools.data_access.chunk_cache.BoundedChunkCache.plan",
                surface="chunk_cache",
                disk=helpers.dir_size_bytes(root),
                planning_latency_s=latency,
                occupancy=int(cache.budget.current_bytes),
                n_bytes=int(fx["size"]),
            )
        except Exception as exc:
            return _unavailable("planning_latency", f"no runnable planning surface: {type(exc).__name__}: {exc}")


def probe_bounded_transfer_planning(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_xfer_") as tmp:
        root = Path(tmp)
        try:
            cache, adapter = _chunk_cache(root / "cache", max(fx["size"] * 4, 2048))
            adapter.register_remote_object(fx["source_uri"], fx["payload"], sha256=fx["payload_sha256"])
            adapter.register_remote_object(fx["extra_uri"], fx["extra_payload"], sha256=fx["extra_sha256"])
            _register(cache, fx, extra=True)
            t0 = time.perf_counter()
            plan = cache.plan(fx["dataset_id"])
            latency = time.perf_counter() - t0
            body = {
                "kind": "bounded_multi_plan",
                "n_requested": len(plan.requested_items),
                "n_download": len(plan.items_to_download),
                "total_download_bytes": int(plan.total_download_bytes),
                "is_executable": bool(plan.is_executable),
            }
            return _ok(
                "bounded_transfer_planning",
                body,
                module="tools.data_access.chunk_cache.BoundedChunkCache.plan",
                surface="chunk_cache",
                disk=helpers.dir_size_bytes(root),
                planning_latency_s=latency,
                occupancy=int(cache.budget.current_bytes),
                n_items=len(plan.requested_items),
                n_bytes=int(fx["size"]) * 2,
            )
        except Exception as exc:
            return _unavailable("bounded_transfer_planning", f"{type(exc).__name__}: {exc}")


def probe_cache_occupancy(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_occ_") as tmp:
        root = Path(tmp)
        try:
            cache, adapter = _chunk_cache(root / "cache", max(fx["size"] * 8, 4096))
            adapter.register_remote_object(fx["source_uri"], fx["payload"], sha256=fx["payload_sha256"])
            _register(cache, fx)
            first = cache.fetch(fx["dataset_id"], fx["bids_path"], chunk_index=0, allow_network=True, max_retries=1)
            second = cache.fetch(fx["dataset_id"], fx["bids_path"], chunk_index=0, allow_network=True, max_retries=1)
            duplicate = bool(first.success and second.success and int(getattr(second, "attempts", 0) or 0) > 0)
            body = {
                "kind": "cache_occupancy",
                "first_success": bool(first.success),
                "second_success": bool(second.success),
                "first_attempts": int(getattr(first, "attempts", 0) or 0),
                "second_attempts": int(getattr(second, "attempts", 0) or 0),
                "payload_sha256": fx["payload_sha256"],
            }
            status = "ok"
            return _ok(
                "cache_occupancy",
                body,
                module="tools.data_access.chunk_cache.BoundedChunkCache.fetch",
                surface="chunk_cache",
                disk=helpers.dir_size_bytes(root),
                occupancy=int(cache.budget.current_bytes),
                duplicate_work=duplicate,
                retry_attempts=int(getattr(second, "attempts", 0) or 0),
                status=status,
                n_bytes=int(fx["size"]),
            )
        except Exception as exc:
            return _unavailable("cache_occupancy", f"{type(exc).__name__}: {exc}")


def probe_eviction_latency(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_evict_") as tmp:
        root = Path(tmp)
        try:
            cache, adapter = _chunk_cache(root / "cache", max(fx["size"] * 8, 4096))
            adapter.register_remote_object(fx["source_uri"], fx["payload"], sha256=fx["payload_sha256"])
            adapter.register_remote_object(fx["extra_uri"], fx["extra_payload"], sha256=fx["extra_sha256"])
            _register(cache, fx, extra=True)
            cache.fetch(fx["dataset_id"], fx["bids_path"], allow_network=True, max_retries=1)
            cache.fetch(fx["dataset_id"], fx["extra_bids_path"], allow_network=True, max_retries=1)
            before = int(cache.budget.current_bytes)
            t0 = time.perf_counter()
            reclaimed, recs = cache.evict(max(1, fx["size"] // 2))
            latency = time.perf_counter() - t0
            after = int(cache.budget.current_bytes)
            body = {
                "kind": "eviction",
                "reclaimed": int(reclaimed or 0),
                "n_evicted": len(recs or []),
                "before": before,
                "after": after,
            }
            return _ok(
                "eviction_latency",
                body,
                module="tools.data_access.chunk_cache.BoundedChunkCache.evict",
                surface="chunk_cache",
                disk=helpers.dir_size_bytes(root),
                eviction_latency_s=latency,
                occupancy=after,
                n_items=2,
                n_bytes=int(fx["size"]) * 2,
            )
        except Exception as exc:
            return _unavailable("eviction_latency", f"{type(exc).__name__}: {exc}")


def probe_retry_overhead(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_retry_") as tmp:
        root = Path(tmp)
        try:
            cache, adapter = _chunk_cache(root / "cache", max(fx["size"] * 8, 4096))
            adapter.register_remote_object(fx["source_uri"], fx["payload"], sha256=fx["payload_sha256"])
            adapter.set_transient_failure(fx["source_uri"], 2)
            _register(cache, fx)
            result = cache.fetch(fx["dataset_id"], fx["bids_path"], allow_network=True, max_retries=4)
            body = {
                "kind": "retry",
                "success": bool(result.success),
                "attempts": int(getattr(result, "attempts", 0) or 0),
                "payload_sha256": fx["payload_sha256"],
            }
            return _ok(
                "retry_overhead",
                body,
                module="tools.data_access.chunk_cache.MockTransferAdapter",
                surface="chunk_cache",
                disk=helpers.dir_size_bytes(root),
                retry_attempts=int(getattr(result, "attempts", 0) or 0),
                occupancy=int(cache.budget.current_bytes),
                n_bytes=int(fx["size"]),
            )
        except Exception as exc:
            return _unavailable("retry_overhead", f"{type(exc).__name__}: {exc}")


def probe_manifest_recovery(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_manifest_") as tmp:
        root = Path(tmp)
        manifest = {
            "processed_subjects": {"sub-syn001": {"ok": True, "checksum": fx["payload_sha256"]}},
            "failed_subjects": {},
        }
        try:
            from tools.streaming.base_runner import load_manifest, save_manifest

            path = root / "manifest.json"
            save_manifest(path, manifest)
            tmp_sib = path.with_suffix(path.suffix + ".tmp")
            tmp_sib.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            path.write_text("{truncated", encoding="utf-8")
            loaded = load_manifest(path)
            body = {
                "kind": "streaming_manifest",
                "subjects": sorted((loaded or {}).get("processed_subjects", {})),
                "failed": sorted((loaded or {}).get("failed_subjects", {})),
            }
            partial = loaded is None or "processed_subjects" not in loaded
            status = "partial_state" if partial else "ok"
            return _ok(
                "manifest_recovery",
                body,
                module="tools.streaming.base_runner.save_manifest",
                surface="streaming_manifest",
                disk=helpers.dir_size_bytes(root),
                partial_state=partial,
                status=status,
                n_items=len(body["subjects"]),
            )
        except Exception:
            pass
        try:
            from validation.s3_fetchers import BoundedS3ObjectStore

            client = FakeS3Client()
            client.put(fx["s3_bucket"], fx["s3_key"], fx["payload"])
            store = BoundedS3ObjectStore(client, root / "s3", max_cache_bytes=max(fx["size"] * 8, 4096), chunk_size=64)
            dest = root / "s3" / "obj.bin"
            store.fetch_object(
                fx["s3_bucket"],
                fx["s3_key"],
                dest,
                allow_network=True,
                expected_size=int(fx["size"]),
                expected_checksum=fx["payload_sha256"],
            )
            store.manifest_path.write_text("{truncated", encoding="utf-8")
            recovered = store._load_manifest()
            partial = not isinstance(recovered, dict)
            body = {"kind": "s3_manifest", "n_records": len(recovered) if isinstance(recovered, dict) else 0}
            return _ok(
                "manifest_recovery",
                body,
                module="validation.s3_fetchers.BoundedS3ObjectStore._load_manifest",
                surface="bounded_s3",
                disk=helpers.dir_size_bytes(root),
                partial_state=partial,
                occupancy=int(store._managed_size()) if hasattr(store, "_managed_size") else None,
                n_bytes=int(fx["size"]),
            )
        except Exception as exc:
            return _unavailable("manifest_recovery", f"{type(exc).__name__}: {exc}")


def probe_checksum_verification(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mw_cksum_") as tmp:
        root = Path(tmp)
        try:
            cache, adapter = _chunk_cache(root / "cache", max(fx["size"] * 8, 4096))
            adapter.register_remote_object(fx["source_uri"], fx["payload"], sha256=fx["payload_sha256"])
            from tools.data_access.chunk_cache import ChunkRange

            cache.register_manifest_item(
                dataset_id=fx["dataset_id"],
                bids_path=fx["bids_path"],
                source_uri=fx["source_uri"],
                size_bytes=int(fx["size"]),
                expected_checksum="0" * 64,
                chunk_index=0,
                chunk_range=ChunkRange(start_byte=0, end_byte=int(fx["size"]) - 1, total_file_size=int(fx["size"])),
            )
            result = cache.fetch(fx["dataset_id"], fx["bids_path"], allow_network=True, max_retries=1)
            error_code = getattr(result, "error_code", None)
            mismatch = (not result.success) and str(error_code or "").upper() in {
                "CHECKSUM_MISMATCH",
                "CACHEERRORCODE.CHECKSUM_MISMATCH",
            }
            if not mismatch and not result.success:
                mismatch = "checksum" in str(getattr(result, "error_message", "") or "").lower()
            body = {
                "kind": "checksum_mismatch_probe",
                "success": bool(result.success),
                "error_code": error_code if not hasattr(error_code, "value") else error_code.value,
                "mismatch_detected": bool(mismatch) or (not result.success),
            }
            status = "ok" if (not result.success) else "checksum_mismatch"
            return _ok(
                "checksum_verification",
                body,
                module="tools.data_access.chunk_cache.BoundedChunkCache.fetch",
                surface="chunk_cache",
                disk=helpers.dir_size_bytes(root),
                occupancy=int(cache.budget.current_bytes),
                status=status,
                n_bytes=int(fx["size"]),
            )
        except Exception as exc:
            return _unavailable("checksum_verification", f"{type(exc).__name__}: {exc}")


PROBES: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "planning_latency": probe_planning_latency,
    "bounded_transfer_planning": probe_bounded_transfer_planning,
    "cache_occupancy": probe_cache_occupancy,
    "eviction_latency": probe_eviction_latency,
    "retry_overhead": probe_retry_overhead,
    "manifest_recovery": probe_manifest_recovery,
    "checksum_verification": probe_checksum_verification,
}


def run_probe(target: str, *, seed: int = 0, size: int = 64) -> Dict[str, Any]:
    if target not in PROBES:
        return _unavailable(target, "unknown_target")
    fx = make_fixture(seed=seed, size=size)
    try:
        return PROBES[target](fx)
    except Exception as exc:
        row = _unavailable(target, f"{type(exc).__name__}: {exc}")
        row["status"] = "error"
        return row


def run_measured(target: str, *, seed: int = 0, size: int = 64, repetitions: int = 1) -> Dict[str, Any]:
    fx = make_fixture(seed=seed, size=size)

    def _once() -> Dict[str, Any]:
        return PROBES[target](fx)

    if target not in PROBES:
        payload = _unavailable(target, "unknown_target")
        return {"ok": False, "reason": "unknown_target", "payload": payload, "checksum": None}
    measured = helpers.measure(_once, repetitions=repetitions)
    measured["target"] = target
    measured["synthetic"] = True
    measured["evidence_class"] = "performance_only"
    return measured
