#!/usr/bin/env python3
"""Validate empirical-input readiness from a local JSON packet. No downloads."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analysis.empirical_readiness.evaluator import evaluate_readiness, serialize_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    raw = json.loads(args.packet.read_text(encoding="utf-8"))
    report = evaluate_readiness(raw)
    text = serialize_report(report)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(json.dumps(json.loads(text), indent=2, sort_keys=True))
    if report.status.startswith("READY_"):
        return 0
    if report.status == "INVALID_INPUT":
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
