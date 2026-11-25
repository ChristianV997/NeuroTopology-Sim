#!/usr/bin/env python3
"""CLI utility for approved bounded data acquisition planning and execution.

Provides:
- Metadata-first dry-run planning (zero data byte downloads).
- Fail-closed network permission gate (`--allow-network` required to acquire).
- Strict validation: unknown size, unapproved license, and full-object requests rejected.
- Consumer-tracked checkout and delete-on-final-consumer eviction.
- Legacy acquisition caller audit scanner and migration reporting.
- Deterministic RFC 8259 finite JSON output and SHA-256 verification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Sequence

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.data_access.approved_adapter import (
    APPROVED_ACQUISITION_SCHEMA,
    ApprovedAcquisitionAdapter,
    BoundedAcquisitionPlan,
    BoundedAcquisitionRequest,
    BoundedAcquisitionResult,
    ChecksumPolicy,
    EvictionPolicy,
    LegacyCallerScanner,
    LicenseAccessState,
    SourceCatalogType,
    finite_value,
    scan_legacy_callers,
    verify_plan_checksum,
)


def format_plan_markdown(plan: BoundedAcquisitionPlan) -> str:
    """Render BoundedAcquisitionPlan as markdown."""
    status_badge = "**APPROVED (EXECUTABLE)**" if plan.is_executable else "**REJECTED**"
    lines = [
        f"# Approved Bounded Acquisition Plan: `{plan.plan_id}`",
        "",
        f"- **Schema**: `{plan.schema_version}`",
        f"- **Status**: {status_badge}",
        f"- **Catalog Type**: `{plan.catalog_type}`",
        f"- **Dataset ID**: `{plan.dataset_id}`",
        f"- **Object Path**: `{plan.object_path}`",
        f"- **Source URI**: `{plan.source_uri}`",
        f"- **Byte Range**: `[{plan.byte_range.get('start_byte', 0)}, {plan.byte_range.get('end_byte', 0)}]`",
        f"- **Requested Bytes**: `{plan.requested_bytes:,} bytes`",
        f"- **Expected Total Size**: `{plan.expected_size_bytes:,} bytes`",
        f"- **License State**: `{plan.license_state}` (Approved: `{plan.license_approved}`)",
        f"- **Checksum Policy**: `{plan.checksum_policy}`",
        f"- **Expected Checksum**: `{plan.expected_checksum or 'None'}`",
        f"- **Cache Usage**: `{plan.cache_bytes_used:,} / {plan.cache_budget_bytes:,} bytes`",
        f"- **Available Disk**: `{plan.available_disk_bytes:,} bytes`",
        f"- **Plan Integrity SHA-256**: `{plan.checksum}`",
        "",
    ]

    if plan.rejection_reasons:
        lines.append("## Rejection Reasons")
        for reason in plan.rejection_reasons:
            lines.append(f"- :x: {reason}")
        lines.append("")
    else:
        lines.append("## Verification Summary")
        lines.append("- :white_check_mark: Non-zero size specified.")
        lines.append("- :white_check_mark: Bounded byte range validated.")
        lines.append("- :white_check_mark: License approved for automated acquisition.")
        lines.append("- :white_check_mark: Cache budget and disk headroom adequate.")
        lines.append("")

    return "\n".join(lines)


def format_result_markdown(result: BoundedAcquisitionResult) -> str:
    """Render BoundedAcquisitionResult as markdown."""
    status = "**SUCCESS**" if result.success else "**FAILED**"
    lines = [
        f"# Bounded Acquisition Execution Result",
        "",
        f"- **Status**: {status}",
        f"- **Plan ID**: `{result.plan_id}`",
        f"- **Dataset ID**: `{result.dataset_id}`",
        f"- **Object Path**: `{result.object_path}`",
        f"- **Bytes Transferred**: `{result.bytes_transferred:,} bytes`",
        f"- **Cached Path**: `{result.cached_path or 'None'}`",
        f"- **Checksum Verified**: `{result.checksum_verified}`",
        f"- **Remaining Consumers**: `{result.remaining_consumers}`",
        f"- **Attempts**: `{result.attempts}`",
        "",
    ]
    if not result.success:
        lines.append(f"## Failure Details")
        lines.append(f"- **Error Code**: `{result.error_code}`")
        lines.append(f"- **Error Message**: {result.error_message}")
        lines.append("")

    return "\n".join(lines)


def _build_request_from_args(args: argparse.Namespace) -> BoundedAcquisitionRequest:
    """Construct BoundedAcquisitionRequest from CLI args or input file."""
    if getattr(args, "request_file", None):
        rf = Path(args.request_file)
        if not rf.is_file():
            raise FileNotFoundError(f"Request file not found: {rf}")
        data = json.loads(rf.read_text(encoding="utf-8"))
        return BoundedAcquisitionRequest(
            dataset_id=data.get("dataset_id", ""),
            object_path=data.get("object_path", ""),
            source_uri=data.get("source_uri", ""),
            expected_size_bytes=data.get("expected_size_bytes", 0),
            start_byte=data.get("start_byte", 0),
            end_byte=data.get("end_byte", 0),
            catalog_type=data.get("catalog_type", SourceCatalogType.OPENNEURO.value),
            checksum_policy=data.get("checksum_policy", ChecksumPolicy.SHA256_IF_AVAILABLE.value),
            expected_checksum=data.get("expected_checksum"),
            cache_budget_bytes=data.get("cache_budget_bytes", 500 * 1024 * 1024),
            min_headroom_bytes=data.get("min_headroom_bytes", 50 * 1024 * 1024),
            eviction_policy=data.get("eviction_policy", EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value),
            allow_network=data.get("allow_network", False),
            license_state=data.get("license_state", LicenseAccessState.UNKNOWN_BLOCKED.value),
            declared_consumers=data.get("declared_consumers", []),
        )

    cache_budget_bytes = int(args.cache_budget_mb * 1024 * 1024) if hasattr(args, "cache_budget_mb") else 500 * 1024 * 1024
    min_headroom_bytes = int(args.min_headroom_mb * 1024 * 1024) if hasattr(args, "min_headroom_mb") else 50 * 1024 * 1024

    return BoundedAcquisitionRequest(
        dataset_id=args.dataset_id or "",
        object_path=args.object_path or "",
        source_uri=args.source_uri or "",
        expected_size_bytes=args.expected_size or 0,
        start_byte=args.start_byte if args.start_byte is not None else 0,
        end_byte=args.end_byte if args.end_byte is not None else 0,
        catalog_type=args.catalog_type or SourceCatalogType.OPENNEURO.value,
        checksum_policy=args.checksum_policy or ChecksumPolicy.SHA256_IF_AVAILABLE.value,
        expected_checksum=args.expected_checksum,
        cache_budget_bytes=cache_budget_bytes,
        min_headroom_bytes=min_headroom_bytes,
        eviction_policy=args.eviction_policy or EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value,
        allow_network=bool(getattr(args, "allow_network", False)),
        license_state=args.license_state or LicenseAccessState.UNKNOWN_BLOCKED.value,
        declared_consumers=list(getattr(args, "consumer_id", []) or []),
    )


def cmd_plan(args: argparse.Namespace) -> int:
    """Handle `plan` subcommand."""
    request = _build_request_from_args(args)
    adapter = ApprovedAcquisitionAdapter(
        cache_root=args.cache_root,
        max_cache_bytes=request.cache_budget_bytes,
        min_free_headroom_bytes=request.min_headroom_bytes,
    )

    plan = adapter.plan(request)
    plan_dict = plan.to_dict()

    if args.format == "markdown":
        output_str = format_plan_markdown(plan)
    else:
        output_str = json.dumps(plan_dict, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
    else:
        print(output_str)

    return 0 if plan.is_executable else 1


def cmd_acquire(args: argparse.Namespace) -> int:
    """Handle `acquire` subcommand."""
    request = _build_request_from_args(args)
    adapter = ApprovedAcquisitionAdapter(
        cache_root=args.cache_root,
        max_cache_bytes=request.cache_budget_bytes,
        min_free_headroom_bytes=request.min_headroom_bytes,
    )

    result = adapter.acquire(
        request=request,
        chunk_index=args.chunk_index,
        max_retries=args.max_retries,
    )
    result_dict = result.to_dict()

    if args.format == "markdown":
        output_str = format_result_markdown(result)
    else:
        output_str = json.dumps(result_dict, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
    else:
        print(output_str)

    return 0 if result.success else 1


def cmd_consume(args: argparse.Namespace) -> int:
    """Handle `consume` subcommand."""
    adapter = ApprovedAcquisitionAdapter(cache_root=args.cache_root)
    ack = adapter.consume(
        dataset_id=args.dataset_id,
        object_path=args.object_path,
        consumer_id=args.consumer_id,
        chunk_index=args.chunk_index,
    )
    safe_ack = finite_value(ack)

    if args.format == "markdown":
        lines = [
            "# Consumer Acknowledgment",
            "",
            f"- **Consumer**: `{args.consumer_id}`",
            f"- **Remaining Consumers**: `{safe_ack.get('remaining_consumers')}`",
            f"- **Lease Released**: `{safe_ack.get('lease_released')}`",
            f"- **File Evicted (Cleaned Up)**: `{safe_ack.get('evicted')}`",
            f"- **Message**: {safe_ack.get('message')}",
        ]
        output_str = "\n".join(lines)
    else:
        output_str = json.dumps(safe_ack, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
    else:
        print(output_str)

    return 0


def cmd_report_legacy(args: argparse.Namespace) -> int:
    """Handle `report-legacy` subcommand."""
    scanner = LegacyCallerScanner(repo_root=args.repo_root)
    report = scanner.scan()

    if args.format == "markdown":
        output_str = scanner.to_markdown(report)
    else:
        output_str = json.dumps(report, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
    else:
        print(output_str)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        description="Approved Bounded Acquisition Planning and Execution CLI.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_request_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--request-file", help="Path to JSON file with BoundedAcquisitionRequest parameters.")
        p.add_argument("--dataset-id", help="Dataset identifier (e.g., ds004504, dandi:000001).")
        p.add_argument("--object-path", help="Relative path of the target object.")
        p.add_argument("--source-uri", help="Source URI (HTTPS or S3 URL).")
        p.add_argument("--expected-size", type=int, help="Total expected file size in bytes.")
        p.add_argument("--start-byte", type=int, default=0, help="Starting byte index of the range.")
        p.add_argument("--end-byte", type=int, default=0, help="Ending byte index of the range (inclusive).")
        p.add_argument(
            "--catalog-type",
            choices=[c.value for c in SourceCatalogType],
            default=SourceCatalogType.OPENNEURO.value,
            help="Source catalog/archive type.",
        )
        p.add_argument(
            "--license-state",
            choices=[l.value for l in LicenseAccessState],
            default=LicenseAccessState.UNKNOWN_BLOCKED.value,
            help="Explicit license state.",
        )
        p.add_argument(
            "--checksum-policy",
            choices=[cp.value for cp in ChecksumPolicy],
            default=ChecksumPolicy.SHA256_IF_AVAILABLE.value,
            help="Checksum verification policy.",
        )
        p.add_argument("--expected-checksum", help="Expected SHA-256 digest of the chunk or file.")
        p.add_argument(
            "--eviction-policy",
            choices=[ep.value for ep in EvictionPolicy],
            default=EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value,
            help="Chunk lifecycle and eviction policy.",
        )
        p.add_argument("--cache-budget-mb", type=int, default=500, help="Maximum cache capacity in MB.")
        p.add_argument("--min-headroom-mb", type=int, default=50, help="Minimum free disk headroom in MB.")
        p.add_argument("--cache-root", default=".cache/approved_adapter", help="Local directory for chunk cache.")
        p.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format.")
        p.add_argument("--output", help="Optional file destination for output.")

    # 1. plan
    parser_plan = subparsers.add_parser("plan", help="Dry-run planning without downloading data bytes.")
    add_common_request_flags(parser_plan)
    parser_plan.set_defaults(func=cmd_plan)

    # 2. acquire
    parser_acquire = subparsers.add_parser("acquire", help="Acquire chunk with lease and fail-closed network gate.")
    add_common_request_flags(parser_acquire)
    parser_acquire.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicit permission to perform network requests (fail-closed if omitted).",
    )
    parser_acquire.add_argument(
        "--consumer-id",
        action="append",
        help="Declared consumer identifier (can specify multiple times).",
    )
    parser_acquire.add_argument("--chunk-index", type=int, default=0, help="Chunk index (0 for sub-file range).")
    parser_acquire.add_argument("--max-retries", type=int, default=3, help="Max transient retry attempts.")
    parser_acquire.set_defaults(func=cmd_acquire)

    # 3. consume
    parser_consume = subparsers.add_parser("consume", help="Acknowledge consumer and release lease / evict chunk.")
    parser_consume.add_argument("--cache-root", default=".cache/approved_adapter", help="Cache root directory.")
    parser_consume.add_argument("--dataset-id", required=True, help="Dataset ID.")
    parser_consume.add_argument("--object-path", required=True, help="Object relative path.")
    parser_consume.add_argument("--consumer-id", required=True, help="Consumer ID acknowledging completion.")
    parser_consume.add_argument("--chunk-index", type=int, default=0, help="Chunk index.")
    parser_consume.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format.")
    parser_consume.add_argument("--output", help="Optional file destination for output.")
    parser_consume.set_defaults(func=cmd_consume)

    # 4. report-legacy
    parser_legacy = subparsers.add_parser("report-legacy", help="Scan repository for legacy unapproved callers.")
    parser_legacy.add_argument("--repo-root", default=".", help="Repository root path to scan.")
    parser_legacy.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format.")
    parser_legacy.add_argument("--output", help="Optional file destination for output.")
    parser_legacy.set_defaults(func=cmd_report_legacy)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
