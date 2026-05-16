"""
Obsidian vault sync for local agent research loop (P23/P24).

P24 update: writes structured vault folders (00_Dashboard, 01_Datasets, etc.),
adds CLI with --root/--vault/--out, and writes a result JSON.

Backward compatibility: all P23 paths (ScienceR-Dsim/INDEX.md, per-dataset
notes, loop_state.md, matrix.md) are still written in addition to new paths.

stdlib only. Never modifies source artifacts; only writes to vault_root.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_DATASETS = ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]


@dataclass
class ObsidianSyncConfig:
    """Configuration for the Obsidian sync."""
    vault_root: str
    science_outputs_root: str = "outputs/btc_icft"
    loop_outputs_root: str = "outputs/local_agents"
    index_note: str = "ScienceR-Dsim/INDEX.md"
    dataset_folder: str = "ScienceR-Dsim/datasets"
    loop_folder: str = "ScienceR-Dsim/loop"
    matrix_folder: str = "ScienceR-Dsim/matrix"
    tag: str = "sciencer-dsim"


@dataclass
class ObsidianSyncResult:
    """Summary of what the sync wrote."""
    vault_root: str
    notes_written: list = field(default_factory=list)
    notes_skipped: list = field(default_factory=list)
    error: str = ""
    next_action: str = "unknown"
    warnings: list = field(default_factory=list)


def _safe_note_path(vault_root: Path, rel: str) -> Path:
    p = vault_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_json_safe(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _dataset_status_note(dataset_id: str, outputs_root: Path) -> str:
    lines = [
        f"# {dataset_id} — ScienceR-Dsim Status",
        "",
        "```",
        f"dataset_id: {dataset_id}",
        "```",
        "",
    ]

    gate_path = outputs_root / dataset_id / "real_execution_gate" / "ready_for_real_execution.json"
    if dataset_id.upper() == "DS005620":
        gate_path = outputs_root / "ds005620_real_execution_gate" / "ready_for_real_execution.json"
    gate = _read_json_safe(gate_path)
    if gate:
        lines += [
            "## Real Execution Gate",
            "",
            f"- ready_for_real_execution: `{gate.get('ready_for_real_execution', 'unknown')}`",
            f"- next_action: `{gate.get('next_action', 'unknown')}`",
            f"- peer_review_confirmed_by_human: `{gate.get('peer_review_confirmed_by_human', False)}`",
            "",
        ]

    operator_path = outputs_root / dataset_id / "real_artifact_operator" / "real_artifact_build_plan.json"
    if dataset_id.upper() == "DS005620":
        operator_path = outputs_root / "ds005620_real_artifact_operator" / "real_artifact_build_plan.json"
    plan = _read_json_safe(operator_path)
    if plan:
        lines += [
            "## Artifact Operator",
            "",
            f"- next_action: `{plan.get('next_action', 'unknown')}`",
            f"- planner_version: `{plan.get('planner_version', 'unknown')}`",
            "",
        ]

    lines += ["---", "", f"#sciencer-dsim #{dataset_id.lower()}"]
    return "\n".join(lines)


def _loop_state_note(loop_root: Path) -> str:
    # Try both old and new output file names
    state = _read_json_safe(loop_root / "loop_state.json") or {}
    if not state:
        state = _read_json_safe(loop_root / "research_loop_plan.json") or {}
    next_action_d = _read_json_safe(loop_root / "loop_next_action.json") or {}
    if not next_action_d:
        next_action_d = _read_json_safe(loop_root / "research_loop_next_action.json") or {}
    lines = [
        "# Local Agent Loop — State",
        "",
        f"- status: `{state.get('status', 'unknown')}`",
        f"- steps_total: `{state.get('steps_total', 0)}`",
        f"- steps_completed: `{state.get('steps_completed', 0)}`",
        f"- steps_failed: `{state.get('steps_failed', 0)}`",
        f"- next_action: `{next_action_d.get('next_action', 'unknown')}`",
        "",
        "---",
        "",
        "#sciencer-dsim #local-agent",
    ]
    return "\n".join(lines)


def _matrix_note(matrix_root: Path) -> str:
    matrix = _read_json_safe(matrix_root / "dataset_source_matrix.json") or {}
    next_actions = _read_json_safe(matrix_root / "next_actions.json") or {}
    lines = [
        "# Multi-Dataset Matrix",
        "",
        f"- global_next_action: `{next_actions.get('global_next_action', 'unknown')}`",
        "",
        "## Datasets",
        "",
    ]
    for ds_id, entry in matrix.items():
        lines.append(f"- **{ds_id}**: `{entry.get('real_execution_supported', False)}`")
    lines += ["", "---", "", "#sciencer-dsim #matrix"]
    return "\n".join(lines)


def _index_note(config: ObsidianSyncConfig, datasets: list) -> str:
    lines = [
        "# ScienceR-Dsim — Obsidian Index",
        "",
        "Auto-generated by the local agent research loop (P23/P24).",
        "Do not edit manually — re-sync to update.",
        "",
        "## Datasets",
        "",
    ]
    for ds in datasets:
        lines.append(f"- [[{config.dataset_folder}/{ds}|{ds}]]")
    lines += [
        "",
        "## Loop State",
        "",
        f"- [[{config.loop_folder}/loop_state|Loop State]]",
        "",
        "## Matrix",
        "",
        f"- [[{config.matrix_folder}/matrix|Multi-Dataset Matrix]]",
        "",
        "---",
        "",
        "#sciencer-dsim",
    ]
    return "\n".join(lines)


def _dashboard_status_note(outputs_root: Path, loop_root: Path) -> str:
    next_action = "unknown"
    next_actions = _read_json_safe(outputs_root / "multi_dataset_real_execution" / "next_actions.json") or {}
    if next_actions:
        next_action = next_actions.get("global_next_action", "unknown")
    loop_next = _read_json_safe(loop_root / "research_loop_next_action.json") or {}
    if not loop_next:
        loop_next = _read_json_safe(loop_root / "loop_next_action.json") or {}
    if loop_next:
        next_action = loop_next.get("next_action", next_action)

    lines = [
        "# ScienceR-Dsim — Status Dashboard",
        "",
        "Auto-generated. Do not edit.",
        "",
        f"**next_action**: `{next_action}`",
        "",
        "## Guardrails",
        "",
        "- empirical_claims_permitted: `false`",
        "- ontology_quarantined: `true`",
        "- claim_scope_cap: `engineering_runtime`",
        "- auto_pushes_git: `false`",
        "- auto_merges_pr: `false`",
        "",
        "---",
        "",
        "#sciencer-dsim #dashboard",
    ]
    return "\n".join(lines)


def _open_tasks_note(outputs_root: Path, loop_root: Path) -> str:
    next_action = "unknown"
    next_command = ""
    loop_next = _read_json_safe(loop_root / "research_loop_next_action.json") or {}
    if not loop_next:
        loop_next = _read_json_safe(loop_root / "loop_next_action.json") or {}
    if loop_next:
        next_action = loop_next.get("next_action", "unknown")
        next_command = loop_next.get("next_command", "")

    lines = [
        "# Open Tasks",
        "",
        "Auto-generated from loop next action.",
        "",
        f"- [ ] **{next_action}**",
    ]
    if next_command:
        lines += [f"  - Command: `{next_command}`"]
    lines += [
        "",
        "Human review is always required before real-data execution.",
        "",
        "---",
        "",
        "#sciencer-dsim #tasks",
    ]
    return "\n".join(lines)


def _agent_roster_note() -> str:
    lines = [
        "# Agent Roster",
        "",
        "| Role | Auto-run? | Needs human review? |",
        "|---|---|---|",
        "| mock_runner | yes | No |",
        "| validator | yes | No |",
        "| artifact_planner | yes | No |",
        "| gate_inspector | yes | Yes |",
        "| obsidian_syncer | yes | No |",
        "| matrix_builder | yes | No |",
        "| real_data_executor | **no** | **Yes** |",
        "| safety_watcher | yes | No |",
        "",
        "`real_data_executor` is never auto-run.",
        "",
        "---",
        "",
        "#sciencer-dsim #agents",
    ]
    return "\n".join(lines)


def _iteration_log_note(outputs_root: Path) -> str:
    iter_state = _read_json_safe(
        outputs_root / "multi_dataset_autonomous_iteration" / "iteration_state.json"
    ) or {}
    lines = [
        "# Autonomous Iteration Log",
        "",
        f"- status: `{iter_state.get('status', 'not_available')}`",
        f"- datasets_total: `{iter_state.get('datasets_total', 0)}`",
        f"- steps_completed: `{iter_state.get('steps_completed', 0)}`",
        f"- steps_failed: `{iter_state.get('steps_failed', 0)}`",
        "",
        "---",
        "",
        "#sciencer-dsim #iteration",
    ]
    return "\n".join(lines)


def _evidence_ledger_note(outputs_root: Path) -> str:
    lines = [
        "# Evidence Ledger",
        "",
        "**Empirical claims are never permitted from mock E2E or local data presence alone.**",
        "",
        "Controls required before any empirical readiness:",
        "- nulls.json",
        "- ablations.json",
        "- leakage_report.json",
        "- artifact_report.json",
        "",
        "Current status: `blocked_no_real_execution`",
        "empirical_claims_permitted: `false`",
        "",
        "---",
        "",
        "#sciencer-dsim #evidence",
    ]
    return "\n".join(lines)


def _ontology_scope_note(outputs_root: Path) -> str:
    lines = [
        "# Claim Scope Matrix",
        "",
        "All datasets:",
        "- claim_scope_cap: `engineering_runtime`",
        "- promotion_state: `engineering_validated`",
        "- ontology_quarantined: `true`",
        "",
        "Ontology promotion requires real execution + controls + independent mechanism evidence + peer review.",
        "None of these are automated by this framework.",
        "",
        "---",
        "",
        "#sciencer-dsim #ontology",
    ]
    return "\n".join(lines)


def _runs_jsonl_entry(loop_root: Path) -> str:
    """Return a single JSONL entry for the agent memory log."""
    import datetime
    loop_next = _read_json_safe(loop_root / "research_loop_next_action.json") or {}
    if not loop_next:
        loop_next = _read_json_safe(loop_root / "loop_next_action.json") or {}
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "next_action": loop_next.get("next_action", "unknown"),
        "source": "obsidian_sync",
    }
    return json.dumps(entry)


def sync_obsidian(
    outputs_root: str | Path,
    vault_root: str | Path,
    config: Optional[ObsidianSyncConfig] = None,
    dataset_ids: Optional[list] = None,
) -> ObsidianSyncResult:
    """
    Mirror ScienceR-Dsim outputs into an Obsidian vault.

    P24: writes both legacy paths (ScienceR-Dsim/*) and new structured paths
    (00_Dashboard/, 01_Datasets/, etc.). Only writes to vault_root.
    Never modifies source artifacts.
    """
    vault = Path(vault_root)
    outputs = Path(outputs_root)

    if config is None:
        config = ObsidianSyncConfig(vault_root=str(vault))

    loop_root = Path(config.loop_outputs_root)
    result = ObsidianSyncResult(vault_root=str(vault))

    if dataset_ids is None:
        dataset_ids = list(_DATASETS)

    # ------------------------------------------------------------------ #
    # Legacy paths (P23 backward compat)
    # ------------------------------------------------------------------ #
    for ds_id in dataset_ids:
        note_content = _dataset_status_note(ds_id, outputs)
        note_path = _safe_note_path(vault, f"{config.dataset_folder}/{ds_id}.md")
        note_path.write_text(note_content, encoding="utf-8")
        result.notes_written.append(str(note_path))

    loop_note = _loop_state_note(loop_root)
    loop_path = _safe_note_path(vault, f"{config.loop_folder}/loop_state.md")
    loop_path.write_text(loop_note, encoding="utf-8")
    result.notes_written.append(str(loop_path))

    matrix_root = outputs / "multi_dataset_real_execution"
    matrix_note = _matrix_note(matrix_root)
    matrix_path = _safe_note_path(vault, f"{config.matrix_folder}/matrix.md")
    matrix_path.write_text(matrix_note, encoding="utf-8")
    result.notes_written.append(str(matrix_path))

    index = _index_note(config, dataset_ids)
    index_path = _safe_note_path(vault, config.index_note)
    index_path.write_text(index, encoding="utf-8")
    result.notes_written.append(str(index_path))

    # ------------------------------------------------------------------ #
    # P24 structured vault paths
    # ------------------------------------------------------------------ #

    # 00_Dashboard
    dash_status = _dashboard_status_note(outputs, loop_root)
    p = _safe_note_path(vault, "00_Dashboard/ScienceR-Dsim_Status.md")
    p.write_text(dash_status, encoding="utf-8")
    result.notes_written.append(str(p))

    open_tasks = _open_tasks_note(outputs, loop_root)
    p = _safe_note_path(vault, "00_Dashboard/Open_Tasks.md")
    p.write_text(open_tasks, encoding="utf-8")
    result.notes_written.append(str(p))

    roster = _agent_roster_note()
    p = _safe_note_path(vault, "00_Dashboard/Agent_Roster.md")
    p.write_text(roster, encoding="utf-8")
    result.notes_written.append(str(p))

    # 01_Datasets — per-dataset (reuse content)
    for ds_id in dataset_ids:
        note_content = _dataset_status_note(ds_id, outputs)
        p = _safe_note_path(vault, f"01_Datasets/{ds_id}.md")
        p.write_text(note_content, encoding="utf-8")
        result.notes_written.append(str(p))

    multi_matrix = _matrix_note(matrix_root)
    p = _safe_note_path(vault, "01_Datasets/Multi_Dataset_Matrix.md")
    p.write_text(multi_matrix, encoding="utf-8")
    result.notes_written.append(str(p))

    # 02_Runtime
    iter_log = _iteration_log_note(outputs)
    p = _safe_note_path(vault, "02_Runtime/Autonomous_Iteration_Log.md")
    p.write_text(iter_log, encoding="utf-8")
    result.notes_written.append(str(p))

    # 03_Evidence
    evidence = _evidence_ledger_note(outputs)
    p = _safe_note_path(vault, "03_Evidence/Evidence_Ledger.md")
    p.write_text(evidence, encoding="utf-8")
    result.notes_written.append(str(p))

    # 04_Ontology
    ontology = _ontology_scope_note(outputs)
    p = _safe_note_path(vault, "04_Ontology/Claim_Scope_Matrix.md")
    p.write_text(ontology, encoding="utf-8")
    result.notes_written.append(str(p))

    # 99_Agent_Memory — append a JSONL run entry
    mem_path = _safe_note_path(vault, "99_Agent_Memory/runs.jsonl")
    entry = _runs_jsonl_entry(loop_root)
    with mem_path.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")
    result.notes_written.append(str(mem_path))

    # Determine next_action for result
    loop_next = _read_json_safe(loop_root / "research_loop_next_action.json") or {}
    if not loop_next:
        loop_next = _read_json_safe(loop_root / "loop_next_action.json") or {}
    result.next_action = loop_next.get("next_action", "unknown")

    return result


# ---------------------------------------------------------------------------
# P24 CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Obsidian sync CLI (P24)")
    p.add_argument("--root", default="outputs/btc_icft", help="ScienceR-Dsim outputs root")
    p.add_argument("--vault", default="obsidian", help="Obsidian vault root path")
    p.add_argument("--out", default=None, help="Write sync result JSON to this path")
    args = p.parse_args(argv)

    result = sync_obsidian(
        outputs_root=args.root,
        vault_root=args.vault,
    )

    result_dict = {
        "ok": not bool(result.error),
        "vault": result.vault_root,
        "files_written": result.notes_written,
        "missing_sources": result.notes_skipped,
        "next_action": result.next_action,
        "warnings": ([result.error] if result.error else []) + result.warnings,
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result_dict, indent=2), encoding="utf-8")

    print(json.dumps(result_dict, indent=2))
    return 0 if result_dict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
