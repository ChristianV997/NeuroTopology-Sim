#!/usr/bin/env python3
"""Thin CLI over tools.research_plan_quality. Fully offline, no
downloads, no model calls, no paper-corpus ingestion -- reads one local
JSON research-plan file and prints a deterministic audit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.research_plan_quality.models import ResearchPlan  # noqa: E402
from tools.research_plan_quality.reporting import to_finite_json, to_markdown  # noqa: E402
from tools.research_plan_quality.rubric import evaluate_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="path to a research-plan JSON file")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument(
        "--include-generated-at", default=None,
        help="explicit timestamp string to embed as generated_at (omit to leave it null)",
    )
    args = parser.parse_args()

    plan = ResearchPlan.from_dict(json.loads(args.plan.read_text()))
    result = evaluate_plan(
        plan,
        include_generated_at=args.include_generated_at is not None,
        generated_at_value=args.include_generated_at,
    )

    json_text = to_finite_json(result)
    markdown_text = to_markdown(result)

    if args.json_out:
        args.json_out.write_text(json_text)
    else:
        print(json_text)
    if args.markdown_out:
        args.markdown_out.write_text(markdown_text)

    print(f"overall_status={result.overall_status} overall_score={result.overall_score}", file=sys.stderr)
    return 0 if result.overall_status != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
