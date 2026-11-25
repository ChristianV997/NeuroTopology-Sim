#!/usr/bin/env python
"""Normalize heterogeneous benchmark reports into comparable evidence records.

Does not run benchmarks. Consumes JSON produced by process-isolated runners,
matrix orchestration, or telemetry exporters and writes finite, deterministic
normalized evidence (and optional pair-wise decisions).

Examples
--------
Normalize a list / results wrapper::

    python scripts/normalize_benchmark_evidence.py \\
      --input benchmark_reports.json \\
      --output normalized_evidence.json

Compare baseline vs candidate objects in one file::

    python scripts/normalize_benchmark_evidence.py \\
      --input pair.json --output decision.json --compare
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.performance.evidence_normalizer import (
    NORMALIZATION_SCHEMA_VERSION,
    compare_evidence,
    dumps,
    load_reports,
    normalize_reports,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Path to benchmark_reports.json")
    p.add_argument("--output", required=True, help="Path to normalized_evidence.json")
    p.add_argument(
        "--compare",
        action="store_true",
        help="Treat input as {baseline, candidate} (or first two results) and emit a decision",
    )
    p.add_argument(
        "--max-runtime-ratio",
        type=float,
        default=1.25,
        help="Max candidate/baseline runtime ratio before regression (same-host only)",
    )
    p.add_argument(
        "--max-tracemalloc-ratio",
        type=float,
        default=1.10,
        help="Max tracemalloc ratio before regression",
    )
    p.add_argument(
        "--max-child-rss-ratio",
        type=float,
        default=1.25,
        help="Max child RSS ratio before regression (same-host only)",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        payload = load_reports(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to load input: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.compare:
        if isinstance(payload, dict) and "baseline" in payload and "candidate" in payload:
            baseline, candidate = payload["baseline"], payload["candidate"]
        else:
            records = normalize_reports(payload)
            if len(records) < 2:
                print("compare mode needs baseline+candidate or >=2 results", file=sys.stderr)
                return 2
            baseline, candidate = records[0].to_dict(), records[1].to_dict()
        decision = compare_evidence(
            baseline,
            candidate,
            max_runtime_regression_ratio=args.max_runtime_ratio,
            max_tracemalloc_regression_ratio=args.max_tracemalloc_ratio,
            max_child_rss_regression_ratio=args.max_child_rss_ratio,
        )
        payload_out = {
            "schema_version": NORMALIZATION_SCHEMA_VERSION,
            "mode": "compare",
            "evidence_class": "performance_only",
            "synthetic": True,
            "decision": decision.to_dict(),
        }
        text = dumps(payload_out)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"decision={decision.decision.value} comparable={decision.comparable}")
        print(f"wrote {out_path}")
        # Exit: 0 pass; 1 regression/correctness/timeout/crash/infra; 5 inconclusive/missing/not_comparable
        d = decision.decision.value
        if d == "pass":
            return 0
        if d in {"regression", "correctness_failure", "timeout", "child_crash", "infrastructure_blocked"}:
            return 1
        return 5

    normalized = normalize_reports(payload)
    payload_out = {
        "schema_version": NORMALIZATION_SCHEMA_VERSION,
        "mode": "normalize",
        "evidence_class": "performance_only",
        "synthetic": True,
        "count": len(normalized),
        "records": [r.to_dict() for r in normalized],
    }
    text = dumps(payload_out)
    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"normalized {len(normalized)} record(s)")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
