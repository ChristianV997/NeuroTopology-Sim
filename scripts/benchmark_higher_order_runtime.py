#!/usr/bin/env python
"""Benchmark the bounded higher-order runtime layer (full vs bounded vs adaptive).

Self-contained parent orchestrator + child workload:

* (default)     run the benchmark in-process and print a finite JSON report.
* ``--isolated`` run the benchmark in a child process (process isolation) and
  attach the child's sampled RSS (``null`` when psutil is unavailable).
* ``child``     internal subcommand executed by ``--isolated``; prints the report.

Imports only this repo's owned ``tools/higher_order_runtime`` package -- never the
unmerged higher-order feature branches, streaming, or process-runner code. Uses
deterministic synthetic fixtures. No ``shell=True``; no network.

Scientific-integrity note: performance evidence only, never scientific/biological
evidence; runtime optimization does not alter scientific semantics.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make the package importable when this file is executed directly as a script
# (sys.path[0] would otherwise be scripts/, not the repository root).
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.higher_order_runtime.benchmark import WorkloadConfig, run_benchmark
from tools.higher_order_runtime.telemetry import dumps, execute_child


def _config_from_args(args: argparse.Namespace) -> WorkloadConfig:
    return WorkloadConfig(
        n_samples=args.samples, n_channels=args.channels, seed=args.seed,
        segment_len=args.segment_len, candidate_limit=args.candidate_limit,
        surrogate_limit=args.surrogate_limit,
    )


def _run_local(args: argparse.Namespace) -> Dict[str, Any]:
    cfg = _config_from_args(args)
    return run_benchmark(cfg, chunk_size=args.chunk_size, budget_bytes=args.budget_bytes,
                         tolerance=args.tolerance)


def _run_isolated(args: argparse.Namespace) -> Dict[str, Any]:
    child_cfg = {
        "samples": args.samples, "channels": args.channels, "seed": args.seed,
        "segment_len": args.segment_len, "candidate_limit": args.candidate_limit,
        "surrogate_limit": args.surrogate_limit, "chunk_size": args.chunk_size,
        "budget_bytes": args.budget_bytes, "tolerance": args.tolerance,
    }
    argv = [sys.executable, str(Path(__file__).resolve()), "child",
            "--config-json", json.dumps(child_cfg)]
    result = execute_child(argv, timeout_s=args.timeout_s)
    report: Optional[Dict[str, Any]] = None
    parse_error: Optional[str] = None
    if not result.timed_out and (result.stdout or "").strip():
        try:
            report = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception as exc:  # noqa: BLE001
            parse_error = str(exc)
    return {
        "isolated": True,
        "child_exit_code": result.exit_code,
        "child_timed_out": result.timed_out,
        "child_peak_rss_bytes": result.peak_rss_bytes,  # null when psutil absent
        "child_elapsed_s": result.elapsed_s,
        "parse_error": parse_error,
        "report": report,
    }


def _child_main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="child")
    ap.add_argument("--config-json", required=True)
    ns = ap.parse_args(argv)
    c = json.loads(ns.config_json)
    cfg = WorkloadConfig(
        n_samples=int(c["samples"]), n_channels=int(c["channels"]), seed=int(c["seed"]),
        segment_len=int(c["segment_len"]), candidate_limit=c["candidate_limit"],
        surrogate_limit=int(c["surrogate_limit"]),
    )
    report = run_benchmark(cfg, chunk_size=int(c["chunk_size"]),
                           budget_bytes=int(c["budget_bytes"]), tolerance=float(c["tolerance"]))
    sys.stdout.write(dumps(report, indent=None))
    sys.stdout.write("\n")
    return 0 if report["all_equivalent"] else 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "child":
        return _child_main(argv[1:])

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--channels", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--segment-len", type=int, default=512)
    ap.add_argument("--candidate-limit", type=int, default=64)
    ap.add_argument("--surrogate-limit", type=int, default=16)
    ap.add_argument("--chunk-size", type=int, default=2048)
    ap.add_argument("--budget-bytes", type=int, default=4 * 1024 * 1024)
    ap.add_argument("--tolerance", type=float, default=1e-9)
    ap.add_argument("--timeout-s", type=float, default=120.0)
    ap.add_argument("--isolated", action="store_true", help="run in a child process")
    ap.add_argument("--output", type=str, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    payload = _run_isolated(args) if args.isolated else _run_local(args)
    text = dumps(payload)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    if args.json:
        print(text)
    else:
        if args.isolated:
            rep = payload.get("report") or {}
            print(f"isolated child exit={payload['child_exit_code']} "
                  f"timed_out={payload['child_timed_out']} "
                  f"child_rss={payload['child_peak_rss_bytes']}")
            print(f"all_equivalent={rep.get('all_equivalent')} "
                  f"peak_ratio={rep.get('tracemalloc_peak_ratio_bounded_over_full')}")
        else:
            print(f"all_equivalent={payload['all_equivalent']} "
                  f"replay_identical={payload['deterministic_replay_identical']} "
                  f"checkpoint={payload['checkpoint_available']}")
            print(f"tracemalloc_peak_ratio_bounded_over_full="
                  f"{payload['tracemalloc_peak_ratio_bounded_over_full']}")
            for name, eq in payload["equivalence"].items():
                print(f"  {name}: equivalent={eq['equivalent']}")

    if args.isolated:
        rep = payload.get("report") or {}
        return 0 if rep.get("all_equivalent") else 1
    return 0 if payload["all_equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
