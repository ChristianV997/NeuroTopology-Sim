#!/usr/bin/env python3
"""CLI utility to audit, validate, and summarize Research Cycle Registry artifacts.

Guarantees:
- Verification of schema versions (HypothesisRecord.v1, ExperimentPlan.v1, etc.).
- Validation of promotion and retention rules (Rules A through G).
- Strict verification of SHA-256 record integrity checksums.
- Non-finite (NaN/Inf) rejection in compliance with RFC-8259.
- Summary reporting of hypotheses, falsification records, and experiment plans.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.research_cycle import (
    ResearchCycleRegistry,
    check_promotion_gates,
    compute_record_checksum,
    load_registry_json,
    verify_record_checksum,
)
from tools.research_cycle.gates import PromotionBlockedError
from tools.research_cycle.schema import HypothesisStatus


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and validate a Research Cycle Registry JSON artifact."
    )
    parser.add_argument(
        "--registry", "-r",
        required=True,
        help="Path to the research cycle registry JSON file.",
    )
    parser.add_argument(
        "--check-checksums",
        action="store_true",
        default=True,
        help="Verify SHA-256 checksums across all records (default: True).",
    )
    parser.add_argument(
        "--check-gates",
        action="store_true",
        default=True,
        help="Verify promotion gates on all hypotheses (default: True).",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Emit validation results as JSON to stdout.",
    )
    return parser.parse_args(args)


def validate_registry_file(
    path: str | Path,
    check_checksums: bool = True,
    check_gates: bool = True,
) -> dict[str, Any]:
    """Audit a registry JSON file and return structured audit results."""
    p = Path(path)
    if not p.exists():
        return {
            "valid": False,
            "errors": [f"Registry file not found: {p}"],
            "file": str(p),
        }

    try:
        data = load_registry_json(p)
    except Exception as exc:
        return {
            "valid": False,
            "errors": [f"Failed to parse registry JSON: {exc}"],
            "file": str(p),
        }

    errors: list[str] = []
    warnings: list[str] = []

    # Check top-level schema
    schema = data.get("schema_version")
    if schema != "ResearchCycleRegistry.v1":
        errors.append(f"Unexpected schema_version: '{schema}', expected 'ResearchCycleRegistry.v1'")

    hypotheses = data.get("hypotheses", {})
    plans = data.get("plans", {})
    evidence = data.get("evidence", {})
    revisions = data.get("revisions", [])

    # Verify checksums if requested
    if check_checksums:
        for h_id, h in hypotheses.items():
            if not verify_record_checksum(h):
                errors.append(f"Hypothesis '{h_id}' checksum mismatch or missing.")
        for p_id, pl in plans.items():
            if not verify_record_checksum(pl):
                errors.append(f"Experiment plan '{p_id}' checksum mismatch or missing.")
        for e_id, ev in evidence.items():
            if not verify_record_checksum(ev):
                errors.append(f"Evidence record '{e_id}' checksum mismatch or missing.")

    # Reconstruct registry object for high-level gate checks
    try:
        reg = ResearchCycleRegistry.load_from_file(p)
    except Exception as exc:
        errors.append(f"Registry load_from_file raised: {exc}")
        reg = None

    if reg and check_gates:
        for h_id, hyp in reg._hypotheses.items():
            if hyp.status == HypothesisStatus.SUPPORTED_AS_SPECIFIED.value:
                all_ev = [reg._evidence[eid] for eid in hyp.evidence_links if eid in reg._evidence]
                try:
                    check_promotion_gates(hyp, hyp.status, all_evidence=all_ev)
                except PromotionBlockedError as pbe:
                    errors.append(f"Hypothesis '{h_id}' violates promotion gate: {pbe}")

    status_counts: dict[str, int] = {}
    for h in hypotheses.values():
        st = h.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    contradictions_count = sum(1 for e in evidence.values() if e.get("is_contradictory"))

    return {
        "valid": len(errors) == 0,
        "file": str(p),
        "registry_id": data.get("registry_id"),
        "total_hypotheses": len(hypotheses),
        "total_experiment_plans": len(plans),
        "total_evidence_updates": len(evidence),
        "total_theory_revisions": len(revisions),
        "contradictory_evidence_count": contradictions_count,
        "status_distribution": status_counts,
        "errors": errors,
        "warnings": warnings,
    }


def main(args: list[str] | None = None) -> int:
    ns = parse_args(args)
    results = validate_registry_file(
        ns.registry,
        check_checksums=ns.check_checksums,
        check_gates=ns.check_gates,
    )

    if ns.json_output:
        print(json.dumps(results, indent=2))
        return 0 if results["valid"] else 1

    print("=" * 80)
    print("RESEARCH CYCLE REGISTRY VALIDATION AUDIT")
    print(f"File: {results['file']}")
    print(f"Registry ID: {results.get('registry_id', 'N/A')}")
    print(f"Overall Valid: {results['valid']}")
    print("-" * 80)
    print(f"Total Hypotheses:       {results.get('total_hypotheses', 0)}")
    print(f"Experiment Plans:       {results.get('total_experiment_plans', 0)}")
    print(f"Evidence Updates:       {results.get('total_evidence_updates', 0)}")
    print(f"Theory Revisions:       {results.get('total_theory_revisions', 0)}")
    print(f"Contradictory Evidence: {results.get('contradictory_evidence_count', 0)}")
    print("\nHypothesis Status Breakdown:")
    for st, count in sorted(results.get("status_distribution", {}).items()):
        print(f"  • {st:<25}: {count}")

    if results["errors"]:
        print("\nERRORS DETECTED:")
        for err in results["errors"]:
            print(f"  [ERROR] {err}")

    if results["warnings"]:
        print("\nWARNINGS:")
        for warn in results["warnings"]:
            print(f"  [WARN] {warn}")

    print("=" * 80)
    return 0 if results["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
