"""CLI for the mobile-compatible research report compiler.

Usage
-----
    python -m scripts.compile_mobile_research_report \\
        --manifest governance/mobile_report/manifest.json \\
        --output-dir artifacts/mobile_research_report \\
        --formats markdown,json,csv

No network access, no solver imports, no automatic data loading: this
script only reads the exact files named in ``--manifest``. See
docs/reporting/mobile_report_contract.md for the manifest and output
contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.mobile_report.compiler import compile_report  # noqa: E402
from tools.mobile_report.render_csv import render_csv_tables  # noqa: E402
from tools.mobile_report.render_markdown import render_markdown  # noqa: E402

VALID_FORMATS = {"json", "markdown", "csv"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to the input manifest file (JSON or YAML).")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write report outputs into.")
    parser.add_argument(
        "--formats",
        default="markdown,json",
        help="Comma-separated subset of {json,markdown,csv} to emit (default: markdown,json).",
    )
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    parser.add_argument("--repo", default=None, help="Repository identifier to record under repository_and_integration_commit.")
    parser.add_argument("--integration-ref", default=None, help="Integration branch/ref to record.")
    parser.add_argument("--integration-commit", default=None, help="Integration commit SHA to record.")
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
        integration_ref=args.integration_ref,
        integration_commit=args.integration_commit,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if "json" in formats:
        (args.output_dir / "mobile_research_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )

    if "markdown" in formats:
        (args.output_dir / "mobile_research_report.md").write_text(render_markdown(report), encoding="utf-8")

    if "csv" in formats:
        csv_dir = args.output_dir / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        for name, contents in render_csv_tables(report).items():
            (csv_dir / name).write_text(contents, encoding="utf-8")

    print(f"status={report['status']} final_release_recommendation={report['final_release_recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
