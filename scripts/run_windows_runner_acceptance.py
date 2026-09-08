#!/usr/bin/env python
"""CLI for the Windows-focused isolated-runner acceptance harness.

Invokes the existing ``scripts/run_tests_isolated.py`` through safe subprocesses
(no ``shell=True``) and reports platform behavior. On non-Windows hosts it prints
``platform_status=unsupported`` and runs only portable contract tests; it never
claims Windows behavior passed.

Usage:
    python scripts/run_windows_runner_acceptance.py            # human summary
    python scripts/run_windows_runner_acceptance.py --json     # finite JSON
    python scripts/run_windows_runner_acceptance.py --output out/acc.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from tools.runner_acceptance.harness import dumps, run_acceptance


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout-s", type=int, default=5,
                    help="Per-scenario runner timeout used by Windows cases (seconds)")
    ap.add_argument("--output", type=str, default=None, help="Write the JSON report to this path")
    ap.add_argument("--json", action="store_true", help="Print the full JSON report")
    ap.add_argument("--no-portable-runner", action="store_true",
                    help="Skip the portable case that invokes the runner in a Unicode/space path")
    args = ap.parse_args(argv)

    report = run_acceptance(timeout_s=args.timeout_s,
                            include_portable_runner=not args.no_portable_runner)

    text = dumps(report)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    if args.json:
        print(text)
    else:
        print(f"platform={report['platform']} platform_status={report['platform_status']} "
              f"python={report['python_version']} runner={report['runner_version'][:12]}")
        print(f"summary={report['summary']} ran_ok={report['ran_ok']} "
              f"windows_behavior_validated={report['windows_behavior_validated']}")
        for r in report["results"]:
            print(f"  {r['test_case']:34s} [{r['category']:14s}] {r['outcome']:11s} "
                  f"obs={r['observed_outcome']}")
        if report["platform_status"] == "unsupported":
            print("NOTE: non-Windows host -> Windows-specific behavior is UNSUPPORTED here "
                  "and was not claimed to pass.")

    # Neutral 'unsupported' cases do not fail the run; only real FAIL/ERROR do.
    return 0 if report["ran_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
