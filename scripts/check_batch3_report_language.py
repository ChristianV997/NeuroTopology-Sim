#!/usr/bin/env python3
"""Advisory scan of explicitly selected Markdown/JSON reports (offline only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.batch3_report_firewall.checker import InputSelectionError, inspect_reports


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Existing bounded directory containing the selected reports.")
    parser.add_argument("paths", nargs="+", help="Explicit report paths relative to --root; no recursive scan is performed.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        result = inspect_reports(args.root, args.paths)
        code = 0
    except InputSelectionError as exc:
        result = {
            "schema_version": "Batch3ReportLanguageFindings.v1",
            "advisory_only": True,
            "review_recommended": True,
            "input_errors": [str(exc)],
            "findings": [],
        }
        code = 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
