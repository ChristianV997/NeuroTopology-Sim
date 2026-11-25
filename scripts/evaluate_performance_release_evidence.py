#!/usr/bin/env python
"""Evaluate release readiness of normalized performance evidence pairs.

Consumes PR #258-compatible normalized benchmark records. Does not run
benchmarks and does not modify the normalizer, performance policy, streaming
code, or process runner.

Example::

    python scripts/evaluate_performance_release_evidence.py \\
      --input normalized_pair.json \\
      --output-json release_evidence.json \\
      --output-md release_evidence.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.performance.release_evidence_gate import (
    GateThresholds,
    ReleaseDecision,
    dumps,
    evaluate_release_evidence,
    load_pair,
    render_markdown,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="JSON with baseline+candidate or results[2]")
    p.add_argument("--output-json", required=True, help="Path for finite JSON report")
    p.add_argument("--output-md", default=None, help="Optional Markdown report path")
    p.add_argument("--min-repetitions", type=int, default=3)
    p.add_argument("--max-runtime-rel-spread", type=float, default=0.50)
    p.add_argument("--max-runtime-ratio", type=float, default=1.25)
    p.add_argument("--max-tracemalloc-ratio", type=float, default=1.10)
    p.add_argument("--max-child-rss-ratio", type=float, default=1.25)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        baseline, candidate = load_pair(args.input)
    except (OSError, ValueError, TypeError) as exc:
        print(f"failed to load input: {exc}", file=sys.stderr)
        return 2

    thresholds = GateThresholds(
        min_repetitions=args.min_repetitions,
        max_runtime_rel_spread=args.max_runtime_rel_spread,
        max_runtime_regression_ratio=args.max_runtime_ratio,
        max_tracemalloc_regression_ratio=args.max_tracemalloc_ratio,
        max_child_rss_regression_ratio=args.max_child_rss_ratio,
    )
    report = evaluate_release_evidence(
        baseline,
        candidate,
        thresholds,
        test_metadata={"cli": "evaluate_performance_release_evidence"},
    )

    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(dumps(report.to_dict()) + "\n", encoding="utf-8")

    md_text = render_markdown(report)
    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md_text, encoding="utf-8")

    print(f"decision={report.decision.value}")
    print(f"comparable={report.comparable}")
    print(f"reason_codes={report.reason_codes}")
    print(f"wrote {out_json}")
    if args.output_md:
        print(f"wrote {args.output_md}")

    # Exit codes: 0 ready; 1 failure/regression/timeout/infra/correctness;
    # 5 inconclusive / not comparable / missing metric.
    d = report.decision
    if d == ReleaseDecision.EVIDENCE_READY:
        return 0
    if d in {
        ReleaseDecision.CORRECTNESS_FAILURE,
        ReleaseDecision.TIMEOUT_FAILURE,
        ReleaseDecision.INFRASTRUCTURE_BLOCKED,
        ReleaseDecision.REGRESSION_DETECTED,
    }:
        return 1
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
