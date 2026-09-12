#!/usr/bin/env python
"""CLI for the post-merge pipeline benchmark harness (local-only, synthetic).

Measures current main after the streaming-ingest merge. No production edits.
No OpenNeuro/AWS/DANDI downloads. No Awareness Studio import from this package.

Usage:
    python scripts/benchmark_post_merge_pipeline.py --size 16 --repetitions 1 --json
    python scripts/benchmark_post_merge_pipeline.py --isolated --per-target-timeout-s 45
    python scripts/benchmark_post_merge_pipeline.py generate --out tools/benchmarking/post_merge_pipeline/outputs
    python scripts/benchmark_post_merge_pipeline.py validate --root tools/benchmarking/post_merge_pipeline/outputs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets
from tools.benchmarking.post_merge_pipeline.harness import SCHEMA_VERSION, run_all, run_target
from tools.benchmarking.post_merge_pipeline.reporting import generate
from tools.benchmarking.post_merge_pipeline.schema import EVIDENCE_CLASS
from tools.benchmarking.pipeline_efficiency.telemetry import dumps, execute_child, json_safe
from tools.benchmarking.post_merge_pipeline.validator import validate_root
from tools.benchmarking.post_merge_pipeline.workloads import TARGETS


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
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _run_isolated(args: argparse.Namespace) -> Dict[str, Any]:
    budgets = _budgets(args)
    names = sorted(TARGETS.keys())
    if args.target:
        names = [args.target] if args.target in TARGETS else []
    results: List[Dict[str, Any]] = []
    summary: Dict[str, int] = {}
    script = str(Path(__file__).resolve())
    for name in names:
        argv = [
            sys.executable,
            script,
            "child",
            "--target",
            name,
            "--seed",
            str(args.seed),
            "--repetitions",
            str(args.repetitions),
        ]
        if args.size is not None:
            argv += ["--size", str(args.size)]
        child = execute_child(argv, timeout_s=args.per_target_timeout_s)
        if child.timed_out:
            record = {
                "target": name,
                "status": "timeout",
                "deterministic": {"checksum_match": None},
                "telemetry": None,
                "child_elapsed_s": child.elapsed_s,
                "evidence_class": EVIDENCE_CLASS,
                "synthetic": True,
            }
        elif child.exit_code != 0:
            record = {
                "target": name,
                "status": "child_crash",
                "deterministic": {"checksum_match": None},
                "exit_code": child.exit_code,
                "stderr_tail": child.stderr[-500:],
                "evidence_class": EVIDENCE_CLASS,
                "synthetic": True,
            }
        else:
            try:
                record = json.loads(child.stdout.strip().splitlines()[-1])
            except Exception as exc:
                record = {
                    "target": name,
                    "status": "infrastructure_failure",
                    "error": f"unparseable child output: {exc}",
                    "evidence_class": EVIDENCE_CLASS,
                    "synthetic": True,
                }
        summary[record.get("status", "unknown")] = summary.get(record.get("status", "unknown"), 0) + 1
        results.append(record)
    return json_safe(
        {
            "schema": SCHEMA_VERSION,
            "mode": "isolated",
            "evidence_class": EVIDENCE_CLASS,
            "synthetic": True,
            "config": {
                "seed": args.seed,
                "size": args.size,
                "repetitions": args.repetitions,
                "per_target_timeout_s": args.per_target_timeout_s,
                "max_workers": 1,
            },
            "budgets": budgets.to_dict(),
            "num_targets": len(results),
            "summary": summary,
            "results": results,
            "notes": [
                "Each target ran in its own bounded, timed child process (shell=False).",
                "Synthetic performance evidence only.",
            ],
        }
    )


def _cmd_child(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="child")
    parser.add_argument("--target", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=None)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args(argv)
    if args.target not in TARGETS:
        print(json.dumps({"target": args.target, "status": "error", "error": "unknown target"}), flush=True)
        return 2
    record = run_target(
        TARGETS[args.target],
        ResourceBudgets(),
        seed=args.seed,
        size=args.size,
        repetitions=args.repetitions,
    )
    print(json.dumps(record, allow_nan=False), flush=True)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "child":
        return _cmd_child(argv[1:])
    if argv and argv[0] == "validate":
        parser = argparse.ArgumentParser(prog="validate")
        parser.add_argument("--root", required=True)
        args = parser.parse_args(argv[1:])
        result = validate_root(args.root)
        print(dumps(result))
        return 0 if result["ok"] else 1
    if argv and argv[0] == "generate":
        parser = argparse.ArgumentParser(prog="generate")
        parser.add_argument("--out", required=True)
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--size", type=int, default=16)
        parser.add_argument("--repetitions", type=int, default=1)
        args = parser.parse_args(argv[1:])
        report = generate(args.out, seed=args.seed, size=args.size, repetitions=args.repetitions)
        print(
            f"schema={report['schema']} targets={report['num_targets']} "
            f"summary={report['summary']} all_equivalent={report.get('all_equivalent')}"
        )
        return 0 if report.get("all_equivalent") is not False else 1

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=None)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--memory-budget-mb", type=float, default=None)
    parser.add_argument("--disk-budget-mb", type=float, default=None)
    parser.add_argument("--rss-budget-mb", type=float, default=None)
    parser.add_argument("--runtime-budget-s", type=float, default=None)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--per-target-timeout-s", type=float, default=60.0)
    parser.add_argument("--target", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = _run_isolated(args) if args.isolated else run_all(
        _budgets(args),
        seed=args.seed,
        size=args.size,
        repetitions=args.repetitions,
        targets=[args.target] if args.target else None,
    )
    text = dumps(report)
    if args.output:
        _write_atomic(args.output, text)
    if args.json:
        print(text)
    else:
        print(
            f"schema={report['schema']} targets={report['num_targets']} "
            f"summary={report.get('summary')} "
            f"all_equivalent={report.get('all_equivalent')} "
            f"all_within_budget={report.get('all_within_budget')}"
        )
        for row in report.get("results") or []:
            det = row.get("deterministic") or {}
            print(f"  {str(row.get('target')):40s} {str(row.get('status')):18s} match={det.get('checksum_match')}")

    ok = report.get("all_equivalent") in (True, None) and all(
        row.get("status") in ("ok", "budget_overrun", "timeout")
        or (row.get("deterministic") or {}).get("checksum_match") is True
        for row in report.get("results") or []
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
