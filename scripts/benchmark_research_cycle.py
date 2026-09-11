#!/usr/bin/env python
"""CLI for the research-cycle resource benchmark harness (local-only, synthetic).

Two modes:

* default -- run all (or selected) targets in-process, print a human summary or
  finite JSON, optionally write an atomic report.
* ``child`` -- run a SINGLE target and print its record as JSON (used by
  ``--isolated`` to run each target in its own bounded, timed subprocess).

No datasets are downloaded, no simulations run, and no external APIs are called.
Output is synthetic performance evidence only and makes no scientific claims.

Usage:
    python scripts/benchmark_research_cycle.py --size 256 --repetitions 3 --json
    python scripts/benchmark_research_cycle.py --isolated --per-target-timeout-s 30
    python scripts/benchmark_research_cycle.py --memory-budget-mb 8 --disk-budget-mb 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.benchmarking.research_cycle_benchmarks.budgets import ResourceBudgets
from tools.benchmarking.research_cycle_benchmarks.harness import (
    SCHEMA_VERSION,
    run_all,
    run_target,
)
from tools.benchmarking.research_cycle_benchmarks.telemetry import (
    dumps,
    execute_child,
    json_safe,
)
from tools.benchmarking.research_cycle_benchmarks.workloads import TARGETS


def _budgets(args: argparse.Namespace) -> ResourceBudgets:
    mb = lambda v: None if v is None else int(v * 1024 * 1024)
    return ResourceBudgets(
        memory_bytes=mb(args.memory_budget_mb),
        disk_bytes=mb(args.disk_budget_mb),
        runtime_s=args.runtime_budget_s,
        rss_bytes=mb(args.rss_budget_mb),
    )


def _write_atomic(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            h.write(text)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _run_isolated(args: argparse.Namespace) -> Dict[str, Any]:
    """Run each target in its own child process with a hard per-target timeout."""
    budgets = _budgets(args)
    names = sorted(TARGETS.keys())
    results: List[Dict[str, Any]] = []
    summary: Dict[str, int] = {}
    for name in names:
        argv = [sys.executable, str(Path(__file__).resolve()), "child",
                "--target", name, "--seed", str(args.seed),
                "--repetitions", str(args.repetitions)]
        if args.size is not None:
            argv += ["--size", str(args.size)]
        child = execute_child(argv, timeout_s=args.per_target_timeout_s)
        if child.timed_out:
            record = {"target": name, "status": "timeout",
                      "deterministic": {"checksum_match": None},
                      "telemetry": None, "child_elapsed_s": child.elapsed_s,
                      "evidence_class": "performance_only", "synthetic": True}
        elif child.exit_code != 0:
            record = {"target": name, "status": "child_crash",
                      "deterministic": {"checksum_match": None},
                      "exit_code": child.exit_code, "stderr_tail": child.stderr[-500:],
                      "evidence_class": "performance_only", "synthetic": True}
        else:
            try:
                record = json.loads(child.stdout.strip().splitlines()[-1])
            except Exception as exc:
                record = {"target": name, "status": "infrastructure_failure",
                          "error": f"unparseable child output: {exc}",
                          "evidence_class": "performance_only", "synthetic": True}
        summary[record.get("status", "unknown")] = summary.get(record.get("status", "unknown"), 0) + 1
        results.append(record)
    return json_safe({
        "schema": SCHEMA_VERSION, "mode": "isolated",
        "evidence_class": "performance_only", "synthetic": True,
        "config": {"seed": args.seed, "size": args.size, "repetitions": args.repetitions,
                   "per_target_timeout_s": args.per_target_timeout_s, "max_workers": 1},
        "budgets": budgets.to_dict(), "num_targets": len(results),
        "summary": summary, "results": results,
        "notes": ["Each target ran in its own bounded, timed child process (shell=False)."],
    })


def _cmd_child(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="child")
    ap.add_argument("--target", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--repetitions", type=int, default=3)
    a = ap.parse_args(argv)
    if a.target not in TARGETS:
        print(json.dumps({"target": a.target, "status": "error",
                          "error": "unknown target"}), flush=True)
        return 2
    record = run_target(TARGETS[a.target], ResourceBudgets(),
                        seed=a.seed, size=a.size, repetitions=a.repetitions)
    print(json.dumps(record, allow_nan=False), flush=True)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "child":
        return _cmd_child(argv[1:])

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--memory-budget-mb", type=float, default=None)
    ap.add_argument("--disk-budget-mb", type=float, default=None)
    ap.add_argument("--rss-budget-mb", type=float, default=None)
    ap.add_argument("--runtime-budget-s", type=float, default=None)
    ap.add_argument("--isolated", action="store_true",
                    help="run each target in its own bounded, timed child process")
    ap.add_argument("--per-target-timeout-s", type=float, default=60.0)
    ap.add_argument("--output", type=str, default=None, help="atomic JSON report path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = _run_isolated(args) if args.isolated else run_all(
        _budgets(args), seed=args.seed, size=args.size, repetitions=args.repetitions)

    text = dumps(report)
    if args.output:
        _write_atomic(args.output, text)
    if args.json:
        print(text)
    else:
        print(f"schema={report['schema']} targets={report['num_targets']} "
              f"summary={report['summary']} "
              f"all_equivalent={report.get('all_equivalent')} "
              f"all_within_budget={report.get('all_within_budget')}")
        for r in report["results"]:
            det = r.get("deterministic", {})
            print(f"  {r['target']:40s} {r['status']:18s} match={det.get('checksum_match')}")

    ok = report.get("all_equivalent") in (True, None) and all(
        r.get("status") in ("ok",) or r.get("deterministic", {}).get("checksum_match") is True
        for r in report["results"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
