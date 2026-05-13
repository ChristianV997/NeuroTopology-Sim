"""
P18.2 Science Runtime Inspector CLI.

Loads the latest P18.1 execution artifacts, builds the runtime state,
emits a JSONL event, writes a snapshot, and produces a human-readable report.

Usage:
  python -m sciencer_d.btc_icft.pipelines.inspect_science_runtime \\
    --dataset-id DS005620 \\
    --artifact-root outputs/btc_icft/ds005620_real_benchmark_execution_mock \\
    --out outputs/btc_icft/science_runtime_inspection
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sciencer_d.btc_icft.runtime.events import build_event, envelope_to_dict
from sciencer_d.btc_icft.runtime.event_log import append_envelope
from sciencer_d.btc_icft.runtime.state import build_runtime_state, build_runtime_snapshot
from sciencer_d.btc_icft.runtime.task_inventory import build_default_science_task_registry
from sciencer_d.btc_icft.runtime.snapshots import ScienceRuntimeSnapshotStore


_SOURCE = "inspect_science_runtime"


def _build_report(state_dict: dict, task_inv: dict, snapshot_id: str, dataset_id: str) -> str:
    lines = [
        "# Science Runtime Inspection Report",
        "",
        f"**Dataset:** {dataset_id}",
        f"**Snapshot ID:** {snapshot_id}",
        f"**Benchmark completed:** {state_dict.get('benchmark_completed')}",
        f"**Mock E2E run:** {state_dict.get('mock_e2e_run')}",
        f"**Next action:** `{state_dict.get('next_action')}`",
        "",
        "## Stage Outcomes",
        "",
        f"- P12 succeeded: {state_dict.get('p12_succeeded')}",
        f"- P13 succeeded: {state_dict.get('p13_succeeded')}",
        f"- P11 succeeded: {state_dict.get('p11_succeeded')}",
        "",
        "## Artifact Inventory",
        "",
        f"- Artifact manifest: {state_dict.get('artifact_manifest_exists')}",
        f"- Evidence packet: {state_dict.get('evidence_packet_exists')}",
        f"- Paper skeleton: {state_dict.get('paper_skeleton_exists')}",
        "",
        "## Blockers",
        "",
    ]
    blockers = state_dict.get("blockers", [])
    if blockers:
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("_(none)_")

    lines += [
        "",
        f"## Task Registry ({len(task_inv.get('tasks', []))} tasks)",
        "",
        "_(See task_inventory.json for full details.)_",
        "",
        "---",
        "",
        "_P18.2 runtime inspection — no pipeline stages executed._",
    ]
    return "\n".join(lines)


def _build_next_actions(state_dict: dict) -> dict:
    next_action = state_dict.get("next_action", "unknown")
    chain = [
        "run_mock_e2e",
        "build_artifact_manifest",
        "export_evidence_packet",
        "generate_paper_skeleton",
        "ready_for_real_local_preflight_or_review",
    ]
    try:
        current_idx = chain.index(next_action)
    except ValueError:
        current_idx = -1
    return {
        "current_next_action": next_action,
        "chain": chain,
        "remaining": chain[current_idx:] if current_idx >= 0 else [],
        "completed": chain[:current_idx] if current_idx >= 0 else [],
    }


def _write_outputs(
    out_dir: str,
    state_dict: dict,
    task_inv: dict,
    snapshot: dict,
    event_log_path: str,
    dataset_id: str,
) -> dict[str, str]:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)

    state_path = p / "runtime_state.json"
    state_path.write_text(json.dumps(state_dict, indent=2, default=str), encoding="utf-8")

    # Write task inventory as both canonical and alias name required by spec
    inv_path = p / "task_inventory.json"
    inv_path.write_text(json.dumps(task_inv, indent=2, default=str), encoding="utf-8")
    inv_alias_path = p / "runtime_inventory.json"
    inv_alias_path.write_text(json.dumps(task_inv, indent=2, default=str), encoding="utf-8")

    snap_path = p / "runtime_snapshot.json"
    snap_path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")

    next_actions = _build_next_actions(state_dict)
    next_actions_path = p / "runtime_next_actions.json"
    next_actions_path.write_text(json.dumps(next_actions, indent=2, default=str), encoding="utf-8")

    report_text = _build_report(state_dict, task_inv, snapshot.get("snapshot_id", ""), dataset_id)
    # Write report as both names (runtime_report.md is canonical; report.md required by spec)
    report_path = p / "runtime_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    report_alias_path = p / "report.md"
    report_alias_path.write_text(report_text, encoding="utf-8")

    return {
        "runtime_state.json": str(state_path),
        "task_inventory.json": str(inv_path),
        "runtime_inventory.json": str(inv_alias_path),
        "runtime_snapshot.json": str(snap_path),
        "runtime_next_actions.json": str(next_actions_path),
        "runtime_event_log.jsonl": event_log_path,
        "runtime_report.md": str(report_path),
        "report.md": str(report_alias_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect science runtime state (P18.2)")
    parser.add_argument("--dataset-id", default="DS005620")
    parser.add_argument("--artifact-root", default="outputs/btc_icft/ds005620_real_benchmark_execution_mock")
    parser.add_argument("--manifest-dir", default=None)
    parser.add_argument("--evidence-dir", default=None)
    parser.add_argument("--skeleton-dir", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    state = build_runtime_state(
        dataset_id=args.dataset_id,
        artifact_root=args.artifact_root,
        manifest_dir=args.manifest_dir,
        evidence_dir=args.evidence_dir,
        skeleton_dir=args.skeleton_dir,
    )

    snapshot = build_runtime_snapshot(state)
    registry = build_default_science_task_registry()

    state_dict = {
        "dataset_id": state.dataset_id,
        "artifact_root": state.artifact_root,
        "execution_json_path": state.execution_json_path,
        "benchmark_completed": state.benchmark_completed,
        "p12_succeeded": state.p12_succeeded,
        "p13_succeeded": state.p13_succeeded,
        "p11_succeeded": state.p11_succeeded,
        "mock_e2e_run": state.mock_e2e_run,
        "artifact_manifest_exists": state.artifact_manifest_exists,
        "evidence_packet_exists": state.evidence_packet_exists,
        "paper_skeleton_exists": state.paper_skeleton_exists,
        "next_action": state.next_action,
        "blockers": state.blockers,
        "warnings": state.warnings,
        "last_updated": state.last_updated,
        "predictive_metrics_available": state.predictive_metrics_available,
        "real_local_preflight_ready": state.real_local_preflight_ready,
    }

    task_inv = registry.to_dict()

    snap_dict = asdict(snapshot)

    event_log_path = str(Path(args.out) / "runtime_event_log.jsonl")
    envelope = build_event(
        "runtime_inspected",
        {
            "dataset_id": args.dataset_id,
            "benchmark_completed": state.benchmark_completed,
            "next_action": state.next_action,
            "snapshot_id": snapshot.snapshot_id,
        },
        source=_SOURCE,
    )
    append_envelope(event_log_path, envelope)

    artifacts = _write_outputs(
        out_dir=args.out,
        state_dict=state_dict,
        task_inv=task_inv,
        snapshot=snap_dict,
        event_log_path=event_log_path,
        dataset_id=args.dataset_id,
    )

    print(f"benchmark_completed: {state.benchmark_completed}")
    print(f"next_action: {state.next_action}")
    print(f"snapshot_id: {snapshot.snapshot_id}")
    print(f"artifacts written to: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
