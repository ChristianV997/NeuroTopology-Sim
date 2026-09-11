#!/usr/bin/env python
"""Evaluate research-cycle operational release evidence (read-only).

Consumes Batch 1 JSON exports via adapters. Never emits scientific PASS or a
Bayes factor.

Example::

    PYTHONPATH=. python scripts/evaluate_research_cycle_release.py \\
      --input cycle_bundle.json \\
      --output artifacts/research_cycle_release
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.research_cycle_release.evaluator import evaluate_research_cycle_release
from tools.research_cycle_release.report import dumps, write_reports
from tools.research_cycle_release.schema import DecisionState


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Path to Batch 1 / bundle JSON")
    p.add_argument("--output", default="artifacts/research_cycle_release", help="Output directory")
    p.add_argument(
        "--adapter",
        choices=("auto", "generic", "awareness", "registry"),
        default="auto",
        help="Force adapter selection (default: auto-detect)",
    )
    p.add_argument("--json-stdout", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    path = Path(args.input)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to load input: {exc}", file=sys.stderr)
        return 2

    hint = None if args.adapter == "auto" else args.adapter
    try:
        report = evaluate_research_cycle_release(payload, adapter_hint=hint)
    except (TypeError, ValueError) as exc:
        print(f"failed to evaluate: {exc}", file=sys.stderr)
        return 2

    paths = write_reports(report, args.output)
    if args.json_stdout:
        print(dumps(report.to_dict()))
    else:
        print(f"decision={report.decision.value}")
        print(f"cycle_id={report.cycle_id}")
        print(f"reason_codes={report.reason_codes}")
        print("scientific_pass_emitted=False")
        print("bayes_factor_emitted=False")
        for label, pth in paths.items():
            print(f"wrote {label}={pth}")

    if report.decision == DecisionState.EVIDENCE_READY_FOR_REVIEW:
        return 0
    if report.decision in {
        DecisionState.NETWORK_POLICY_FAILURE,
        DecisionState.PROVENANCE_FAILURE,
        DecisionState.ARTIFACT_FAILURE,
        DecisionState.VALIDATION_FAILURE,
        DecisionState.RESOURCE_FAILURE,
        DecisionState.INFRASTRUCTURE_BLOCKED,
    }:
        return 1
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
