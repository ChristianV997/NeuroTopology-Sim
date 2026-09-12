#!/usr/bin/env python3
"""CLI runner for evaluating data-access migration gating."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data_access.migration_gate import (  # noqa: E402
    DataAccessMigrationGate,
    MigrationManifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate data-access migration gate against scanner findings."
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root directory")
    parser.add_argument("--scanner-report", type=Path, help="Path to precomputed scanner JSON report")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to migration manifest JSON")
    parser.add_argument(
        "--scan-path",
        action="append",
        dest="scan_paths",
        help="Target paths to scan on the fly if no scanner report is given",
    )
    parser.add_argument("--output-json", type=Path, help="Path to write strict finite JSON report")
    parser.add_argument("--output-markdown", type=Path, help="Path to write Markdown summary report")
    parser.add_argument("--as-of-date", type=str, default=None, help="Evaluation date override (YYYY-MM-DD)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail closed if ANY unmigrated findings remain (zero-tolerance mode)",
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Format for stdout output",
    )

    args = parser.parse_args(argv)

    scanner_input = None
    if args.scanner_report:
        scanner_input = args.scanner_report
    elif args.scan_paths:
        from tools.data_access.policy_enforcement.scanner import scan_paths

        scanner_report_obj = scan_paths(args.scan_paths, repository_root=args.root)
        scanner_input = scanner_report_obj
    else:
        # Default empty scan if neither is provided
        scanner_input = {"repository_root": str(args.root), "findings": []}

    gate = DataAccessMigrationGate(repository_root=args.root)
    report = gate.evaluate(
        scanner_input=scanner_input,
        manifest_input=args.manifest,
        current_date=args.as_of_date,
        strict=args.strict,
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(report.to_json(), encoding="utf-8")

    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(report.to_markdown(), encoding="utf-8")

    if args.format == "json":
        print(report.to_json())
    elif args.format == "markdown":
        print(report.to_markdown())
    else:
        print(report.human_summary())
        print(report.compliance_statement)
        if report.fail_closed_reasons:
            print("\nFail-closed issues:")
            for reason in report.fail_closed_reasons:
                print(f"  - ⛔ {reason}")

    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
