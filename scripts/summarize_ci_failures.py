"""Summarize a pytest / `scripts/run_tests_isolated.py` log into a small,
deterministic JSON or Markdown report -- failed/errored test node IDs and
the failed isolated-batch number, if any.

Stdlib-only. No network. No GitHub API call. Reads a local log file (or
stdin) and does string parsing only -- it does not run any test itself and
does not classify *why* a test failed (see docs/ci_failure_audit.md's
failure-classification table for that, which is a human/agent judgment
call, not something this script can infer from log text alone).

    python scripts/summarize_ci_failures.py --log path/to/ci_output.txt
    python scripts/summarize_ci_failures.py --log path/to/ci_output.txt --format markdown
    cat ci_output.txt | python scripts/summarize_ci_failures.py --log -
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# pytest's short summary lines: "FAILED tests/foo.py::test_bar - AssertionError: ..."
# and "ERROR tests/foo.py::test_bar - Exception: ..." (collection/fixture-setup
# failures use ERROR rather than FAILED and may omit the "::test_id" part
# entirely for a whole-file collection error). Both represent a failed run
# for CI-triage purposes, so both are captured with a `status` field so a
# caller can still distinguish them if needed. The " - <reason>" suffix is
# optional in either case (pytest omits it for some failure kinds).
_FAILED_TEST_RE = re.compile(r"^(?P<status>FAILED|ERROR)\s+(?P<node_id>\S+?)(?:\s+-\s+(?P<reason>.*))?$")

# scripts/run_tests_isolated.py's own failure line:
# "[isolated] batch 31 failed with exit code 1"
_FAILED_BATCH_RE = re.compile(r"^\[isolated\]\s+batch\s+(?P<batch>\d+)\s+failed with exit code\s+(?P<exit_code>-?\d+)")

# The batch-start line immediately preceding a batch's own output:
# "[isolated 31/44] 8 files"
_BATCH_HEADER_RE = re.compile(r"^\[isolated\s+(?P<batch>\d+)/(?P<total>\d+)\]\s+(?P<file_count>\d+)\s+files")


def parse_log(text: str) -> dict[str, Any]:
    """Pure function over log text -- never touches the filesystem or
    network. Returns a dict, never raises on malformed/empty input."""
    failed_tests: list[dict[str, str]] = []
    failed_batch: int | None = None
    failed_batch_exit_code: int | None = None
    last_batch_seen: int | None = None
    total_batches: int | None = None

    for line in text.splitlines():
        line = line.rstrip("\n")

        header_match = _BATCH_HEADER_RE.match(line)
        if header_match:
            last_batch_seen = int(header_match.group("batch"))
            total_batches = int(header_match.group("total"))
            continue

        batch_match = _FAILED_BATCH_RE.match(line)
        if batch_match:
            failed_batch = int(batch_match.group("batch"))
            failed_batch_exit_code = int(batch_match.group("exit_code"))
            continue

        test_match = _FAILED_TEST_RE.match(line)
        if test_match:
            failed_tests.append(
                {
                    "status": test_match.group("status"),
                    "node_id": test_match.group("node_id"),
                    "reason": (test_match.group("reason") or "").strip(),
                }
            )

    return {
        "failed_tests": failed_tests,
        "total_failed_tests": len(failed_tests),
        "failed_batch": failed_batch,
        "failed_batch_exit_code": failed_batch_exit_code,
        "last_batch_seen": last_batch_seen,
        "total_batches": total_batches,
        "has_failures": bool(failed_tests) or failed_batch is not None,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["# CI failure summary", ""]
    if not summary["has_failures"]:
        lines.append("No failures detected in this log.")
        return "\n".join(lines) + "\n"

    if summary["failed_batch"] is not None:
        batch_line = f"- failed_batch: {summary['failed_batch']}"
        if summary["total_batches"] is not None:
            batch_line += f" / {summary['total_batches']}"
        batch_line += f" (exit code {summary['failed_batch_exit_code']})"
        lines.append(batch_line)

    lines.append(f"- total_failed_tests: {summary['total_failed_tests']}")
    lines.append("")

    if summary["failed_tests"]:
        lines.append("## Failed tests")
        lines.append("")
        for entry in summary["failed_tests"]:
            reason = f" -- {entry['reason']}" if entry["reason"] else ""
            lines.append(f"- [{entry['status']}] `{entry['node_id']}`{reason}")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", required=True, help="path to a log file, or '-' for stdin")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    if args.log == "-":
        text = sys.stdin.read()
    else:
        log_path = Path(args.log)
        if not log_path.exists():
            print(f"FAILED: log file not found: {args.log}", file=sys.stderr)
            return 1
        text = log_path.read_text(encoding="utf-8", errors="replace")

    summary = parse_log(text)

    if args.format == "markdown":
        print(render_markdown(summary), end="")
    else:
        print(json.dumps(summary, indent=2, sort_keys=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
