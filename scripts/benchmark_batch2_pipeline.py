#!/usr/bin/env python
"""CLI for the Batch-2 pipeline benchmark harness (local-only, synthetic).

Modes:
  default   run all targets in-process
  generate  run + write the artifact pack (Obsidian, command-center, RAG)
  validate  validate an existing artifact pack
  child     run one target (used by --isolated)

No OpenNeuro/AWS/DANDI downloads. No Awareness Studio import. No production edits.
Performance engineering only — never scientific claims.

Usage:
    python scripts/benchmark_batch2_pipeline.py --size 16 --repetitions 1 --json
    python scripts/benchmark_batch2_pipeline.py --isolated --per-target-timeout-s 30
    python scripts/benchmark_batch2_pipeline.py generate --out tools/benchmarks/batch2_pipeline/outputs
    python scripts/benchmark_batch2_pipeline.py validate --root tools/benchmarks/batch2_pipeline/outputs
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

from tools.benchmarks.batch2_pipeline.budgets import (
    ResourceBudgets,
    budget_result_is_consistent,
    telemetry_metrics_are_valid,
)
from tools.benchmarks.batch2_pipeline.harness import (
    SCHEMA_VERSION,
    aggregate_complete_boolean,
    run_all,
    run_target,
)
from tools.benchmarks.batch2_pipeline.reporting import generate
from tools.benchmarks.batch2_pipeline.schema import (
    EVIDENCE_CLASS,
    TARGET_NAMES,
    TargetStatus,
)
from tools.benchmarks.batch2_pipeline.telemetry import dumps, execute_child, json_safe
from tools.benchmarks.batch2_pipeline.validator import validate_report, validate_root
from tools.benchmarks.batch2_pipeline.workloads import TARGETS


def _budgets(args: argparse.Namespace) -> ResourceBudgets:
    mb = lambda v: None if v is None else int(v * 1024 * 1024)
    return ResourceBudgets(
        memory_bytes=mb(args.memory_budget_mb),
        disk_bytes=mb(args.disk_budget_mb),
        runtime_s=args.runtime_budget_s,
        rss_bytes=mb(args.rss_budget_mb),
        max_workers=args.max_workers,
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


def _cli_exit_code(report: Dict[str, Any]) -> int:
    """Return success only for a complete, internally consistent successful report.

    Advisory runtime/RSS do not drive ``all_within_budget`` (see budgets.py), so
    they cannot flip this exit code by themselves.
    """
    if not isinstance(report, dict):
        return 2
    if report.get("error"):
        return 2
    if (
        report.get("schema") != SCHEMA_VERSION
        and report.get("schema_version") != SCHEMA_VERSION
    ):
        return 2
    if report.get("evidence_class") != EVIDENCE_CLASS or report.get("synthetic") is not True:
        return 2
    config = report.get("config")
    if (
        not isinstance(config, dict)
        or type(config.get("max_workers")) is not int
        or config.get("max_workers") != 1
    ):
        return 2
    declared_budgets = report.get("budgets")
    if not isinstance(declared_budgets, dict):
        return 2
    if report.get("all_equivalent") is not True:
        return 1
    if report.get("all_within_budget") is not True:
        return 1
    num_targets = report.get("num_targets")
    results = report.get("results")
    summary = report.get("summary")
    if (
        type(num_targets) is not int
        or num_targets <= 0
        or not isinstance(results, list)
        or len(results) != num_targets
        or not isinstance(summary, dict)
    ):
        return 2

    known_statuses = {status.value for status in TargetStatus}
    result_counts: Dict[str, int] = {}
    result_targets: List[str] = []
    for record in results:
        if not isinstance(record, dict):
            return 1
        if (
            record.get("evidence_class") != EVIDENCE_CLASS
            or record.get("synthetic") is not True
        ):
            return 2
        target = record.get("target")
        if not isinstance(target, str) or target not in TARGET_NAMES:
            return 1
        result_targets.append(target)
        status = record.get("status")
        if not isinstance(status, str) or status not in known_statuses:
            return 1
        result_counts[status] = result_counts.get(status, 0) + 1
        if status != TargetStatus.OK.value:
            return 1
        deterministic = record.get("deterministic")
        if not isinstance(deterministic, dict) or deterministic.get("checksum_match") is not True:
            return 1
        budget = deterministic.get("budget")
        if not isinstance(budget, dict):
            return 1
        telemetry = record.get("telemetry")
        if not isinstance(telemetry, dict):
            return 2
        for side in ("baseline", "candidate"):
            if side in telemetry and not telemetry_metrics_are_valid(telemetry[side]):
                return 2
        candidate_metrics = (
            telemetry.get("candidate") if isinstance(telemetry, dict) else None
        )
        if not budget_result_is_consistent(
            budget,
            candidate_metrics,
            declared_budgets,
            config.get("max_workers"),
        ):
            return 2
        if budget.get("within_budget") is not True:
            return 1

    for status, count in summary.items():
        if not isinstance(status, str) or status not in known_statuses:
            return 1
        if type(count) is not int or count < 0:
            return 2
    configured_targets = config.get("targets")
    if (
        not isinstance(configured_targets, list)
        or not configured_targets
        or any(
            not isinstance(target, str) or target not in TARGET_NAMES
            for target in configured_targets
        )
        or configured_targets != result_targets
    ):
        return 2
    if summary != result_counts:
        return 2
    if sum(result_counts.values()) != num_targets:
        return 1
    # Keep CLI success aligned with validate_report for structural hazards the
    # earlier checks do not cover (non-finite floats, remote-host references, …).
    validation = validate_report(report)
    if not validation.get("ok"):
        return 2
    return 0


def _run_isolated(args: argparse.Namespace) -> Dict[str, Any]:
    budgets = _budgets(args)
    if args.target is not None and args.target not in TARGETS:
        return json_safe(
            {
                "schema": SCHEMA_VERSION,
                "mode": "isolated",
                "evidence_class": EVIDENCE_CLASS,
                "synthetic": True,
                "error": f"unknown target: {args.target!r}",
                "num_targets": 0,
                "summary": {},
                "results": [],
                "all_equivalent": None,
                "all_within_budget": None,
            }
        )
    names = sorted(TARGETS.keys()) if args.target is None else [args.target]
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
            "--max-workers",
            str(args.max_workers),
        ]
        if args.size is not None:
            argv += ["--size", str(args.size)]
        if args.memory_budget_mb is not None:
            argv += ["--memory-budget-mb", str(args.memory_budget_mb)]
        if args.disk_budget_mb is not None:
            argv += ["--disk-budget-mb", str(args.disk_budget_mb)]
        if args.rss_budget_mb is not None:
            argv += ["--rss-budget-mb", str(args.rss_budget_mb)]
        if args.runtime_budget_s is not None:
            argv += ["--runtime-budget-s", str(args.runtime_budget_s)]
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
    matches = [
        (r.get("deterministic") or {}).get("checksum_match")
        for r in results
    ]
    all_equivalent = aggregate_complete_boolean(matches)
    budget_verdicts = [(r.get("deterministic") or {}).get("budget", {}) or {} for r in results]
    all_within_budget = aggregate_complete_boolean(
        [v.get("within_budget") for v in budget_verdicts]
    )
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
                "targets": names,
                "max_workers": 1,
            },
            "budgets": budgets.to_dict(),
            "num_targets": len(results),
            "summary": summary,
            "all_equivalent": all_equivalent,
            "all_within_budget": all_within_budget,
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
    parser.add_argument("--memory-budget-mb", type=float, default=None)
    parser.add_argument("--disk-budget-mb", type=float, default=None)
    parser.add_argument("--rss-budget-mb", type=float, default=None)
    parser.add_argument("--runtime-budget-s", type=float, default=None)
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.target not in TARGETS:
        print(json.dumps({"target": args.target, "status": "error", "error": "unknown target"}), flush=True)
        return 2
    record = run_target(
        TARGETS[args.target],
        _budgets(args),
        seed=args.seed,
        size=args.size,
        repetitions=args.repetitions,
    )
    # Always exit 0 when a JSON record was emitted so the parent can parse
    # status (including budget_overrun) instead of treating it as child_crash.
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
        return _cli_exit_code(report)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=None)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--memory-budget-mb", type=float, default=None)
    parser.add_argument("--disk-budget-mb", type=float, default=None)
    parser.add_argument("--rss-budget-mb", type=float, default=None)
    parser.add_argument("--runtime-budget-s", type=float, default=None)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--target", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--per-target-timeout-s", type=float, default=60.0)
    args = parser.parse_args(argv)

    if args.max_workers != 1:
        print("error: max_workers must be 1 (bounded)", file=sys.stderr)
        return 2

    if args.target is not None and args.target not in TARGETS and not args.isolated:
        print(f"error: unknown target {args.target!r}", file=sys.stderr)
        return 2

    if args.isolated:
        report = _run_isolated(args)
    else:
        budgets = _budgets(args)
        targets = [args.target] if args.target else None
        report = run_all(
            budgets,
            seed=args.seed,
            size=args.size,
            repetitions=args.repetitions,
            targets=targets,
        )

    text = dumps(report) if args.json or args.output else (
        f"schema={report.get('schema')} targets={report.get('num_targets')} "
        f"summary={report.get('summary')} all_equivalent={report.get('all_equivalent')} "
        f"all_within_budget={report.get('all_within_budget')}"
    )
    if args.output:
        _write_atomic(args.output, (dumps(report) if not args.json else text) + "\n")
    print(text if args.json or not args.output else f"wrote {args.output}")
    return _cli_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
