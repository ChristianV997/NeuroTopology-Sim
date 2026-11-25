#!/usr/bin/env python3
"""Audit declared cohort, null-calibration, and preregistration reports.

python scripts/audit_statistical_assumptions.py \\
  --input spec.json \\
  --output assumption_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analysis.statistical_assumptions.audit import load_and_audit
from analysis.statistical_assumptions.json_util import dumps_strict


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only statistical-assumption audit.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(json.dumps({"ok": False, "error": f"input not found: {args.input}"}), file=sys.stderr)
        return 2
    try:
        report = load_and_audit(args.input.read_text(encoding="utf-8"), root=args.input.parent)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dumps_strict(report), encoding="utf-8")
    if not args.quiet:
        print(f"{report['status']} scientific_pass={report['scientific_pass']}")
    return 0 if report["status"] == "AUDIT_CLEAN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
