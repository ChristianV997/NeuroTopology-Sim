#!/usr/bin/env python3
"""CLI for the Research Runtime Cross-Platform Acceptance Harness.

Validates the research-cycle runtime infrastructure across Windows and POSIX behavior
without modifying production code. On Windows hosts, verifies Windows path normalization,
mandatory file-locking, PowerShell command construction, and process tree termination;
on POSIX hosts, correctly records Windows behaviors as UNSUPPORTED and verifies POSIX
signals.

Usage:
    python scripts/run_research_runtime_acceptance.py
    python scripts/run_research_runtime_acceptance.py --json
    python scripts/run_research_runtime_acceptance.py --output out/report.json --markdown-output out/report.md
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import List, Optional

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.runner_acceptance.research_runtime import (
    dumps_finite_json,
    generate_markdown_report,
    run_acceptance_suite,
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run cross-platform research runtime acceptance tests.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write the finite JSON acceptance report.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Path to write the GitHub-flavored Markdown report.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON report to stdout.",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=10.0,
        help="Timeout in seconds for individual subprocess scenarios.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional custom working directory for scenario execution.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    report = run_acceptance_suite(base_dir=args.work_dir, timeout_s=args.timeout_s)

    json_text = dumps_finite_json(report.to_dict())
    md_text = generate_markdown_report(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_text + "\n", encoding="utf-8")

    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(md_text, encoding="utf-8")

    if args.json:
        print(json_text)
    else:
        print(f"=== Research Runtime Cross-Platform Acceptance ===")
        print(f"Platform: {report.host_platform} ({report.host_os_name}) | Python: {report.python_version} | Commit: {report.repo_commit[:10]}")
        print(f"PowerShell: {report.powershell_available} (ver={report.powershell_version or 'N/A'})")
        print(f"Summary: Total={report.total_cases}, Passed={report.supported_cases}, Unsupported={report.unsupported_cases}, Pending={report.pending_cases}, Failed={report.failed_cases}")
        print("-" * 75)
        for r in report.results:
            outcome_str = f"[{r.status.value:11s}]"
            print(f"  {outcome_str} {r.test_case:34s} ({r.category:18s}) - {r.duration_ms:6.1f}ms")
            if r.unsupported_reason:
                print(f"               Reason: {r.unsupported_reason}")
            if r.error_message:
                print(f"               Error:  {r.error_message}")
        print("=" * 75)

    return 0 if report.failed_cases == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
