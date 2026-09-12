#!/usr/bin/env python
"""Benchmark bounded-access vs rejected full-object requests (local-only).

Consumes production cache/streaming/policy modules read-only. Never downloads
OpenNeuro/AWS/DANDI data and never claims scientific improvement.

Example::

    PYTHONPATH=. python scripts/benchmark_data_migration_effectiveness.py \\
      --size 64 --repetitions 1 --output artifacts/data_migration_effectiveness
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.benchmarking.data_migration_effectiveness.budgets import ResourceBudgets
from tools.benchmarking.data_migration_effectiveness.harness import run_all, run_target
from tools.benchmarking.data_migration_effectiveness.report import dumps, generate, write_reports
from tools.benchmarking.data_migration_effectiveness.schema import TARGET_NAMES
from tools.benchmarking.data_migration_effectiveness.telemetry import execute_child
from tools.benchmarking.data_migration_effectiveness.validator import validate_root
from tools.benchmarking.data_migration_effectiveness.workloads import TARGETS


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--size", type=int, default=64)
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--target", default=None)
    p.add_argument("--output", default="artifacts/data_migration_effectiveness")
    p.add_argument("--memory-budget-mb", type=float, default=None)
    p.add_argument("--disk-budget-mb", type=float, default=None)
    p.add_argument("--runtime-budget-s", type=float, default=None)
    p.add_argument("--rss-budget-mb", type=float, default=None)
    p.add_argument("--isolated", action="store_true")
    p.add_argument("--per-target-timeout-s", type=float, default=30.0)
    p.add_argument("--json-stdout", action="store_true")
    p.add_argument("mode", nargs="?", default="run", choices=("run", "child", "generate", "validate"))
    return p.parse_args(argv)


def _budgets(args) -> ResourceBudgets:
    mb = lambda v: None if v is None else int(v * 1024 * 1024)
    return ResourceBudgets(
        memory_bytes=mb(args.memory_budget_mb),
        disk_bytes=mb(args.disk_budget_mb),
        runtime_s=args.runtime_budget_s,
        rss_bytes=mb(args.rss_budget_mb),
    )


def main(argv=None) -> int:
    args = parse_args(argv)
    budgets = _budgets(args)
    if args.mode == "validate":
        result = validate_root(args.output)
        print(dumps(result))
        return 0 if result.get("ok") else 1
    if args.mode == "generate":
        payload = generate(args.output, seed=args.seed, size=args.size, repetitions=args.repetitions)
        if args.json_stdout:
            print(dumps(payload))
        else:
            print(f"schema={payload.get('schema')}")
            print(f"all_checksums_match={payload.get('all_checksums_match')}")
            print(f"scientific_improvement_claimed={payload.get('scientific_improvement_claimed')}")
            print(f"wrote pack={args.output}")
        return 0 if payload.get("all_checksums_match", True) else 1
    if args.mode == "child":
        if not args.target or args.target not in TARGETS:
            print("child requires --target", file=sys.stderr)
            return 2
        row = run_target(
            args.target,
            budgets,
            seed=args.seed,
            size=args.size,
            repetitions=args.repetitions,
        )
        print(dumps(row, indent=None), flush=True)
        return 0 if row.get("status") in {"ok", "timeout", "rejected", "budget_overrun"} else 1

    names = [args.target] if args.target else sorted(TARGET_NAMES)
    if args.isolated:
        results = []
        script = str(Path(__file__).resolve())
        for name in names:
            child = execute_child(
                [
                    sys.executable,
                    script,
                    "child",
                    "--target",
                    name,
                    "--seed",
                    str(args.seed),
                    "--size",
                    str(args.size),
                    "--repetitions",
                    str(args.repetitions),
                ],
                timeout_s=args.per_target_timeout_s,
            )
            if child.timed_out:
                results.append({"target": name, "status": "timeout", "isolated": True})
            elif child.exit_code != 0:
                results.append({"target": name, "status": "child_crash", "isolated": True, "stderr": child.stderr[-500:]})
            else:
                import json

                blob = child.stdout.strip()
                results.append(json.loads(blob))
        payload = {
            "schema": "data_migration_effectiveness/v1",
            "evidence_class": "performance_only",
            "synthetic": True,
            "scientific_improvement_claimed": False,
            "network_accessed": False,
            "full_dataset_download": False,
            "isolated": True,
            "config": {
                "seed": args.seed,
                "size": args.size,
                "repetitions": args.repetitions,
                "targets": names,
                "max_workers": 1,
            },
            "results": results,
            "all_checksums_match": all(
                (r.get("deterministic") or {}).get("checksum_match") for r in results if r.get("status") != "timeout" or r.get("deterministic")
            )
            and all((r.get("deterministic") or {}).get("checksum_match") is not False for r in results),
            "limitations": ["Isolated child execution; still local synthetic only."],
        }
    else:
        payload = run_all(
            seed=args.seed,
            size=args.size,
            repetitions=args.repetitions,
            budgets=budgets,
            targets=names,
        )

    paths = write_reports(payload, args.output)
    if args.json_stdout:
        print(dumps(payload))
    else:
        print(f"schema={payload.get('schema')}")
        print(f"all_checksums_match={payload.get('all_checksums_match')}")
        print(f"scientific_improvement_claimed={payload.get('scientific_improvement_claimed')}")
        print(f"network_accessed={payload.get('network_accessed')}")
        print(f"regressions={payload.get('regressions')}")
        print(f"optimization_candidates={payload.get('optimization_candidates')}")
        for label, pth in paths.items():
            print(f"wrote {label}={pth}")
    return 0 if payload.get("all_checksums_match", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
