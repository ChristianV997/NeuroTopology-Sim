"""CLI: python -m tools.experimental_audits.winding_charge_round6 [--json PATH]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.experimental_audits.winding_charge_round6.audit import (
    CHECK_FAIL,
    run_conformance_audit,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Independent Round 6 winding/charge discrete-identity audit "
            "(HOLD / SYNTHETIC_ONLY; not a scientific VALIDATED claim)."
        )
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional path to write the JSON audit report.",
    )
    args = parser.parse_args(argv)

    report = run_conformance_audit()
    payload = report.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.json is not None:
        report.write_json(args.json)
        print(f"wrote {args.json}", file=sys.stderr)

    if report.summary.get(CHECK_FAIL, 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
