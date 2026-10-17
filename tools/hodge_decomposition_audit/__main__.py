"""CLI: run Hodge decomposition numerical audit and optionally write reports."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.hodge_decomposition_audit.audit import run_audit
from tools.hodge_decomposition_audit.report import dumps, write_json, write_markdown


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-json", default=None)
    p.add_argument("--output-md", default=None)
    p.add_argument("--json-stdout", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = run_audit()
    if args.output_json:
        write_json(args.output_json, report)
    if args.output_md:
        write_markdown(args.output_md, report)
    if args.json_stdout or not (args.output_json or args.output_md):
        print(dumps(report))
    else:
        print(f"audit_status={report['audit_status']}")
        print(f"evidence_class={report['evidence_class']}")
        print(f"engineering_checks_ok={report['summary']['engineering_checks_ok']}")
        print(f"proposal_claimed_passed={report['proposal_claimed_passed']}")
    return 0 if report["summary"]["engineering_checks_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
