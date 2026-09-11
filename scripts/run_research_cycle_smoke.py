#!/usr/bin/env python
"""Run the research-cycle end-to-end smoke harness (local-only).

Consumes canonical release-evidence interfaces. Never emits scientific PASS
or a Bayes factor.

Example::

    PYTHONPATH=. python scripts/run_research_cycle_smoke.py \\
      --output artifacts/research_cycle_smoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.release_readiness.research_cycle_smoke.report import dumps, write_reports
from tools.release_readiness.research_cycle_smoke.runner import run_smoke_suite
from tools.release_readiness.research_cycle_smoke.schema import ScenarioId


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="artifacts/research_cycle_smoke")
    p.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Optional scenario id (repeatable). Default: all.",
    )
    p.add_argument("--json-stdout", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    scenarios = None
    if args.scenario:
        try:
            scenarios = [ScenarioId(s) for s in args.scenario]
        except ValueError as exc:
            print(f"invalid scenario: {exc}", file=sys.stderr)
            return 2

    payload = run_smoke_suite(scenarios)
    paths = write_reports(payload, args.output)
    if args.json_stdout:
        print(dumps(payload))
    else:
        print(f"n_scenarios={payload.get('n_scenarios')}")
        print(f"all_decisions_match={payload.get('all_decisions_match')}")
        print(f"all_guards_pass={payload.get('all_guards_pass')}")
        print(f"deterministic={payload.get('deterministic')}")
        print("scientific_pass_emitted=False")
        print("bayes_factor_emitted=False")
        print("network_accessed=False")
        for row in payload.get("decision_matrix") or []:
            print(
                f"  {row['scenario_id']}: expected={row['expected']} "
                f"observed={row['observed']} match={row['match']}"
            )
        for label, pth in paths.items():
            print(f"wrote {label}={pth}")

    if payload.get("all_decisions_match") and payload.get("all_guards_pass") and payload.get("deterministic"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
