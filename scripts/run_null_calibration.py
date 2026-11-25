#!/usr/bin/env python3
"""Run a deterministic null-calibration spec.

python scripts/run_null_calibration.py \\
  --input spec.json \\
  --output calibration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analysis.null_calibration.calibrate import load_and_calibrate
from analysis.null_calibration.json_util import dumps_strict


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic null-calibration runner.")
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
        report = load_and_calibrate(args.input.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dumps_strict(report), encoding="utf-8")
    if not args.quiet:
        status = report.get("status") or ("BUNDLE" if "runs" in report else "UNKNOWN")
        print(f"{status} null-calibration scientific_pass={report.get('scientific_pass')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
