"""Run read-only local CI resource diagnostics or classify a captured log.

Examples:
  python scripts/audit_ci_environment.py --format summary
  python scripts/audit_ci_environment.py --log ci.log --format json
  cat ci.log | python scripts/audit_ci_environment.py --log - --format summary

The log mode is pure local parsing. It does not contact GitHub, inspect remote
job state, install packages, launch Docker builds, or mutate caches.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.ci_resource_audit import (  # noqa: E402
    AUDIT_SCHEMA,
    FAILURE_CLASSES,
    build_environment_report,
    parse_ci_log,
    render_human_summary,
    serialize_report,
)


def _read_log(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", help="captured CI log path, or '-' for stdin; no network is used")
    parser.add_argument("--repo-path", type=Path, default=Path.cwd())
    parser.add_argument("--temp-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, help="write JSON output to this file instead of stdout")
    parser.add_argument("--summary-out", type=Path, help="write the human-readable summary to this file")
    parser.add_argument("--format", choices=("json", "summary"), default="json")
    parser.add_argument("--timestamp", action="store_true", help="include an explicitly non-deterministic UTC timestamp")
    parser.add_argument("--no-packages", action="store_true", help="skip installed-package enumeration")
    args = parser.parse_args(argv)

    if args.log:
        try:
            log = parse_ci_log(_read_log(args.log))
        except OSError as exc:
            report = {"schema": AUDIT_SCHEMA, "mode": "log", "failure_classes": list(FAILURE_CLASSES), "log": {"input_valid": False, "classification": "unknown_infrastructure_failure", "errors": [str(exc)]}}
            if args.out:
                args.out.write_text(serialize_report(report), encoding="utf-8")
            else:
                print(serialize_report(report), end="")
            return 1
        report = {"schema": AUDIT_SCHEMA, "mode": "log", "generated_at_utc": None, "failure_classes": list(FAILURE_CLASSES), "log": log}
    else:
        report = build_environment_report(repo_path=args.repo_path, temp_dir=args.temp_dir, include_packages=not args.no_packages, include_timestamp=args.timestamp)

    summary = render_human_summary(report)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(summary, encoding="utf-8")
    rendered = summary if args.format == "summary" else serialize_report(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
