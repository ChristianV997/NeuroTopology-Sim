#!/usr/bin/env python3
"""CLI utility to validate research cycle contracts and perform adapter transformations.

Enforces non-negotiable verification gates:
- Explicit falsification criteria
- Explicit null predictions
- Identifiable source provenance
- Non-promoted status without human review
- Permitted topological and neurodynamic feature families
- Tamper-evident SHA-256 checksums

Usage:
    python scripts/validate_research_cycle_contracts.py --input <path/to/contract.json> [--check-gates]
    python scripts/validate_research_cycle_contracts.py --input <path> --convert-to awareness_node --output out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure local repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.research_cycle_contracts.adapters import (
    awareness_node_to_hypothesis,
    hypothesis_to_awareness_node,
    ledger_row_to_evidence,
    plan_and_evidence_to_ledger_row,
)
from tools.research_cycle_contracts.models import (
    AwarenessHypothesisNodeV1,
    EvidenceUpdateV1,
    ExperimentLedgerRowV1,
    ExperimentPlanV1,
    HypothesisRecordV1,
)
from tools.research_cycle_contracts.rejection import (
    ContractCompatibilityError,
    ContractRejectionError,
    validate_evidence_contract,
    validate_hypothesis_contract,
    validate_ledger_row_contract,
)
from tools.research_cycle_contracts.serialization import (
    load_contract_json,
    save_contract_json,
    to_canonical_json,
    verify_checksum,
)


def infer_contract_type(data: dict[str, Any]) -> str:
    """Infer the contract schema type from JSON object fields."""
    ver = data.get("schema_version", "")
    if "HypothesisRecord" in ver or ("hypothesis_id" in data and "falsification_criterion" in data):
        return "hypothesis"
    if "AwarenessHypothesisNode" in ver or ("node_id" in data and "falsification_criteria" in data):
        return "awareness_node"
    if "ExperimentLedgerRow" in ver or ("row_id" in data and "reviewer_signoff" in data):
        return "ledger_row"
    if "EvidenceUpdate" in ver or ("evidence_id" in data and "is_out_of_sample" in data):
        return "evidence"
    if "ExperimentPlan" in ver or ("plan_id" in data and "target_sample_size" in data):
        return "plan"
    if "AwarenessStudioCycleInput" in ver or ("cycle_id" in data and "nodes" in data):
        return "cycle_input"
    return "unknown"


def validate_file(
    path: Path,
    expected_type: str = "auto",
    check_gates: bool = True,
    verify_integrity: bool = True,
) -> dict[str, Any]:
    """Validate a single contract file."""
    result: dict[str, Any] = {
        "file": str(path),
        "valid": False,
        "contract_type": "unknown",
        "errors": [],
        "warnings": [],
        "notices": [],
    }

    try:
        data = load_contract_json(path, verify_integrity=verify_integrity)
    except Exception as exc:
        result["errors"].append(f"Failed to load or verify integrity: {exc}")
        return result

    inferred = infer_contract_type(data)
    result["contract_type"] = inferred

    if expected_type != "auto" and inferred != expected_type:
        result["errors"].append(
            f"Contract type mismatch: expected '{expected_type}', inferred '{inferred}'"
        )
        return result

    try:
        if inferred == "hypothesis":
            hypo = HypothesisRecordV1(**data)
            if check_gates:
                notices = validate_hypothesis_contract(hypo)
                result["notices"].extend(notices)
            result["valid"] = True

        elif inferred == "awareness_node":
            node = AwarenessHypothesisNodeV1(**data)
            # Round-trip validate to hypothesis
            hypo, warnings = awareness_node_to_hypothesis(node, validate=check_gates)
            result["warnings"].extend([w.to_dict() for w in warnings])
            result["valid"] = True

        elif inferred == "evidence":
            ev = EvidenceUpdateV1(**data)
            if check_gates:
                notices = validate_evidence_contract(ev)
                result["notices"].extend(notices)
            result["valid"] = True

        elif inferred == "ledger_row":
            row = ExperimentLedgerRowV1(**data)
            if check_gates:
                notices = validate_ledger_row_contract(row)
                result["notices"].extend(notices)
            result["valid"] = True

        elif inferred == "plan":
            _ = ExperimentPlanV1(**data)
            result["valid"] = True

        elif inferred == "cycle_input":
            for n_dict in data.get("nodes", []):
                n = AwarenessHypothesisNodeV1(**n_dict)
                hypo, warnings = awareness_node_to_hypothesis(n, validate=check_gates)
                result["warnings"].extend([w.to_dict() for w in warnings])
            result["valid"] = True

        else:
            result["errors"].append(f"Unrecognized contract schema for {path}")

    except ContractRejectionError as exc:
        result["errors"].append(f"Gate rejection: [{exc.reason_code}] {exc.message}")
    except Exception as exc:
        result["errors"].append(f"Validation exception: {type(exc).__name__}: {exc}")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate research cycle contracts and perform schema conversions."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to a contract JSON file or directory of contract files.",
    )
    parser.add_argument(
        "--contract-type",
        choices=["auto", "hypothesis", "awareness_node", "evidence", "plan", "ledger_row", "cycle_input"],
        default="auto",
        help="Expected contract type (default: auto)",
    )
    parser.add_argument(
        "--check-gates",
        action="store_true",
        default=True,
        help="Enforce non-negotiable verification gates (default: True)",
    )
    parser.add_argument(
        "--skip-gates",
        dest="check_gates",
        action="store_false",
        help="Skip strict gate validation.",
    )
    parser.add_argument(
        "--skip-integrity",
        action="store_true",
        help="Skip SHA-256 integrity verification against embedded checksum.",
    )
    parser.add_argument(
        "--convert-to",
        choices=["awareness_node", "hypothesis", "ledger_row"],
        help="Convert the input contract to another format and write output.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path when --convert-to is used.",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output validation report as structured JSON.",
    )

    args = parser.parse_args(argv)
    target_path = Path(args.input)

    if not target_path.exists():
        print(f"ERROR: Input path does not exist: {target_path}", file=sys.stderr)
        return 2

    files_to_check: list[Path] = []
    if target_path.is_dir():
        files_to_check = sorted(target_path.glob("**/*.json"))
    else:
        files_to_check = [target_path]

    results = []
    overall_valid = True

    for p in files_to_check:
        res = validate_file(
            p,
            expected_type=args.contract_type,
            check_gates=args.check_gates,
            verify_integrity=not args.skip_integrity,
        )
        if not res["valid"]:
            overall_valid = False
        results.append(res)

    # Conversion handling if requested on a single file
    if args.convert_to and len(files_to_check) == 1 and overall_valid:
        in_file = files_to_check[0]
        data = load_contract_json(in_file, verify_integrity=not args.skip_integrity)
        inferred = infer_contract_type(data)

        converted_obj = None
        if args.convert_to == "awareness_node" and inferred == "hypothesis":
            converted_obj, _ = hypothesis_to_awareness_node(data, validate=args.check_gates)
        elif args.convert_to == "hypothesis" and inferred == "awareness_node":
            converted_obj, _ = awareness_node_to_hypothesis(data, validate=args.check_gates)
        else:
            print(
                f"ERROR: Conversion from '{inferred}' to '{args.convert_to}' not directly supported.",
                file=sys.stderr,
            )
            return 1

        if args.output:
            out_path = Path(args.output)
            save_contract_json(converted_obj, out_path)
            print(f"Successfully converted and saved to {out_path}")
        else:
            print(to_canonical_json(converted_obj))

    if args.json_output:
        print(json.dumps({"overall_valid": overall_valid, "results": results}, indent=2))
    else:
        for r in results:
            status_str = "PASS" if r["valid"] else "FAIL"
            print(f"[{status_str}] {r['file']} (Type: {r['contract_type']})")
            for notice in r["notices"]:
                print(f"       Notice: {notice}")
            for warning in r["warnings"]:
                print(f"       Warning: {warning}")
            for error in r["errors"]:
                print(f"       ERROR: {error}")

    return 0 if overall_valid else 1


if __name__ == "__main__":
    sys.exit(main())
