"""Read-only CLI for inspecting Awareness Studio research-cycle state.

Reads exactly the sources named on the command line (a ledger SQLite
database, a claim-gate report, and/or one or more simulation-artifact
reports) -- never discovers files, never executes anything, never
touches the network, never writes anything except when ``export``'s
``--output-dir`` is given explicitly.

Usage
-----
    python -m scripts.inspect_research_cycle <mode> \\
        --ledger-db path/to/ledger.sqlite3 \\
        --claim-gate-report path/to/claims.json \\
        --artifacts-dir path/to/artifact_reports/ \\
        --format json

Modes: summary, cycle, claims, hypotheses, artifacts, graph, blockers,
stale, export, validate. See docs/awareness_studio/research_cycle_cli.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.research_cycle_cli.compiler import compile_inspection  # noqa: E402
from tools.research_cycle_cli.render_markdown import render_markdown  # noqa: E402
from tools.research_cycle_cli.render_text import render_summary_text  # noqa: E402

MODES = ("summary", "cycle", "claims", "hypotheses", "artifacts", "graph", "blockers", "stale", "export", "validate")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger-db", type=Path, default=None, help="Path to the research-cycle ledger SQLite database (opened read-only).")
    parser.add_argument("--claim-gate-report", type=Path, default=None, help="Path to a claim-gate report (JSON array/object, or JSONL).")
    parser.add_argument("--claim-gate-jsonl", action="store_true", help="Treat --claim-gate-report as one JSON object per line.")
    parser.add_argument("--artifact-report", type=Path, action="append", default=None, help="Path to one simulation-artifact report (repeatable).")
    parser.add_argument("--artifacts-dir", type=Path, default=None, help="Directory of *.json simulation-artifact reports (non-recursive).")
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text", help="Output format for modes other than export (default: text).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=MODES)
    _add_common_args(parser)
    parser.add_argument("--cycle-id", default=None, help="cycle mode only: restrict output to one cycle_id.")
    parser.add_argument("--output-dir", type=Path, default=None, help="export mode only: directory to write reports into (required for export).")
    return parser.parse_args(argv)


def _select_mode_payload(mode: str, report: dict[str, Any], *, cycle_id: str | None) -> Any:
    if mode == "summary":
        return report
    if mode == "cycle":
        if cycle_id is None:
            return report["cycles"]
        return {
            "cycle": next((c for c in report["cycles"]["records"] if c["cycle_id"] == cycle_id), None),
            "groups_containing_cycle": {group: (cycle_id in ids) for group, ids in report["cycles"]["groups"].items()},
        }
    if mode == "claims":
        return report["claims"]
    if mode == "hypotheses":
        return report["hypotheses"]
    if mode == "artifacts":
        return report["artifacts"]
    if mode == "graph":
        return report["graph"]
    if mode == "blockers":
        return {"blockers": report["blockers"], "exit_code": report["exit_code"]}
    if mode == "stale":
        return {"stale_outputs": report["stale_outputs"]}
    raise AssertionError(f"unhandled mode: {mode}")


def _render(payload: Any, fmt: str, *, full_report_for_markdown: dict[str, Any] | None) -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if fmt == "markdown":
        return render_markdown(full_report_for_markdown) if full_report_for_markdown is not None else json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.mode == "export" and args.output_dir is None:
        print("error: export mode requires --output-dir", file=sys.stderr)
        return 2

    report = compile_inspection(
        ledger_db=args.ledger_db,
        claim_gate_report=args.claim_gate_report,
        claim_gate_jsonl=args.claim_gate_jsonl,
        artifact_reports=args.artifact_report,
        artifacts_dir=args.artifacts_dir,
        now=args.now,
    )

    if args.mode == "validate":
        payload = {"sources": report["sources"], "diagnostics": report["diagnostics"], "exit_code": report["exit_code"]}
        if args.format == "text":
            print(f"validate: exit={report['exit_code']} diagnostics={len(report['diagnostics'])}")
            for d in report["diagnostics"]:
                print(f"  - [{d['kind']}] {d['source']}: {d['detail']}")
        else:
            print(_render(payload, args.format, full_report_for_markdown=report), end="")
        return report["exit_code"]

    if args.mode == "export":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "inspection_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        (args.output_dir / "inspection_report.md").write_text(render_markdown(report), encoding="utf-8")
        (args.output_dir / "inspection_summary.txt").write_text(render_summary_text(report), encoding="utf-8")
        print(render_summary_text(report), end="")
        return report["exit_code"]

    if args.mode == "summary":
        if args.format == "text":
            print(render_summary_text(report), end="")
        else:
            print(_render(report, args.format, full_report_for_markdown=report), end="")
        return report["exit_code"]

    payload = _select_mode_payload(args.mode, report, cycle_id=args.cycle_id)
    if args.format == "text":
        print(render_summary_text(report), end="")
    else:
        print(_render(payload, args.format, full_report_for_markdown=report), end="")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
