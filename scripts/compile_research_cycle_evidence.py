#!/usr/bin/env python3
"""CLI utility to compile simulation artifacts into canonical research-cycle bridge records.

Links:
- Source dataset & provenance
- Experiment plan
- Simulation run & metrics
- Artifact manifest
- Validation report
- Evidence graph
- Release-evidence decision

Scientific Guardrails:
- Never infer scientific validity from artifact presence.
- Never promote proxy, synthetic, or benchmark output to formal evidence.
- Preserves nulls instead of zero-filling missing metrics.
- Rejects missing or fabricated provenance.
- Strict finite JSON (no NaN or Infinity).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.research_cycle_bridge import (
    ResearchCycleBridgeRecord,
    build_research_cycle_bridge,
    validate_bridge_record,
    verify_bridge_checksum,
)


def render_markdown(record: ResearchCycleBridgeRecord) -> str:
    """Render a concise deterministic markdown report of the bridge record."""
    d = record.to_dict()
    prov = d.get("provenance", {})
    rel_ev = d.get("release_evidence") or {}
    egraph = d.get("evidence_graph") or {}
    nodes = egraph.get("nodes", [])
    edges = egraph.get("edges", [])

    lines = [
        "# Research Cycle Evidence Bridge Record",
        "",
        f"- **Record ID:** `{d.get('record_id')}`",
        f"- **Cycle ID:** `{d.get('cycle_id')}`",
        f"- **Status:** `{d.get('status')}`",
        f"- **Data Mode:** `{d.get('data_mode')}`",
        f"- **Evidence Class:** `{d.get('evidence_class')}`",
        f"- **Synthetic Flag:** `{d.get('synthetic')}`",
        f"- **Proxy Flag:** `{d.get('proxy')}`",
        f"- **Empirical Flag:** `{d.get('empirical')}`",
        f"- **Scientific Verdict:** `{d.get('scientific_verdict')}`",
        f"- **Bridge SHA-256:** `{d.get('checksum')}`",
        "",
        "## Provenance",
        f"- **Run ID:** `{prov.get('run_id') or 'unknown'}`",
        f"- **Created At:** `{prov.get('created_at') or 'unknown'}`",
        f"- **Source:** `{prov.get('source') or 'unknown'}`",
        f"- **Git Commit:** `{prov.get('git_commit') or 'unknown'}`",
        "",
        "## Release Evidence Evaluation",
        f"- **Decision:** `{rel_ev.get('decision') or 'not_evaluated'}`",
        f"- **Reason Codes:** {', '.join(f'`{rc}`' for rc in rel_ev.get('reason_codes', [])) or 'none'}",
        "",
        "## Evidence Graph Lineage",
        f"- **Graph ID:** `{egraph.get('graph_id')}`",
        f"- **Total Nodes:** {len(nodes)}",
        f"- **Total Edges:** {len(edges)}",
        "",
        "| Edge Source | Relationship | Target |",
        "| :--- | :---: | :--- |",
    ]
    for e in edges:
        lines.append(f"| `{e.get('source')}` | `{e.get('relationship')}` | `{e.get('target')}` |")

    lines.extend([
        "",
        "## Guardrails & Limitations",
        "- Scientific validity is never inferred from artifact presence.",
        "- Synthetic and proxy records are never promoted to formal empirical evidence.",
        "- Missing metrics stay null (never zero-filled).",
        "- Offline local execution (no live network access).",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile simulation artifacts into canonical research-cycle evidence bridge records.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("--run-dir", type=Path, required=True, help="Path to simulation run directory.")
    parser.add_argument("--plan", type=Path, default=None, help="Optional path to ExperimentPlan.v1 JSON.")
    parser.add_argument("--cycle-id", type=str, default=None, help="Optional research cycle ID.")
    parser.add_argument("--dataset-id", type=str, default=None, help="Optional dataset ID override.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to write bridge output file.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format.")
    parser.add_argument("--verify", action="store_true", default=False, help="Perform strict validation and checksum audit.")

    args = parser.parse_args(argv)

    if not args.run_dir.is_dir():
        print(json.dumps({"error": f"Run directory not found: {args.run_dir}"}), file=sys.stderr)
        return 2

    try:
        bridge = build_research_cycle_bridge(
            run_dir=args.run_dir,
            experiment_plan=args.plan,
            cycle_id=args.cycle_id,
            dataset_id=args.dataset_id,
        )
    except Exception as exc:
        print(json.dumps({"error": f"Failed to build bridge: {exc}"}), file=sys.stderr)
        return 2

    validation_errors = validate_bridge_record(bridge)
    if args.verify and validation_errors:
        print(json.dumps({"error": "Bridge validation failed", "errors": validation_errors}, indent=2), file=sys.stderr)
        return 1

    if args.format == "markdown":
        output_text = render_markdown(bridge)
    else:
        output_text = bridge.to_json()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")

    print(output_text)

    # Return 0 for complete/valid runs; 1 for partial/failed/blocked runs
    return 0 if bridge.status == "COMPLETE" and not validation_errors else 1


if __name__ == "__main__":
    sys.exit(main())
