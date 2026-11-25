#!/usr/bin/env python3
"""Run the read-only data-access policy scanner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.data_access.policy_enforcement.scanner import scan_repository  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only manifest-first data-access policy audit")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--output", type=Path, help="Write strict JSON report")
    parser.add_argument("--path", action="append", dest="paths", help="Production-relative path to scan; repeatable")
    args = parser.parse_args(argv)
    report = scan_repository(args.root, paths=args.paths)
    payload = report.to_json()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(report.human_summary())
    if report.findings:
        for finding in report.findings:
            print(f"{finding.file}:{finding.line}: {finding.severity} {finding.rule} — {finding.remediation}")
    return 0 if report.compliant else 1


if __name__ == "__main__":
    raise SystemExit(main())
