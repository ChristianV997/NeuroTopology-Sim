"""Plan bounded local outputs for explicitly requested external data.

The former script downloaded a PDB object and a three-file OpenNeuro EEG
triplet directly.  Those full-object and multi-object paths are intentionally
removed.  OpenNeuro/BIDS bytes must enter through the canonical manifest-first
chunk cache with an explicit range, provenance, budget, output root, network
decision, and eviction lifecycle.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.data_access.chunk_cache import BoundedChunkCache, ChunkRange
from tools.data_access.policy_enforcement.paths import check_path_containment
from tools.fetch_ds000245 import BoundedAccessError, BoundedObjectRequest, release_after_final_consumer


class FullObjectDownloadRejected(BoundedAccessError):
    """Raised for the removed legacy full-object or full-dataset operations."""


def download_pdb(destination: Path) -> str:
    """Reject the historical unbounded PDB download explicitly.

    This caller is retained as a compatibility seam so old automation gets an
    actionable failure instead of silently downloading data.  PDB access is
    outside the canonical OpenNeuro/BIDS adapter owned by this migration; no
    cache_budget, sha256 checksum, or eviction lifecycle can be inferred.
    """
    raise FullObjectDownloadRejected(
        "direct PDB downloads were removed; provide a separately reviewed bounded adapter and manifest"
    )


def _request_from_arguments(
    destination: Path,
    *,
    dataset_id: str,
    bids_path: str,
    source_uri: str,
    expected_size_bytes: int | None,
    source_sha256: str | None,
    cache_root: Path | None,
    output_root: Path | None,
    max_cache_bytes: int | None,
    chunk_range: ChunkRange | None,
    allow_network: bool,
    final_consumer: str,
    eviction_metadata: Mapping[str, Any] | None,
    chunk_sha256: str | None,
) -> BoundedObjectRequest:
    required = {
        "expected_size_bytes": expected_size_bytes,
        "source_sha256": source_sha256,
        "cache_root": cache_root,
        "output_root": output_root,
        "max_cache_bytes": max_cache_bytes,
        "chunk_range": chunk_range,
        "eviction_metadata": eviction_metadata,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise BoundedAccessError("explicit bounded access fields are required: " + ", ".join(missing))
    assert expected_size_bytes is not None and source_sha256 is not None
    assert cache_root is not None and output_root is not None and max_cache_bytes is not None
    assert chunk_range is not None and eviction_metadata is not None
    containment = check_path_containment(str(output_root), str(destination))
    if not containment.contained:
        raise BoundedAccessError("destination must be a distinct child of output_root")
    return BoundedObjectRequest(
        dataset_id=dataset_id,
        bids_path=bids_path,
        source_uri=source_uri,
        expected_size_bytes=expected_size_bytes,
        source_sha256=source_sha256,
        chunk_sha256=chunk_sha256,
        cache_root=cache_root,
        output_root=output_root,
        max_cache_bytes=max_cache_bytes,
        chunk_range=chunk_range,
        final_consumer=final_consumer,
        eviction_metadata=eviction_metadata,
        allow_network=allow_network,
    )


def download_eeg(
    destination: Path,
    *,
    dataset_id: str = "ds005620",
    bids_path: str | None = None,
    source_uri: str | None = None,
    expected_size_bytes: int | None = None,
    source_sha256: str | None = None,
    cache_root: Path | None = None,
    output_root: Path | None = None,
    max_cache_bytes: int | None = None,
    chunk_range: ChunkRange | None = None,
    allow_network: bool = False,
    eviction_metadata: Mapping[str, Any] | None = None,
    final_consumer: str = "fetch-real-datasets",
    chunk_sha256: str | None = None,
    transfer_adapter: Any = None,
) -> tuple[bool, str]:
    """Transfer one declared EEG range through ``BoundedChunkCache`` only."""
    if bids_path is None or source_uri is None:
        raise BoundedAccessError("bids_path and source_uri are required; multi-file/full-dataset fetch is rejected")
    request = _request_from_arguments(
        destination,
        dataset_id=dataset_id,
        bids_path=bids_path,
        source_uri=source_uri,
        expected_size_bytes=expected_size_bytes,
        source_sha256=source_sha256,
        cache_root=cache_root,
        output_root=output_root,
        max_cache_bytes=max_cache_bytes,
        chunk_range=chunk_range,
        allow_network=allow_network,
        final_consumer=final_consumer,
        eviction_metadata=eviction_metadata,
        chunk_sha256=chunk_sha256,
    )
    if request.chunk_sha256 is None:
        raise BoundedAccessError("chunk_sha256 is required for bounded transfer; missing checksum blocks execution")
    cache = BoundedChunkCache(
        request.cache_root,
        max_cache_bytes=request.max_cache_bytes,
        transfer_adapter=transfer_adapter,
    )
    cache.register_manifest_item(
        dataset_id=request.dataset_id,
        bids_path=request.normalized_bids_path,
        source_uri=request.source_uri,
        size_bytes=request.chunk_range.byte_count,
        expected_checksum=request.chunk_sha256,
        chunk_range=request.chunk_range,
        chunk_index=request.chunk_index,
    )
    result = cache.fetch(
        request.dataset_id,
        request.normalized_bids_path,
        chunk_index=request.chunk_index,
        allow_network=request.allow_network,
    )
    if not result.success:
        return False, f"{result.error_code}: {result.error_message}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result.cached_path or "", destination)
    cleanup = release_after_final_consumer(cache, request, result)
    return True, json.dumps({"status": "bounded_transfer", "cleanup": cleanup}, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="JSON manifest containing one bounded EEG request")
    parser.add_argument("--execute", action="store_true", help="Execute the declared range; otherwise print the plan")
    args = parser.parse_args(argv)
    raw = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        parser.error("manifest must be a JSON object")
    try:
        destination_value = raw.get("destination")
        cache_value = raw.get("cache_root")
        output_value = raw.get("output_root")
        chunk_value = raw.get("chunk_range")
        if not isinstance(destination_value, str) or not destination_value:
            raise BoundedAccessError("destination is required in the manifest")
        if not isinstance(chunk_value, Mapping):
            raise BoundedAccessError("chunk_range is required in the manifest")
        request = _request_from_arguments(
            Path(destination_value),
            dataset_id=str(raw.get("dataset_id", "")),
            bids_path=raw.get("bids_path"),
            source_uri=raw.get("source_uri"),
            expected_size_bytes=raw.get("expected_size_bytes"),
            source_sha256=raw.get("source_sha256"),
            cache_root=Path(str(cache_value)) if cache_value else None,
            output_root=Path(str(output_value)) if output_value else None,
            max_cache_bytes=raw.get("max_cache_bytes"),
            chunk_range=ChunkRange(**chunk_value),
            allow_network=bool(raw.get("allow_network", False)),
            eviction_metadata=raw.get("eviction_metadata"),
            final_consumer=str(raw.get("final_consumer", "fetch-real-datasets")),
            chunk_sha256=raw.get("chunk_sha256"),
        )
    except (KeyError, TypeError, ValueError, BoundedAccessError) as exc:
        parser.error(str(exc))
    if args.execute:
        try:
            ok, status = download_eeg(
                Path(destination_value),
                dataset_id=request.dataset_id,
                bids_path=request.bids_path,
                source_uri=request.source_uri,
                expected_size_bytes=request.expected_size_bytes,
                source_sha256=request.source_sha256,
                cache_root=request.cache_root,
                output_root=request.output_root,
                max_cache_bytes=request.max_cache_bytes,
                chunk_range=request.chunk_range,
                allow_network=request.allow_network,
                eviction_metadata=request.eviction_metadata,
                final_consumer=request.final_consumer,
                chunk_sha256=request.chunk_sha256,
            )
        except (KeyError, TypeError, ValueError, BoundedAccessError) as exc:
            parser.error(str(exc))
        print(json.dumps({"success": ok, "status": status}, sort_keys=True))
        return 0 if ok else 2
    print(json.dumps({"schema_version": "NeuroTopology.BoundedOpenNeuroRequest.v1", "network_accessed": False, "request": request.to_dict(), "destination": destination_value}, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
