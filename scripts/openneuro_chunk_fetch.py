#!/usr/bin/env python3
"""CLI utility for manifest-first, bounded, resumable OpenNeuro/BIDS chunk cache.

Policies:
- Fail-closed network: downloads require explicit `--allow-network` opt-in.
- No full-dataset downloads by default: single files or byte-range chunks only.
- Strict BIDS path validation and containment within the configured cache root.
- Deterministic tamper-evident reports with cryptographic SHA-256 verification.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.data_access.chunk_cache import (
    BoundedChunkCache,
    CacheErrorCode,
    CacheReport,
    ChunkRange,
    TransferPlan,
    TransferResult,
    validate_bids_path,
    verify_cache_report_checksum,
)


def format_plan_markdown(plan: TransferPlan) -> str:
    """Format a TransferPlan as Markdown."""
    status_str = "EXECUTABLE" if plan.is_executable else "REJECTED"
    lines = [
        f"# Chunk Transfer Plan: {plan.dataset_id}",
        "",
        f"> **Status:** `{status_str}`",
        f"> **Total Requested Download:** `{plan.total_download_bytes:,} bytes`",
        f"> **Cache Usage:** `{plan.cache_bytes_used:,} / {plan.cache_bytes_max:,} bytes`",
        f"> **Available Disk:** `{plan.available_disk_bytes:,} bytes`",
        f"> **Eviction Required:** `{plan.eviction_required_bytes:,} bytes`",
        "",
    ]
    if plan.rejection_reason:
        lines.append(f"**Rejection Reason:** {plan.rejection_reason}\n")

    lines.append("## Items to Download")
    if plan.items_to_download:
        lines.append("| Dataset | BIDS Path | Chunk | Size (Bytes) |")
        lines.append("| :--- | :--- | :---: | :---: |")
        for itm in plan.items_to_download:
            lines.append(f"| `{itm['dataset_id']}` | `{itm['bids_path']}` | {itm['chunk_index']} | {itm['size_bytes']:,} |")
    else:
        lines.append("No download required; all items are already cached.\n")

    lines.append("")
    lines.append("## Already Cached Items")
    if plan.already_cached_items:
        lines.append("| Dataset | BIDS Path | Chunk | Size (Bytes) |")
        lines.append("| :--- | :--- | :---: | :---: |")
        for itm in plan.already_cached_items:
            lines.append(f"| `{itm['dataset_id']}` | `{itm['bids_path']}` | {itm['chunk_index']} | {itm['size_bytes']:,} |")
    else:
        lines.append("None.\n")

    return "\n".join(lines)


def format_report_markdown(report: CacheReport) -> str:
    """Format a CacheReport as Markdown."""
    lines = [
        "# OpenNeuro Bounded Chunk Cache Audit Report",
        "",
        f"- **Schema Version:** `{report.schema_version}`",
        f"- **Report Timestamp:** `{report.report_timestamp}`",
        f"- **Cache Root:** `{report.cache_root}`",
        f"- **Cryptographic SHA-256:** `{report.report_checksum_sha256}`",
        "",
        "## Budget & Utilization",
        f"- **Max Budget:** `{report.budget.get('max_cache_bytes', 0):,} bytes`",
        f"- **Current Occupancy:** `{report.budget.get('current_bytes', 0):,} bytes`",
        f"- **Remaining Headroom:** `{report.budget.get('remaining_budget_bytes', 0):,} bytes`",
        f"- **Total Manifest Records:** `{report.total_manifest_items}`",
        f"- **Cached Files:** `{report.cached_items_count}`",
        f"- **Evicted Records:** `{report.evicted_items_count}`",
        f"- **Active Leases:** `{report.active_leases_count}`",
        "",
        "## Manifest Items",
    ]

    if report.items:
        lines.append("| Dataset | BIDS Path | Chunk | Status | Size (Bytes) | Leases | Checksum |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |")
        for itm in report.items:
            sha = itm.get("actual_checksum") or itm.get("expected_checksum") or "n/a"
            if sha != "n/a" and len(sha) > 10:
                sha = sha[:10] + "..."
            lines.append(
                f"| `{itm['dataset_id']}` | `{itm['bids_path']}` | {itm['chunk_index']} | `{itm['status']}` | {itm['size_bytes']:,} | {itm['active_leases']} | `{sha}` |"
            )
    else:
        lines.append("Cache is empty.")

    return "\n".join(lines)


def parse_chunk_range(range_str: str | None) -> ChunkRange | None:
    """Parse 'start-end' or 'start:end' string into ChunkRange."""
    if not range_str:
        return None
    cleaned = range_str.replace(":", "-").strip()
    parts = cleaned.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid chunk range format: {range_str}. Expected 'start-end'.")
    return ChunkRange(start_byte=int(parts[0]), end_byte=int(parts[1]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenNeuro/BIDS bounded chunk cache manager.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("--cache-root", type=str, required=True, help="Absolute or relative path to cache directory.")
    parser.add_argument("--max-cache-mb", type=float, default=500.0, help="Maximum cache size in megabytes.")
    parser.add_argument("--min-headroom-mb", type=float, default=50.0, help="Minimum free disk headroom in megabytes.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json", help="Output formatting.")
    parser.add_argument("--output", type=str, default=None, help="Optional output file path to write results.")

    subparsers = parser.add_subparsers(dest="action", required=True, help="Action to execute.")

    # 1. plan
    plan_p = subparsers.add_parser("plan", help="Evaluate dry-run plan with zero network calls.")
    plan_p.add_argument("--dataset-id", type=str, required=True, help="OpenNeuro dataset ID (e.g. ds005620).")
    plan_p.add_argument("--bids-path", type=str, default=None, help="Optional specific BIDS relative path.")
    plan_p.add_argument("--chunk-index", type=int, default=0, help="Chunk index (0 for entire file).")

    # 2. register
    reg_p = subparsers.add_parser("register", help="Register object metadata into manifest before downloading.")
    reg_p.add_argument("--dataset-id", type=str, required=True, help="OpenNeuro dataset ID.")
    reg_p.add_argument("--bids-path", type=str, required=True, help="Validated BIDS relative path.")
    reg_p.add_argument("--source-uri", type=str, required=True, help="Source download URI or S3 path.")
    reg_p.add_argument("--size-bytes", type=int, required=True, help="Expected object size in bytes.")
    reg_p.add_argument("--checksum", type=str, default=None, help="Expected SHA-256 or MD5/ETag checksum.")
    reg_p.add_argument("--chunk-range", type=str, default=None, help="Optional byte range 'start-end'.")
    reg_p.add_argument("--chunk-index", type=int, default=0, help="Chunk index.")

    # 3. fetch
    fetch_p = subparsers.add_parser("fetch", help="Fetch a chunk or file (requires explicit --allow-network).")
    fetch_p.add_argument("--dataset-id", type=str, required=True, help="OpenNeuro dataset ID.")
    fetch_p.add_argument("--bids-path", type=str, required=True, help="Validated BIDS relative path.")
    fetch_p.add_argument("--chunk-index", type=int, default=0, help="Chunk index.")
    fetch_p.add_argument("--allow-network", action="store_true", default=False, help="Explicitly enable network access.")
    fetch_p.add_argument("--source-uri", type=str, default=None, help="Optional source URI if registering on-demand.")
    fetch_p.add_argument("--size-bytes", type=int, default=None, help="Optional size in bytes if registering on-demand.")
    fetch_p.add_argument("--checksum", type=str, default=None, help="Optional expected checksum.")
    fetch_p.add_argument("--chunk-range", type=str, default=None, help="Optional byte range 'start-end'.")
    fetch_p.add_argument("--max-retries", type=int, default=3, help="Max retry attempts for transient errors.")

    # 4. inspect
    subparsers.add_parser("inspect", help="Generate tamper-evident cache audit report.")

    # 5. evict
    evict_p = subparsers.add_parser("evict", help="Evict unleased chunks in LRU order.")
    evict_p.add_argument("--target-mb", type=float, default=None, help="Megabytes to reclaim.")
    evict_p.add_argument("--target-bytes", type=int, default=None, help="Bytes to reclaim.")

    # 6. cleanup
    clean_p = subparsers.add_parser("cleanup", help="Clean up stale partial downloads (.part.*).")
    clean_p.add_argument("--max-age-seconds", type=float, default=0.0, help="Minimum file age in seconds.")

    args = parser.parse_args(argv)

    max_bytes = int(args.max_cache_mb * 1024 * 1024)
    headroom_bytes = int(args.min_headroom_mb * 1024 * 1024)

    cache = BoundedChunkCache(
        cache_root=args.cache_root,
        max_cache_bytes=max_bytes,
        min_free_headroom_bytes=headroom_bytes,
    )

    result_payload: Any = None
    exit_code = 0

    if args.action == "plan":
        req = None
        if args.bids_path:
            req = [(args.bids_path, args.chunk_index)]
        plan = cache.plan(args.dataset_id, requested_items=req)
        if args.format == "markdown":
            result_payload = format_plan_markdown(plan)
        else:
            result_payload = {
                "dataset_id": plan.dataset_id,
                "is_executable": plan.is_executable,
                "rejection_reason": plan.rejection_reason,
                "total_download_bytes": plan.total_download_bytes,
                "cache_bytes_used": plan.cache_bytes_used,
                "cache_bytes_max": plan.cache_bytes_max,
                "available_disk_bytes": plan.available_disk_bytes,
                "eviction_required_bytes": plan.eviction_required_bytes,
                "items_to_download": plan.items_to_download,
                "already_cached_items": plan.already_cached_items,
            }
        exit_code = 0 if plan.is_executable else 1

    elif args.action == "register":
        cr = parse_chunk_range(args.chunk_range)
        rec = cache.register_manifest_item(
            dataset_id=args.dataset_id,
            bids_path=args.bids_path,
            source_uri=args.source_uri,
            size_bytes=args.size_bytes,
            expected_checksum=args.checksum,
            chunk_range=cr,
            chunk_index=args.chunk_index,
        )
        result_payload = {
            "dataset_id": rec.dataset_id,
            "bids_path": rec.bids_path,
            "chunk_index": rec.chunk_index,
            "status": rec.status,
            "size_bytes": rec.size_bytes,
            "expected_checksum": rec.expected_checksum,
        }

    elif args.action == "fetch":
        # Register if parameters provided
        if args.source_uri and args.size_bytes is not None:
            cr = parse_chunk_range(args.chunk_range)
            cache.register_manifest_item(
                dataset_id=args.dataset_id,
                bids_path=args.bids_path,
                source_uri=args.source_uri,
                size_bytes=args.size_bytes,
                expected_checksum=args.checksum,
                chunk_range=cr,
                chunk_index=args.chunk_index,
            )

        res = cache.fetch(
            dataset_id=args.dataset_id,
            bids_path=args.bids_path,
            chunk_index=args.chunk_index,
            allow_network=args.allow_network,
            max_retries=args.max_retries,
        )
        result_payload = {
            "success": res.success,
            "dataset_id": res.dataset_id,
            "bids_path": res.bids_path,
            "chunk_index": res.chunk_index,
            "bytes_transferred": res.bytes_transferred,
            "cached_path": res.cached_path,
            "checksum_verified": res.checksum_verified,
            "error_code": res.error_code,
            "error_message": res.error_message,
            "attempts": res.attempts,
        }
        exit_code = 0 if res.success else 2

    elif args.action == "inspect":
        report = cache.inspect()
        if args.format == "markdown":
            result_payload = format_report_markdown(report)
        else:
            result_payload = report.to_dict()

    elif args.action == "evict":
        tbytes = args.target_bytes
        if tbytes is None and args.target_mb is not None:
            tbytes = int(args.target_mb * 1024 * 1024)
        if tbytes is None:
            tbytes = 0

        reclaimed, evicted = cache.evict(tbytes)
        result_payload = {
            "reclaimed_bytes": reclaimed,
            "evicted_count": len(evicted),
            "evicted_items": [
                {"dataset_id": r.dataset_id, "bids_path": r.bids_path, "chunk_index": r.chunk_index}
                for r in evicted
            ],
        }

    elif args.action == "cleanup":
        count, reclaimed = cache.cleanup_stale_partials(max_age_seconds=args.max_age_seconds)
        result_payload = {
            "removed_partial_files": count,
            "reclaimed_bytes": reclaimed,
        }

    # Render output
    if isinstance(result_payload, str):
        output_str = result_payload
    else:
        output_str = json.dumps(result_payload, indent=2)

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(output_str, encoding="utf-8")

    print(output_str)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
