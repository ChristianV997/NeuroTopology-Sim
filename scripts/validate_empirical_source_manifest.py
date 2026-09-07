#!/usr/bin/env python3
"""Validate a preregistered empirical-source manifest. No downloads. No stats."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from configs.empirical_sources.manifest import serialize_report, validate_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    report = validate_manifest(args.manifest)
    text = serialize_report(report)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(json.dumps(json.loads(text), indent=2, sort_keys=True))
    if report.status == "VALID_PREREGISTRATION":
        return 0
    if report.status == "UNAVAILABLE_SOURCE":
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
