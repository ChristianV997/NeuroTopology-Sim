#!/usr/bin/env python
"""CLI: run a declarative benchmark matrix under bounded orchestration.

Examples
--------
Dry-run (validate + plan, no execution)::

    PYTHONPATH=. python scripts/run_benchmark_matrix.py \\
        --matrix tools/benchmark_orchestration/examples/local_smoke_matrix.json \\
        --output artifacts/benchmark_orchestration --dry-run

Execute with caps::

    PYTHONPATH=. python scripts/run_benchmark_matrix.py \\
        --matrix tools/benchmark_orchestration/examples/local_smoke_matrix.json \\
        --output artifacts/benchmark_orchestration \\
        --max-workers 1 --total-timeout-s 600 --max-retries 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.benchmark_orchestration.matrix import MatrixValidationError, load_matrix
from tools.benchmark_orchestration.orchestrator import run_campaign
from tools.benchmark_orchestration.report import write_reports
from tools.benchmark_orchestration.schema import CampaignConfig, CaseStatus


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--matrix", required=True, help="Path to JSON or YAML matrix")
    p.add_argument("--output", required=True, help="Output directory for reports/logs")
    p.add_argument("--dry-run", action="store_true", help="Validate and plan only")
    p.add_argument("--resume", action="store_true", help="Resume from output/manifest.json")
    p.add_argument("--max-workers", type=int, default=1)
    p.add_argument("--per-case-timeout-s", type=int, default=None)
    p.add_argument("--total-timeout-s", type=int, default=None)
    p.add_argument("--max-retries", type=int, default=None)
    p.add_argument(
        "--allow-network",
        action="store_true",
        help="Disable local-only matrix validation (default: local-only)",
    )
    p.add_argument("--json-stdout", action="store_true", help="Print report JSON to stdout")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.max_workers < 1:
        print("max-workers must be >= 1", file=sys.stderr)
        return 2
    try:
        matrix = load_matrix(args.matrix, local_only=not args.allow_network)
    except MatrixValidationError as exc:
        print(f"matrix validation failed: {exc}", file=sys.stderr)
        return 2

    config = CampaignConfig(
        per_case_timeout_s=args.per_case_timeout_s,
        total_timeout_s=args.total_timeout_s,
        max_workers=args.max_workers,
        max_retries=args.max_retries,
        dry_run=bool(args.dry_run),
        resume=bool(args.resume),
        local_only=not args.allow_network,
    )
    report = run_campaign(matrix, config, output_dir=args.output)
    paths = write_reports(report, args.output)

    if args.json_stdout:
        from tools.benchmark_orchestration.report import dumps_json

        print(dumps_json(report))
    else:
        s = report.summary
        print("benchmark orchestration")
        print(f"  cases={s['total_cases']} duration_s={s['duration_s']}")
        print(f"  counts={s['counts']}")
        print(f"  any_timeout={s['any_timeout']} any_failure={s['any_failure']}")
        print(f"  wrote {paths['json']}")
        print(f"  wrote {paths['markdown']}")

    # Exit codes: 0 all PASS (or dry-run NOT_RUN only); 124 any timeout;
    # 1 correctness/crash/infra failure; 3 only optional-dep misses.
    statuses = {r.status for r in report.results}
    if CaseStatus.TIMEOUT in statuses:
        return 124
    hard = {
        CaseStatus.CORRECTNESS_FAILURE,
        CaseStatus.CHILD_CRASH,
        CaseStatus.INFRASTRUCTURE_BLOCKED,
    }
    if statuses & hard:
        return 1
    if statuses == {CaseStatus.OPTIONAL_DEPENDENCY_MISSING} or (
        statuses <= {CaseStatus.PASS, CaseStatus.OPTIONAL_DEPENDENCY_MISSING, CaseStatus.NOT_RUN}
        and CaseStatus.OPTIONAL_DEPENDENCY_MISSING in statuses
        and CaseStatus.PASS not in statuses
        and not report.dry_run
    ):
        # Pure optional-dep campaign → distinct non-zero.
        if CaseStatus.OPTIONAL_DEPENDENCY_MISSING in statuses and not (
            statuses & {CaseStatus.PASS}
        ):
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
