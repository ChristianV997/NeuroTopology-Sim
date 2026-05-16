"""
Local agent status module (P24).

Reads P22 multi-dataset outputs and current loop state to produce a
comprehensive local_agent_status.json.

CLI:
    python -m tools.local_agents.status \
        --root outputs/btc_icft \
        --local-agent-root outputs/local_agents \
        --out outputs/local_agents/local_agent_status.json

stdlib only. Never executes commands or downloads data.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Optional

from tools.local_agents.state_reader import read_sciencer_state, _load_json


_GUARDRAILS = {
    "executes_real_data": False,
    "downloads_data": False,
    "auto_confirms_peer_review": False,
    "empirical_claims_permitted": False,
    "ontology_quarantined": True,
    "claim_scope_cap": "engineering_runtime",
}


def build_local_agent_status(
    root: str | Path = "outputs/btc_icft",
    local_agent_root: str | Path = "outputs/local_agents",
    vault: str = "obsidian",
) -> dict:
    """
    Build a comprehensive status dict for the local agent system.

    Reads P22 multi-dataset outputs, DS005620 gate/operator outputs,
    language validation, ontology check, loop results, and Obsidian sync.
    """
    root = Path(root)
    lag_root = Path(local_agent_root)

    state = read_sciencer_state(outputs_root=root)

    # DS005620 status
    ds5620_gate = _load_json(root / "ds005620_real_execution_gate" / "ready_for_real_execution.json") or {}
    ds5620_op = _load_json(root / "ds005620_real_artifact_operator" / "real_artifact_next_command.json") or {}
    ds5620_status = {
        "gate_ready": ds5620_gate.get("ready_for_real_execution", False),
        "gate_next_action": ds5620_gate.get("next_action", "not_available"),
        "operator_next_action": ds5620_op.get("next_action", "not_available"),
        "peer_review_confirmed_by_human": False,
    }

    # Multi-dataset P22 status
    mds = state.multi_dataset
    multi_dataset_status = {
        "matrix_present": mds.matrix_present,
        "iteration_present": mds.iteration_present,
        "global_next_action": mds.global_next_action,
        "per_dataset_next_actions": mds.per_dataset_next_actions,
        "iteration_state": mds.iteration_state,
    }

    # Language status
    lang_check = _load_json(root / "ds005620_generated_language_validation.json") or {}
    language_status = {
        "available": bool(lang_check),
        "violations_found": lang_check.get("violations_found", False),
        "passed": not lang_check.get("violations_found", True) if lang_check else None,
    }

    # Ontology status
    ontology_check = _load_json(root / "ontology_claim_language_validation.json") or {}
    ontology_status = {
        "available": bool(ontology_check),
        "violations_found": ontology_check.get("violations_found", False),
        "claim_scope_cap": "engineering_runtime",
        "ontology_quarantined": True,
    }

    # Local agent loop status
    loop_next = _load_json(lag_root / "research_loop_next_action.json") or {}
    if not loop_next:
        loop_next = _load_json(lag_root / "loop_next_action.json") or {}
    loop_plan = _load_json(lag_root / "research_loop_plan.json") or {}
    if not loop_plan:
        loop_plan = _load_json(lag_root / "loop_state.json") or {}
    loop_status = {
        "available": bool(loop_plan),
        "status": loop_plan.get("status", "not_available"),
        "steps_total": loop_plan.get("steps_total", 0),
        "steps_failed": loop_plan.get("steps_failed", 0),
        "next_action": loop_next.get("next_action", "not_available"),
    }

    # Obsidian sync status
    obsidian_result = _load_json(lag_root / "obsidian_sync_result.json") or {}
    obsidian_status = {
        "available": bool(obsidian_result),
        "ok": obsidian_result.get("ok", False),
        "vault": obsidian_result.get("vault", vault),
        "files_written": len(obsidian_result.get("files_written", [])),
        "next_action": obsidian_result.get("next_action", "not_available"),
    }

    # Compute top-level next action and warnings
    next_action = state.global_next_action
    next_command = _next_command_map(next_action)
    manual_required = next_action in (
        "human_peer_review_required",
        "provide_local_root",
        "provide_metadata",
        "provide_raw_eeg",
        "prepare_reviewed_contract_declaration",
    )
    human_review_required = "human_peer_review" in next_action
    blocked_by: list[str] = []
    warnings: list[str] = []

    if language_status.get("violations_found"):
        blocked_by.append("language_violations")
    if not mds.matrix_present:
        warnings.append("P22 multi-dataset matrix not yet built; run: make real-data-source-matrix")

    return {
        "ok": True,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "repo_runtime_available": True,
        "ds005620_status": ds5620_status,
        "multi_dataset_status": multi_dataset_status,
        "language_status": language_status,
        "ontology_status": ontology_status,
        "local_agent_loop_status": loop_status,
        "obsidian_status": obsidian_status,
        "next_action": next_action,
        "next_command": next_command,
        "manual_required": manual_required,
        "human_review_required": human_review_required,
        "blocked_by": blocked_by,
        "warnings": warnings,
        "guardrails": dict(_GUARDRAILS),
    }


def _next_command_map(action: str) -> str:
    mapping = {
        "run_mock_e2e": "make ds005620-e2e-mock",
        "fix_contract_validation": "make validate-ds005620-contracts",
        "fix_language_violations": "make ds005620-generated-language-check",
        "build_multi_dataset_matrix": "make real-data-source-matrix",
        "human_peer_review_required": "Review outputs/btc_icft/ds005620_real_execution_gate/human_peer_review_checklist.md",
        "mock_runtime_complete": "make local-agent-loop-once",
        "no_action_available": "make local-agent-loop-dry-run",
        "dataset_specific_executor_required": "See docs/multi_dataset_real_execution_framework.md",
        "provide_local_root": "Place dataset files in data/<dataset_id>/ directory",
        "provide_metadata": "Place events.tsv in data/DS005620/events.tsv",
    }
    if action in mapping:
        return mapping[action]
    if action.startswith("dataset_operator:") or action.startswith("dataset_gate:"):
        return "make ds005620-real-artifact-plan"
    return ""


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Local agent status (P24)")
    p.add_argument("--root", default="outputs/btc_icft")
    p.add_argument("--local-agent-root", default="outputs/local_agents")
    p.add_argument("--vault", default="obsidian")
    p.add_argument("--out", default="outputs/local_agents/local_agent_status.json")
    args = p.parse_args(argv)

    status = build_local_agent_status(
        root=args.root,
        local_agent_root=args.local_agent_root,
        vault=args.vault,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
