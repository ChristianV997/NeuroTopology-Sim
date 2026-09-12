#!/usr/bin/env python
"""CLI for the migration-wave benchmark (local-only, synthetic).

Compares current origin/main with PRs #331, #344, #345, and #346.
No production edits. No OpenNeuro/AWS/DANDI downloads.

Usage:
    python scripts/benchmark_migration_wave.py --size 64 --repetitions 1
    python scripts/benchmark_migration_wave.py generate --out tools/benchmarking/migration_wave/outputs
    python scripts/benchmark_migration_wave.py validate --root tools/benchmarking/migration_wave/outputs
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]


def _child(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="child")
    parser.add_argument("--variant-root", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args(argv)
    variant_root = str(Path(args.variant_root).resolve())
    for name in list(sys.modules):
        if name == "tools" or name.startswith("tools.") or name == "data" or name.startswith("data.") or name == "validation" or name.startswith("validation."):
            del sys.modules[name]
    while variant_root in sys.path:
        sys.path.remove(variant_root)
    sys.path.insert(0, variant_root)
    spec = importlib.util.spec_from_file_location(
        "mw_probes_isolated",
        ROOT / "tools" / "benchmarking" / "migration_wave" / "probes.py",
    )
    if spec is None or spec.loader is None:
        print(json.dumps({"ok": False, "reason": "probe_load_failed", "checksum": None}))
        return 2
    probes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probes)
    result = probes.run_measured(args.target, seed=args.seed, size=args.size, repetitions=args.repetitions)
    print(json.dumps(result, allow_nan=False, default=str))
    return 0 if result.get("ok") is not False else 1


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


def _variant_overrides(ns: argparse.Namespace) -> Dict[str, str]:
    mapping = {
        "current_main": ns.current_main_root,
        "pr_331": ns.pr_331_root,
        "pr_344": ns.pr_344_root,
        "pr_345": ns.pr_345_root,
        "pr_346": ns.pr_346_root,
    }
    return {key: value for key, value in mapping.items() if value}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "child":
        return _child(argv[1:])

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets
    from tools.benchmarking.pipeline_efficiency.telemetry import dumps
    from tools.benchmarking.migration_wave.harness import run_all
    from tools.benchmarking.migration_wave.reporting import generate
    from tools.benchmarking.migration_wave.schema import EVIDENCE_CLASS
    from tools.benchmarking.migration_wave.validator import validate_root

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
        parser.add_argument("--size", type=int, default=64)
        parser.add_argument("--repetitions", type=int, default=1)
        parser.add_argument("--isolated", action="store_true")
        parser.add_argument("--current-main-root", default=None)
        parser.add_argument("--pr-331-root", default=None)
        parser.add_argument("--pr-344-root", default=None)
        parser.add_argument("--pr-345-root", default=None)
        parser.add_argument("--pr-346-root", default=None)
        parser.add_argument("--variants", default=None, help="Comma-separated variant names")
        args = parser.parse_args(argv[1:])
        report = generate(
            args.out,
            seed=args.seed,
            size=args.size,
            repetitions=args.repetitions,
            isolated=args.isolated,
            harness_root=ROOT,
            variant_roots=_variant_overrides(args),
            variants=args.variants.split(",") if args.variants else None,
        )
        print(
            f"schema={report['schema']} results={report['num_results']} "
            f"summary={report.get('summary')} evidence_class={EVIDENCE_CLASS}"
        )
        return 0

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--memory-budget-mb", type=float, default=None)
    parser.add_argument("--disk-budget-mb", type=float, default=None)
    parser.add_argument("--rss-budget-mb", type=float, default=None)
    parser.add_argument("--runtime-budget-s", type=float, default=None)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--per-target-timeout-s", type=float, default=45.0)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--variants", default=None, help="Comma-separated variant names")
    parser.add_argument("--current-main-root", default=None)
    parser.add_argument("--pr-331-root", default=None)
    parser.add_argument("--pr-344-root", default=None)
    parser.add_argument("--pr-345-root", default=None)
    parser.add_argument("--pr-346-root", default=None)
    args = parser.parse_args(argv)

    mb = lambda v: None if v is None else int(v * 1024 * 1024)
    budgets = ResourceBudgets(
        memory_bytes=mb(args.memory_budget_mb),
        disk_bytes=mb(args.disk_budget_mb),
        runtime_s=args.runtime_budget_s,
        rss_bytes=mb(args.rss_budget_mb),
    )
    report = run_all(
        budgets,
        seed=args.seed,
        size=args.size,
        repetitions=args.repetitions,
        isolated=args.isolated,
        per_target_timeout_s=args.per_target_timeout_s,
        harness_root=ROOT,
        variant_roots=_variant_overrides(args),
        variants=args.variants.split(",") if args.variants else None,
    )
    text = dumps(report)
    if args.output:
        dest = Path(args.output)
        if dest.suffix.lower() == ".json":
            _write_atomic(str(dest), text)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            _write_atomic(str(dest / "migration_wave_report.json"), text)
    summary = (
        f"schema={report['schema']} results={report['num_results']} "
        f"summary={report.get('summary')} evidence_class={EVIDENCE_CLASS}"
    )
    if args.json and not args.output:
        print(text)
    else:
        print(summary)
        if args.output:
            print(f"output={args.output}")
        for row in report.get("results") or []:
            print(f"  {row.get('variant'):14s} {row.get('target'):28s} {row.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
