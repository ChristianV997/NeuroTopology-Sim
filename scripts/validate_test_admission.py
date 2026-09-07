#!/usr/bin/env python3
"""CLI validator and runner for the NeuroTopology-Sim Test Admission Matrix.

Evaluates test groups against current host capabilities or configured profiles,
surfacing missing optional dependencies as graceful skips and missing required
prerequisites as structured blockers without hiding failures.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.test_admission.matrix import (
    AdmissionMatrixEvaluator,
    load_admission_matrix_file,
)
from tools.test_admission.models import (
    AdmissionDecision,
    safe_finite_value,
)
from tools.test_admission.probe import probe_platform_capabilities

DEFAULT_CONFIG_PATH = ROOT / "configs" / "test_admission" / "admission_matrix.yaml"


def format_markdown_report(report_dict: dict[str, Any]) -> str:
    """Renders a readable markdown summary of the admission evaluation."""
    lines = [
        "# Test Admission Matrix Evaluation Report",
        "",
        f"**Host OS:** {report_dict['platform']['os_name']} | **Symlinks:** {report_dict['platform']['has_symlinks']} | **Docker:** {report_dict['platform']['has_docker']}",
        "",
        "## Summary by Decision",
        "| Decision | Count |",
        "| :--- | :--- |",
    ]
    for dec, count in sorted(report_dict.get("summary_by_decision", {}).items()):
        lines.append(f"| `{dec}` | {count} |")

    lines.extend([
        "",
        "## Evaluated Test Groups",
        "| Test Group | Category | Decision | Reason |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for ev in report_dict.get("evaluations", []):
        dec = ev["decision"]
        lines.append(f"| `{ev['test_group']}` | {ev['category']} | `{dec}` | {ev['reason']} |")

    lines.append("")
    return "\n".join(lines)


def run_admission_validation(
    config_path: Path,
    output_path: Path | None = None,
    format_type: str = "json",
    target_group: str | None = None,
    strict: bool = False,
) -> tuple[dict[str, Any], int]:
    """Runs test admission matrix evaluation and writes structured output."""
    records = load_admission_matrix_file(config_path)
    if target_group:
        records = [r for r in records if r.test_group == target_group]
        if not records:
            print(f"Error: target group '{target_group}' not found in {config_path}", file=sys.stderr)
            return {}, 2

    # Probe current platform capabilities
    all_packages = set()
    for r in records:
        all_packages.update(r.required_packages)
        all_packages.update(r.optional_packages)

    capabilities = probe_platform_capabilities(sorted(all_packages))
    evaluator = AdmissionMatrixEvaluator(capabilities)
    report = evaluator.evaluate_matrix(records)
    report_dict = report.to_dict()

    # Null-safe finite JSON string
    json_text = json.dumps(report_dict, indent=2, sort_keys=True, allow_nan=False) + "\n"

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_text, encoding="utf-8")

    if format_type == "json":
        print(json_text)
    elif format_type == "markdown":
        print(format_markdown_report(report_dict))
    else:
        print("=" * 70)
        print("TEST ADMISSION MATRIX EVALUATION SUMMARY")
        print("=" * 70)
        print(f"Platform: {capabilities.os_name} (Windows={capabilities.is_windows}, POSIX={capabilities.is_posix})")
        print(f"Runnable: {len(report.runnable_groups)} | Skipped: {len(report.skipped_groups)} | Blocked: {len(report.blocked_groups)} | Invalid: {len(report.invalid_groups)}")
        print("-" * 70)
        for ev in report.evaluations:
            print(f"[{ev.decision.value:32s}] {ev.test_group} ({ev.category})")
            if ev.decision != AdmissionDecision.RUN:
                print(f"    Reason: {ev.reason}")
        print("=" * 70)

    # Determine exit code
    # If strict, any BLOCKED or INVALID decisions result in exit code 1
    has_blockers = len(report.blocked_groups) > 0 or len(report.invalid_groups) > 0
    exit_code = 1 if (strict and has_blockers) else 0
    return report_dict, exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluates test admission matrix against host platform capabilities."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to admission matrix YAML or JSON configuration.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON evaluation report.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "summary", "markdown"],
        default="summary",
        help="Output display format.",
    )
    parser.add_argument(
        "--target-group",
        type=str,
        default=None,
        help="Filter evaluation to a single test group.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status if any required dependency or policy blocker is found.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _, exit_code = run_admission_validation(
        config_path=args.config,
        output_path=args.output,
        format_type=args.format,
        target_group=args.target_group,
        strict=args.strict,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
