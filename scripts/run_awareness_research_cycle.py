"""CLI for the Awareness Studio research-cycle orchestrator.

Usage
-----
    python -m scripts.run_awareness_research_cycle \\
        --manifest governance/awareness_research_cycle/manifest.json \\
        --output-dir artifacts/awareness_research_cycle \\
        --formats json,markdown,csv

No network access, no discovery of scripts or datasets, no execution of
anything read from the manifest's evidence files: this script only reads
the exact files named in ``--manifest`` and writes report outputs. See
docs/awareness_studio/research_cycle_orchestration.md for the manifest
and output contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.awareness_studio_research_loop.compiler import compile_research_cycle  # noqa: E402
from tools.awareness_studio_research_loop.render_csv import render_csv_tables  # noqa: E402

VALID_FORMATS = {"json", "markdown", "csv"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to the input manifest file (JSON or YAML).")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write report outputs into.")
    parser.add_argument("--formats", default="json,markdown", help="Comma-separated subset of {json,markdown,csv} to emit (default: json,markdown).")
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    parser.add_argument("--repo", default=None, help="Repository identifier to record under repository_identity.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    unknown = formats - VALID_FORMATS
    if unknown:
        print(f"error: unknown format(s) {sorted(unknown)}; valid formats are {sorted(VALID_FORMATS)}", file=sys.stderr)
        return 2

    report = compile_research_cycle(args.manifest, now=args.now, repo=args.repo)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if "json" in formats:
        (args.output_dir / "research_cycle_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )

    if "markdown" in formats:
        (args.output_dir / "paper_draft.md").write_text(report["paper_draft_markdown"], encoding="utf-8")

    if "csv" in formats:
        csv_dir = args.output_dir / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        for name, contents in render_csv_tables(report).items():
            (csv_dir / name).write_text(contents, encoding="utf-8")

    gate_failures = sum(1 for g in report["gate_results"].values() if not g["passed"])
    print(f"status={report['status']} gate_failures={gate_failures} hypotheses={len(report['cycle_states'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
