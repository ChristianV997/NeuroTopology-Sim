"""CLI for the mobile-compatible research-record compiler.

Usage
-----
    python -m scripts.build_research_record \\
        --manifest governance/research_record/manifest.json \\
        --output-dir artifacts/research_record \\
        --formats markdown,json,csv

No network access, no `git`/`gh` calls, no solver imports, no automatic
data loading: this script only reads the exact files named in
``--manifest``. See docs/reporting/research_record_contract.md for the
manifest and output contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.research_record.compiler import compile_record  # noqa: E402
from tools.research_record.render_csv import render_csv_tables  # noqa: E402
from tools.research_record.render_markdown import render_markdown  # noqa: E402

VALID_FORMATS = {"json", "markdown", "csv"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to the input manifest file (JSON or YAML).")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write record outputs into.")
    parser.add_argument(
        "--formats",
        default="markdown,json",
        help="Comma-separated subset of {json,markdown,csv} to emit (default: markdown,json).",
    )
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the record with (default: current UTC time).")
    parser.add_argument("--repo", default=None, help="Repository identifier to record under repository_identity.")
    parser.add_argument("--origin-main-commit", default=None, help="origin/main commit SHA to record.")
    parser.add_argument("--integration-ref", default=None, help="Integration branch/ref to record.")
    parser.add_argument("--integration-commit", default=None, help="Integration commit SHA to record (verified only against corroborating evidence).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    unknown = formats - VALID_FORMATS
    if unknown:
        print(f"error: unknown format(s) {sorted(unknown)}; valid formats are {sorted(VALID_FORMATS)}", file=sys.stderr)
        return 2

    record = compile_record(
        args.manifest,
        now=args.now,
        repo=args.repo,
        origin_main_commit=args.origin_main_commit,
        integration_ref=args.integration_ref,
        integration_commit=args.integration_commit,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if "json" in formats:
        (args.output_dir / "research_record.json").write_text(
            json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )

    if "markdown" in formats:
        (args.output_dir / "research_record.md").write_text(render_markdown(record), encoding="utf-8")

    if "csv" in formats:
        csv_dir = args.output_dir / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        for name, contents in render_csv_tables(record).items():
            (csv_dir / name).write_text(contents, encoding="utf-8")

    print(f"status={record['status']} final_release_recommendation={record['final_release_recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
