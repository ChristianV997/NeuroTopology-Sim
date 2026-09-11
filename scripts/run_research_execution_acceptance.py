#!/usr/bin/env python3
"""CLI runner for cross-platform research execution acceptance harness.

Executes platform capability probes, bounded data access tests, cache eviction,
process isolation, output containment, PowerShell syntax/execution, and Windows-specific
tests. Emits tamper-evident finite JSON and human-readable summaries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.platform_acceptance.research_execution.harness import (
    ResearchExecutionAcceptanceHarness,
)
from tools.platform_acceptance.research_execution.types import (
    AcceptanceReport,
    TestStatus,
    write_atomic_json,
)


def render_markdown_summary(report: AcceptanceReport) -> str:
    """Format report into human-readable Markdown summary."""
    matrix = report.platform_matrix
    lines = [
        "# Research Execution Platform Acceptance Report",
        "",
        f"- **Schema Version**: `{report.schema_version}`",
        f"- **Generated At**: `{report.generated_at}`",
        f"- **Report SHA-256 Checksum**: `{report.checksum}`",
        f"- **Overall Status**: **{'ALL PASSED' if report.all_passed else 'FAILURES DETECTED'}**",
        "",
        "## Platform Matrix",
        "",
        f"- **OS**: `{matrix.os_name}` ({'Windows' if matrix.is_windows else 'Non-Windows / POSIX'})",
        f"- **Release**: `{matrix.platform_release}`",
        f"- **Python**: `{matrix.python_version.split()[0]}`",
        f"- **PowerShell Available**: `{matrix.powershell_available}`",
        f"- **PowerShell Version**: `{matrix.powershell_version or 'N/A'}`",
        f"- **Supported Categories**: {', '.join(f'`{c}`' for c in matrix.supported_categories)}",
        f"- **Unsupported Categories**: {', '.join(f'`{c}`' for c in matrix.unsupported_categories) or 'None'}",
        "",
        "## Test Case Summary",
        "",
        f"- **Total Tests**: {report.total_tests}",
        f"- **Passed**: {report.passed}",
        f"- **Failed**: {report.failed}",
        f"- **Unsupported**: {report.unsupported}",
        f"- **Skipped**: {report.skipped}",
        "",
        "| Test Case | Category | Status | Elapsed (s) | Details |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in report.results:
        status_badge = f"**`{r.status.value}`**"
        details_clean = r.details.replace("|", "\\|")
        lines.append(
            f"| `{r.name}` | `{r.category.value}` | {status_badge} | {r.elapsed_s:.2f} | {details_clean} |"
        )

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run research execution cross-platform acceptance harness."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional destination path for the acceptance JSON report.",
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown"],
        default="summary",
        help="Format of the output report to stdout.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-case execution timeout budget in seconds (default: 10.0s).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict mode: exit non-zero if any test fails or is unsupported.",
    )

    args = parser.parse_args(argv)

    harness = ResearchExecutionAcceptanceHarness(timeout_s=args.timeout)
    report = harness.run_all()

    if args.output:
        out_path = args.output.resolve()
        write_atomic_json(out_path, report.to_dict())
        print(f"Report saved to: {out_path}", file=sys.stderr)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, allow_nan=False))
    else:
        print(render_markdown_summary(report))

    if report.failed > 0:
        return 1

    if args.strict and report.unsupported > 0:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
