#!/usr/bin/env python3
"""CLI validator for reviewed data-access exception records.

Validates:
- Exact file paths without wildcards or broad repository-wide scopes.
- Exact line numbers or symbol names.
- Mandatory named owner and independent reviewer (no self-review).
- Mandatory migration issue reference.
- Expiration date and fail-closed behavior for expired records.
- Rejection of forbidden unsafe behaviors (full-dataset downloads, unbounded
  remote reads, missing checksums, output-root escapes, network-enabled defaults,
  and fabricated provenance).
- Strict finite JSON serialization (RFC 8259) and SHA-256 integrity verification.

INVARIANT:
Repository compliance is NEVER declared merely because an exception exists.
Exceptions are tracked migration debt, not compliance.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.data_access.exception_registry import (
    EXCEPTION_REGISTRY_SCHEMA,
    ExceptionRecordStatus,
    ExceptionRegistry,
    RegistryAuditReport,
    canonical_hash,
    finite_value,
)


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate reviewed data-access exceptions for compliance, expiry, and safety.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--exceptions-dir",
        default="configs/data_access/reviewed_exceptions",
        help="Directory containing reviewed exception files (.json, .yaml, .yml).",
    )
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Evaluation date for checking expiration (YYYY-MM-DD). Defaults to UTC today.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output report format.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional file path to write report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Fail closed (exit code 1) if any exception is expired, malformed, or unsafe.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    exceptions_dir = Path(args.exceptions_dir)
    if not exceptions_dir.is_absolute():
        exceptions_dir = REPO_ROOT / exceptions_dir

    registry = ExceptionRegistry(exceptions_dir=exceptions_dir)
    report = registry.load_from_directory(
        directory=exceptions_dir,
        as_of_date=args.as_of_date,
    )

    if args.format == "json":
        report_dict = report.to_dict()
        output_str = json.dumps(report_dict, indent=2, sort_keys=True) + "\n"
    else:
        output_str = registry.to_markdown(report) + "\n"

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_str, encoding="utf-8")
    else:
        sys.stdout.write(output_str)

    # Fail closed conditions
    has_expired = report.expired_count > 0
    has_rejected = report.rejected_count > 0

    if args.strict and (has_expired or has_rejected):
        sys.stderr.write(
            f"\n[FAIL-CLOSED] Exception validation failed: {report.expired_count} expired, "
            f"{report.rejected_count} rejected/malformed/unsafe exceptions found.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
