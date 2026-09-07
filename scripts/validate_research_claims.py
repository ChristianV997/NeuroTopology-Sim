#!/usr/bin/env python3
"""Validate research-claim records without rewriting scientific results.

Example
-------
python scripts/validate_research_claims.py \\
  --input claims.json \\
  --output claim_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.research_claims.audit import load_and_audit  # noqa: E402
from shared.research_claims.json_util import dumps_strict  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic local audit of research-claim language and metadata."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to claims JSON")
    parser.add_argument("--output", required=True, type=Path, help="Path to write claim_audit.json")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the human-readable summary line",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_file():
        print(json.dumps({"ok": False, "error": f"input not found: {args.input}"}), file=sys.stderr)
        return 2
    try:
        report = load_and_audit(args.input.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_all=True) if False else args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dumps_strict(report), encoding="utf-8")

    if not args.quiet:
        counts = report["counts"]
        status = "PASS" if report["ok"] else "FAIL"
        print(
            f"{status} research-claim audit "
            f"pass={counts['pass']} fail={counts['fail']} "
            f"downgraded={counts['downgraded']} total={counts['total']}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
