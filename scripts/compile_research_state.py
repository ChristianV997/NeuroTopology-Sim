"""CLI for the unified research-state and evidence-report compiler.

Usage
-----
    python -m scripts.compile_research_state \\
        --manifest governance/research_report/manifest.json \\
        --output-dir artifacts/research_state_report \\
        --formats json,markdown,csv

See docs/research/report_contract.md for the manifest and output contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.research_report.compiler import compile_report  # noqa: E402
from tools.research_report.render_csv import render_csv_tables  # noqa: E402
from tools.research_report.render_markdown import render_markdown  # noqa: E402

VALID_FORMATS = {"json", "markdown", "csv"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to the input manifest JSON file.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write report outputs into.")
    parser.add_argument(
        "--formats",
        default="json,markdown",
        help="Comma-separated subset of {json,markdown,csv} to emit (default: json,markdown).",
    )
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    parser.add_argument("--repo", default=None, help="Repository identifier to record under repository_and_baseline.")
    parser.add_argument("--base-ref", default=None, help="Base branch/ref to record under repository_and_baseline.")
    parser.add_argument("--base-commit", default=None, help="Base commit SHA to record under repository_and_baseline.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    unknown = formats - VALID_FORMATS
    if unknown:
        print(f"error: unknown format(s) {sorted(unknown)}; valid formats are {sorted(VALID_FORMATS)}", file=sys.stderr)
        return 2

    report = compile_report(
        args.manifest,
        now=args.now,
        repo=args.repo,
        base_ref=args.base_ref,
        base_commit=args.base_commit,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if "json" in formats:
        (args.output_dir / "research_state_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )

    if "markdown" in formats:
        (args.output_dir / "research_state_report.md").write_text(render_markdown(report), encoding="utf-8")

    if "csv" in formats:
        csv_dir = args.output_dir / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        for name, contents in render_csv_tables(report).items():
            (csv_dir / name).write_text(contents, encoding="utf-8")

    print(f"status={report['status']} final_release_recommendation={report['final_release_recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
