"""CLI: ``python -m tools.research_plan_quality_eval [--manifest PATH] [--json-out PATH]``.

Exit codes: 0 on success, 2 on any harness error (manifest, record, or
evaluation-set failure). A BLOCKED rubric outcome is data, not an error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import HarnessError
from .harness import DEFAULT_MANIFEST, build_report, to_report_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--no-label-consistency", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.manifest, include_label_consistency=not args.no_label_consistency)
    except (HarnessError, OSError) as exc:
        print(f"harness error: {exc}", file=sys.stderr)
        return 2
    text = to_report_json(report)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(
        f"plans={report['fixture_set']['plan_count']} "
        f"cross_split_findings={report['leakage']['cross_split_finding_count']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
