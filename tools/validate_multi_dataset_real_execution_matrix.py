#!/usr/bin/env python3
"""Validate the P22 multi-dataset real-execution matrix outputs.

Checks:
- All required matrix output files exist.
- All six planned datasets are present.
- No dataset claims empirical readiness without real execution + controls.
- No dataset claims ontology promotion.
- No generated command downloads data or auto-runs real execution.
- DS005620 is marked as dataset-specific-supported.
- Non-DS005620 unsupported pieces are honestly blocked, not marked ready.
- operator_report.md contains no banned phrases.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_FILES = [
    "dataset_source_matrix.json",
    "local_data_availability_matrix.json",
    "label_contract_readiness_matrix.json",
    "eeg_reader_readiness_matrix.json",
    "artifact_operator_matrix.json",
    "real_execution_gate_matrix.json",
    "autonomous_iteration_matrix.json",
    "empirical_readiness_matrix.json",
    "ontology_scope_matrix.json",
    "next_actions.json",
    "operator_report.md",
]

REQUIRED_DATASETS = [
    "DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA",
]

BANNED_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]

FORBIDDEN_COMMAND_SUBSTRINGS = [
    "dandi download",
    "openneuro download",
    "aws s3 cp",
    " wget ",
    " curl ",
    "&& wget",
    "&& curl",
]


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def validate(root: Path) -> tuple:
    """Return (passed, errors, warnings)."""
    errors: list = []
    warnings: list = []

    # 1. Required files exist
    for name in REQUIRED_FILES:
        if not (root / name).exists():
            errors.append(f"missing_output: {name}")
    if errors:
        return False, errors, warnings

    # 2. All six datasets present
    src = _load(root / "dataset_source_matrix.json")
    datasets_present = set(src.get("datasets", {}).keys())
    for ds in REQUIRED_DATASETS:
        if ds not in datasets_present:
            errors.append(f"missing_dataset_in_matrix: {ds}")

    # 3. No empirical readiness without real execution + controls
    emp = _load(root / "empirical_readiness_matrix.json")
    for ds, status in emp.get("datasets", {}).items():
        if status.get("empirical_claims_permitted") is True:
            errors.append(f"empirical_claims_permitted_true: {ds}")
        if status.get("readiness_status") == "ready_with_human_review":
            # Verify all controls present and real_execution_completed True
            if not status.get("real_execution_completed"):
                errors.append(
                    f"empirical_ready_without_real_execution: {ds}"
                )
            if not status.get("all_controls_present"):
                errors.append(f"empirical_ready_without_controls: {ds}")

    # 4. Ontology scope is quarantined everywhere
    ont = _load(root / "ontology_scope_matrix.json")
    for ds, status in ont.get("datasets", {}).items():
        if not status.get("ontology_quarantined", True):
            errors.append(f"ontology_not_quarantined: {ds}")
        scope = status.get("claim_scope_cap", "")
        if scope != "engineering_runtime":
            errors.append(
                f"ontology_scope_not_engineering_runtime: {ds} ({scope})"
            )
        prom = status.get("promotion_state", "")
        if prom != "engineering_validated":
            errors.append(
                f"ontology_promotion_state_unexpected: {ds} ({prom})"
            )

    # 5. Commands do not download data or auto-run real execution
    na = _load(root / "next_actions.json")
    for ds, action in na.get("per_dataset", {}).items():
        cmd = str(action.get("next_command", "")).lower()
        for forbidden in FORBIDDEN_COMMAND_SUBSTRINGS:
            if forbidden in cmd:
                errors.append(f"forbidden_command_substring in {ds}: {forbidden!r}")
        if action.get("executes_real_data") is True:
            errors.append(f"next_action_executes_real_data: {ds}")
        if action.get("downloads_data") is True:
            errors.append(f"next_action_downloads_data: {ds}")
        if action.get("safe_to_auto_run") is True:
            # This is OK in principle for inspect-only actions, but never for real data
            if action.get("executes_real_data") or action.get("downloads_data"):
                errors.append(f"safe_to_auto_run_with_real_data: {ds}")

    # 6. DS005620 is specific-supported
    gate = _load(root / "real_execution_gate_matrix.json")
    ds5620 = gate.get("datasets", {}).get("DS005620", {})
    if not ds5620.get("dataset_specific_executor_available"):
        errors.append(
            "DS005620_not_marked_specific_supported_in_gate"
        )

    # 7. Non-DS005620 unsupported pieces are honestly blocked
    for ds, g in gate.get("datasets", {}).items():
        if ds == "DS005620":
            continue
        if g.get("dataset_specific_executor_available") is True:
            errors.append(
                f"non_ds005620_executor_claimed_available: {ds}"
            )
        # gate should not be ready if executor unavailable
        if (
            g.get("ready_for_real_execution") is True
            and not g.get("dataset_specific_executor_available")
        ):
            errors.append(
                f"gate_ready_without_executor: {ds}"
            )
        # peer_review hardcoded false
        if g.get("peer_review_confirmed_by_human") is True:
            errors.append(f"peer_review_auto_confirmed: {ds}")
        if g.get("can_use_execute_flag") is True:
            errors.append(f"can_use_execute_flag_true: {ds}")

    # 8. Report has no banned phrases
    report = (root / "operator_report.md").read_text(encoding="utf-8").lower()
    for phrase in BANNED_PHRASES:
        if phrase in report:
            errors.append(f"banned_phrase_in_report: {phrase!r}")

    # 9. real_execution_command for non-DS005620 should be commented out (not runnable)
    for ds, g in gate.get("datasets", {}).items():
        if ds == "DS005620":
            continue
        cmd = str(g.get("real_execution_command", ""))
        # Either empty/commented or contains "NO MANUAL REAL COMMAND AVAILABLE"
        if cmd and not cmd.strip().startswith("#"):
            errors.append(f"non_ds005620_runnable_real_command: {ds}")

    return (len(errors) == 0), errors, warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate P22 multi-dataset real-execution matrix outputs."
    )
    ap.add_argument(
        "--root",
        required=True,
        help="Path to multi-dataset real-execution outputs directory",
    )
    ap.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write JSON validation summary",
    )
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: matrix root does not exist: {root}", file=sys.stderr)
        return 1

    passed, errors, warnings = validate(root)

    summary = {
        "root": str(root),
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
    }
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )

    if passed:
        print("PASS multi-dataset real-execution matrix validation")
        return 0
    else:
        print("FAIL multi-dataset real-execution matrix validation:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
