"""
Generic real/local execution gate (P22).

Generalizes P18.3 behavior to all datasets. Inspects prerequisites and
emits a gate result. Never auto-runs real execution. Hardcodes peer-review
and execute-flag confirmations to False.

stdlib only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sciencer_d.btc_icft.runtime.multi_dataset_paths import (
    DatasetProfile,
    DatasetRealPathConfig,
    build_dataset_path_config,
)


@dataclass
class GenericExecutionGateResult:
    dataset_id: str
    ready_for_real_execution: bool
    ready_for_p18_execute: bool
    reviewed_contract_static_gate_passed: bool
    all_required_artifacts_present: bool
    dataset_specific_executor_available: bool
    peer_review_required: bool
    peer_review_confirmed_by_human: bool
    can_use_execute_flag: bool
    can_use_peer_reviewed_contract_confirmed_flag: bool
    blockers: list
    warnings: list
    next_action: str
    next_command: str
    real_execution_command: str
    generated_at: str


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contract_static_checks(
    contract_path: str,
    dataset_id: str,
) -> tuple:
    """Return (passed, blockers, warnings) for static contract checks."""
    blockers = []
    warnings = []
    p = Path(contract_path)
    if not p.exists():
        return False, ["contract_missing"], []
    try:
        contract = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"contract_unparseable: {exc}"], []

    # dataset_id must match (case-insensitive)
    cid = str(contract.get("dataset_id", "")).strip()
    if cid.upper() != dataset_id.upper():
        blockers.append(f"dataset_id_mismatch: {cid!r} != {dataset_id!r}")

    # contract_status must be active_reviewed_external_contract
    status = str(contract.get("contract_status", "")).strip()
    if status != "active_reviewed_external_contract":
        blockers.append(f"contract_status_not_active_reviewed: {status!r}")

    # explicit_label_column must be present and non-empty
    elc = contract.get("explicit_label_column")
    if not elc:
        blockers.append("explicit_label_column_missing_or_empty")

    pos = contract.get("positive_values") or []
    neg = contract.get("negative_values") or []
    if not pos:
        blockers.append("positive_values_missing_or_empty")
    if not neg:
        blockers.append("negative_values_missing_or_empty")
    if pos and neg and set(pos) & set(neg):
        blockers.append("positive_negative_overlap")

    # join_keys must include canonical keys
    required_keys = {
        "dataset_id", "row_id", "source_file", "window_id",
        "window_start_s", "window_end_s", "sample_start", "sample_end",
    }
    join_keys = set(contract.get("join_keys", []) or [])
    missing_keys = required_keys - join_keys
    if missing_keys:
        blockers.append(f"missing_join_keys: {sorted(missing_keys)}")

    # shortcut indicators must NOT be true
    shortcut_flags = [
        "label_inference_enabled", "targets_fabricated",
        "filename_derived_labels", "topology_derived_labels",
        "artifact_derived_labels", "automatic_activation",
    ]
    for flag in shortcut_flags:
        if contract.get(flag) is True:
            blockers.append(f"shortcut_flag_set: {flag}")

    return (len(blockers) == 0), blockers, warnings


def build_generic_real_execution_gate(
    profile: DatasetProfile,
) -> GenericExecutionGateResult:
    cfg = build_dataset_path_config(profile)
    ds = profile.dataset_id

    blockers: list = []
    warnings: list = []

    # Inspect required artifacts
    required = {
        "metadata": cfg.metadata_path,
        "reviewed_contract": cfg.reviewed_contract_materialized,
        "signal_blocks_root": cfg.signal_blocks_path,
        "level_m_csv": cfg.level_m_csv_path,
        "level_t_csv": cfg.level_t_csv_path,
    }
    missing = []
    for name, path in required.items():
        if not Path(path).exists():
            missing.append(f"{name}:{path}")
    if missing:
        blockers.append(f"missing_artifacts:{len(missing)}")

    # Static contract checks
    contract_passed, contract_blockers, contract_warnings = _contract_static_checks(
        cfg.reviewed_contract_materialized, ds
    )
    if not contract_passed:
        blockers.extend([f"contract:{b}" for b in contract_blockers])
    warnings.extend(contract_warnings)

    all_present = len(missing) == 0
    executor_available = profile.dataset_specific_executor_available

    # Determine next action and command
    if not all_present:
        if not Path(cfg.metadata_path).exists():
            next_action = "provide_metadata"
            next_command = f"Place {ds} metadata at {cfg.metadata_path}"
        elif not Path(cfg.reviewed_contract_materialized).exists():
            next_action = "run_reviewed_contract_materializer"
            next_command = (
                f"Author/materialize {ds} reviewed contract at "
                f"{cfg.reviewed_contract_materialized}"
            )
        elif not Path(cfg.signal_blocks_path).exists():
            next_action = "run_signal_block_conversion"
            next_command = (
                "Run signal block conversion for dataset (manual operator step)"
            )
        elif not Path(cfg.level_m_csv_path).exists():
            next_action = "run_level_m_signal"
            next_command = (
                "Run Level M signal feature extraction (manual operator step)"
            )
        else:
            next_action = "run_level_t_signal"
            next_command = (
                "Run Level T topology feature extraction (manual operator step)"
            )
        ready = False
    elif not contract_passed:
        next_action = "fix_reviewed_contract"
        next_command = (
            f"Review {cfg.reviewed_contract_materialized} and resolve "
            "static contract check blockers."
        )
        ready = False
    elif not executor_available:
        next_action = "implement_dataset_specific_executor"
        next_command = (
            f"Implement {ds}-specific real benchmark executor. "
            "Generic executor is not wired."
        )
        ready = False
        blockers.append("dataset_specific_executor_unavailable")
    else:
        next_action = "human_peer_review_required"
        next_command = (
            f"Complete peer review checklist before manually running "
            f"real {ds} benchmark execution. No automatic execution."
        )
        ready = True

    # Hardcoded peer-review and execute-flag confirmations
    peer_review_confirmed_by_human = False
    can_use_execute_flag = False
    can_use_peer_reviewed_contract_confirmed_flag = False

    # Manual real execution command
    if executor_available and ds == "DS005620":
        real_cmd = (
            "# DO NOT RUN automatically. Manual operator only.\n"
            "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark "
            f"--dataset-id {ds} "
            f"--reviewed-contract {cfg.reviewed_contract_materialized} "
            f"--metadata {cfg.metadata_path} "
            f"--level-m {str(Path(cfg.level_m_csv_path).parent)} "
            f"--level-t {str(Path(cfg.level_t_csv_path).parent)} "
            f"--out outputs/btc_icft/ds005620_real_benchmark_execution "
            "--execute --peer-reviewed-contract-confirmed"
        )
    else:
        real_cmd = (
            f"# NO MANUAL REAL COMMAND AVAILABLE for {ds}: "
            "dataset-specific executor not yet implemented."
        )

    return GenericExecutionGateResult(
        dataset_id=ds,
        ready_for_real_execution=ready,
        ready_for_p18_execute=ready and executor_available,
        reviewed_contract_static_gate_passed=contract_passed,
        all_required_artifacts_present=all_present,
        dataset_specific_executor_available=executor_available,
        peer_review_required=True,
        peer_review_confirmed_by_human=peer_review_confirmed_by_human,
        can_use_execute_flag=can_use_execute_flag,
        can_use_peer_reviewed_contract_confirmed_flag=(
            can_use_peer_reviewed_contract_confirmed_flag
        ),
        blockers=blockers,
        warnings=warnings,
        next_action=next_action,
        next_command=next_command,
        real_execution_command=real_cmd,
        generated_at=_ts_now(),
    )


def gate_result_to_dict(g: GenericExecutionGateResult) -> dict:
    return {
        "dataset_id": g.dataset_id,
        "ready_for_real_execution": g.ready_for_real_execution,
        "ready_for_p18_execute": g.ready_for_p18_execute,
        "reviewed_contract_static_gate_passed": g.reviewed_contract_static_gate_passed,
        "all_required_artifacts_present": g.all_required_artifacts_present,
        "dataset_specific_executor_available": g.dataset_specific_executor_available,
        "peer_review_required": g.peer_review_required,
        "peer_review_confirmed_by_human": g.peer_review_confirmed_by_human,
        "can_use_execute_flag": g.can_use_execute_flag,
        "can_use_peer_reviewed_contract_confirmed_flag": (
            g.can_use_peer_reviewed_contract_confirmed_flag
        ),
        "blockers": g.blockers,
        "warnings": g.warnings,
        "next_action": g.next_action,
        "next_command": g.next_command,
        "real_execution_command": g.real_execution_command,
        "generated_at": g.generated_at,
    }


def write_generic_gate_outputs(
    result: GenericExecutionGateResult,
    out_dir: str,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}

    ready_doc = {
        "dataset_id": result.dataset_id,
        "ready_for_real_execution": result.ready_for_real_execution,
        "next_action": result.next_action,
        "next_command": result.next_command,
        "peer_review_required": result.peer_review_required,
        "peer_review_confirmed_by_human": result.peer_review_confirmed_by_human,
    }
    p = out / "ready_for_real_execution.json"
    p.write_text(json.dumps(ready_doc, indent=2) + "\n", encoding="utf-8")
    paths["ready_for_real_execution.json"] = str(p)

    gate_doc = gate_result_to_dict(result)
    p = out / "real_execution_gate.json"
    p.write_text(json.dumps(gate_doc, indent=2) + "\n", encoding="utf-8")
    paths["real_execution_gate.json"] = str(p)

    return paths
