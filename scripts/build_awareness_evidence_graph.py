#!/usr/bin/env python3
"""CLI utility to generate deterministic evidence graph projections for Awareness Studio.

Accepts JSON/JSONL manifests, builds graph projection, audits integrity diagnostics,
and exports JSON, Markdown, and HTML-independent summaries.

Usage:
    python scripts/build_awareness_evidence_graph.py --manifest path/to/manifest.json --output-json graph.json --output-md report.md
    python scripts/build_awareness_evidence_graph.py -m path/to/manifest.json --filter-evidence-class empirical formal --strict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repository root and apps/awareness_studio/src are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIO_SRC = REPO_ROOT / "apps" / "awareness_studio" / "src"
for p in (REPO_ROOT, STUDIO_SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from awareness_studio.research_graph import (
    DiagnosticSeverity,
    EvidenceGraphBuilder,
    load_manifest_file,
    save_graph,
    to_awareness_summary,
    to_json,
    to_markdown,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic read-only research-cycle evidence graph projection."
    )
    parser.add_argument(
        "--manifest",
        "-m",
        required=True,
        help="Path to input JSON/JSONL manifest file.",
    )
    parser.add_argument(
        "--output-json",
        "-o",
        help="Path to write canonical RFC-8259 projection graph JSON.",
    )
    parser.add_argument(
        "--output-md",
        help="Path to write structured audit Markdown report.",
    )
    parser.add_argument(
        "--output-summary",
        help="Path to write compact Awareness Studio summary JSON.",
    )
    parser.add_argument(
        "--filter-evidence-class",
        nargs="+",
        choices=["synthetic", "proxy", "empirical", "formal", "unknown"],
        help="Filter projected subgraph to specified evidence classes.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero code if any critical error diagnostics are detected.",
    )

    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.exists():
        print(f"ERROR: Manifest file does not exist: {manifest_path}", file=sys.stderr)
        return 2

    try:
        graph = load_manifest_file(manifest_path)
    except Exception as exc:
        print(f"ERROR: Failed to load manifest '{manifest_path}': {exc}", file=sys.stderr)
        return 2

    # If evidence class filter specified
    if args.filter_evidence_class:
        graph = graph.filter_by_evidence_class(args.filter_evidence_class)

    # Save requested outputs
    if args.output_json:
        save_graph(graph, args.output_json, fmt="json")
        print(f"Saved canonical graph JSON to: {args.output_json}")

    if args.output_md:
        save_graph(graph, args.output_md, fmt="md")
        print(f"Saved audit Markdown report to: {args.output_md}")

    if args.output_summary:
        save_graph(graph, args.output_summary, fmt="summary")
        print(f"Saved Awareness Studio summary to: {args.output_summary}")

    # If no output specified, print summary to stdout
    if not (args.output_json or args.output_md or args.output_summary):
        print(json.dumps(to_awareness_summary(graph), indent=2))

    # Diagnostics check
    critical_errors = [
        d for d in graph.diagnostics if d.severity == DiagnosticSeverity.ERROR.value
    ]
    if critical_errors:
        print(f"\nWARNING: {len(critical_errors)} critical diagnostic error(s) detected:", file=sys.stderr)
        for err in critical_errors:
            print(f"  [{err.code}] {err.message} (Affected: {err.affected_ids})", file=sys.stderr)

        if args.strict:
            print("FAILED: --strict mode enabled and critical diagnostics were found.", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
