#!/usr/bin/env python3
"""Validate local artifacts with the offline evidence promotion gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evidence_promotion_gate.reporting import (  # noqa: E402
    blocking_exit_code,
    evaluate_and_report,
    serialize_json,
    write_report,
)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline fail-closed evidence promotion gate")
    parser.add_argument("--input", required=True, type=Path, help="Fixture file or directory of case directories")
    parser.add_argument("--output", type=Path, help="Write JSON report; stdout when omitted")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        payload = evaluate_and_report(args.input)
    except Exception as exc:  # fail closed
        payload = {
            "schema_version": "EvidencePromotionGate.v1",
            "scientific_pass": False,
            "case_count": 0,
            "error": str(exc),
            "results": [],
        }
        output = serialize_json(payload)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 2
    if args.output:
        write_report(payload, args.output)
    else:
        print(serialize_json(payload), end="")
    return blocking_exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
