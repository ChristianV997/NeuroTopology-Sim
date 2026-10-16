"""CLI entry for Batch 3 offline integration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.batch3_offline_integration.runner import run_offline_integration, write_report
from tools.batch3_offline_integration.serialization import dumps


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture-name", default="workflow_request.json")
    p.add_argument("--prior-run-dir", default=None)
    p.add_argument("--force-fail-stage", default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--json-stdout", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = run_offline_integration(
        fixture_name=args.fixture_name,
        prior_run_dir=args.prior_run_dir,
        force_fail_stage=args.force_fail_stage,
    )
    if args.output:
        write_report(report, args.output)
    if args.json_stdout or not args.output:
        print(dumps(report))
    else:
        print(f"workflow_executed_successfully={report['workflow_executed_successfully']}")
        print(f"scientific_validity_claimed={report['scientific_validity_claimed']}")
        print(f"report_sha256={report['report_sha256']}")
        print(f"wrote={args.output}")
    return 0 if report.get("workflow_executed_successfully") else 1


if __name__ == "__main__":
    raise SystemExit(main())
