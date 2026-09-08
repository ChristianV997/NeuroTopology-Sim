#!/usr/bin/env python
"""Evaluate benchmark JSON records against a performance-regression policy.

Two modes:

* **compare** -- baseline vs candidate benchmark records:
      python scripts/evaluate_performance_budget.py compare \
          --baseline baseline.json --candidate candidate.json \
          --max-runtime-ratio 1.25 --max-tracemalloc-ratio 1.10
* **budget** -- a single record against absolute budgets:
      python scripts/evaluate_performance_budget.py budget \
          --record candidate.json --peak-rss-budget-mb 300 --tracemalloc-budget-mb 16

Records are flat JSON objects shaped like the process-memory telemetry output
(fields: ``backend``, ``input_dims``, ``chunk_size``, ``repetitions``,
``wall_best_s``, ``wall_mean_s``, ``tracemalloc_peak_bytes``, ``peak_rss_bytes``,
``checksum``, optional ``hardware``/``synthetic``). Missing metrics are treated
as unknown (``null``), never as zero or as a pass.

Output is JSON with no NaN/Infinity. Exit codes:
    0 pass / within-budget
    2 regression / over-budget
    3 correctness failure
    4 invalid comparison
    5 inconclusive (required data missing)

This tool only *reads* records; it runs no benchmarks and imports no streaming
or kernel code. Synthetic benchmarks are performance evidence only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from tools.streaming.performance_policy import (
    PolicyThresholds,
    Verdict,
    compare_records,
    dumps,
    evaluate_against_budget,
)

_VERDICT_EXIT = {
    Verdict.PASS.value: 0,
    Verdict.REGRESSION.value: 2,
    Verdict.CORRECTNESS_FAILURE.value: 3,
    Verdict.INVALID_COMPARISON.value: 4,
    Verdict.INCONCLUSIVE.value: 5,
}


def _load_record(path: str, pointer: Optional[str] = None) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if pointer:
        for key in pointer.split("."):
            if isinstance(data, list):
                data = data[int(key)]
            else:
                data = data[key]
    if not isinstance(data, dict):
        raise ValueError(f"record at {path!r} (pointer={pointer!r}) is not a JSON object")
    return data


def _thresholds_from_args(args: argparse.Namespace) -> PolicyThresholds:
    defaults = PolicyThresholds()
    return PolicyThresholds(
        checksum_rel_tol=args.checksum_rel_tol,
        max_runtime_regression_ratio=args.max_runtime_ratio,
        max_peak_rss_regression_ratio=args.max_peak_rss_ratio,
        max_tracemalloc_regression_ratio=args.max_tracemalloc_ratio,
        min_repetitions=args.min_repetitions,
        max_runtime_rel_spread=defaults.max_runtime_rel_spread,
        require_same_backend=not args.allow_backend_mismatch,
        require_same_hardware=args.require_same_hardware,
    )


def _cmd_compare(args: argparse.Namespace) -> int:
    baseline = _load_record(args.baseline, args.baseline_pointer)
    candidate = _load_record(args.candidate, args.candidate_pointer)
    report = compare_records(baseline, candidate, _thresholds_from_args(args))
    print(dumps(report.to_dict()))
    return _VERDICT_EXIT.get(report.verdict.value, 1)


def _cmd_budget(args: argparse.Namespace) -> int:
    record = _load_record(args.record, args.record_pointer)
    to_bytes = lambda mb: None if mb is None else int(mb * 1024 * 1024)
    result = evaluate_against_budget(
        record,
        peak_rss_budget_bytes=to_bytes(args.peak_rss_budget_mb),
        tracemalloc_budget_bytes=to_bytes(args.tracemalloc_budget_mb),
        runtime_budget_s=args.runtime_budget_s,
        thresholds=_thresholds_from_args(args),
    )
    print(dumps(result))
    within = result["within_budget"]
    if within is True:
        return 0
    if within is False:
        return 2
    return 5  # nothing evaluable


def _add_threshold_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--checksum-rel-tol", type=float, default=1e-9)
    p.add_argument("--max-runtime-ratio", type=float, default=1.25)
    p.add_argument("--max-peak-rss-ratio", type=float, default=1.25)
    p.add_argument("--max-tracemalloc-ratio", type=float, default=1.10)
    p.add_argument("--min-repetitions", type=int, default=3)
    p.add_argument("--allow-backend-mismatch", action="store_true")
    p.add_argument("--require-same-hardware", action="store_true")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    cmp_p = sub.add_parser("compare", help="baseline vs candidate policy check")
    cmp_p.add_argument("--baseline", required=True)
    cmp_p.add_argument("--candidate", required=True)
    cmp_p.add_argument("--baseline-pointer", default=None,
                       help="dotted path to a nested record inside the JSON")
    cmp_p.add_argument("--candidate-pointer", default=None)
    _add_threshold_args(cmp_p)
    cmp_p.set_defaults(func=_cmd_compare)

    bud_p = sub.add_parser("budget", help="single record vs absolute budgets")
    bud_p.add_argument("--record", required=True)
    bud_p.add_argument("--record-pointer", default=None)
    bud_p.add_argument("--peak-rss-budget-mb", type=float, default=None)
    bud_p.add_argument("--tracemalloc-budget-mb", type=float, default=None)
    bud_p.add_argument("--runtime-budget-s", type=float, default=None)
    _add_threshold_args(bud_p)
    bud_p.set_defaults(func=_cmd_budget)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
