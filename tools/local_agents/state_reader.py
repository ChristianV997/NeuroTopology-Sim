"""
ScienceR-Dsim state reader for the local agent research loop (P23).

Reads output files from prior pipeline runs to compute the current system state
and suggest the highest-priority next action.

stdlib only. Never writes files or executes commands.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DatasetState:
    dataset_id: str
    local_data_present: bool = False
    gate_ready: bool = False
    gate_next_action: str = "unknown"
    operator_next_action: str = "unknown"
    empirical_claims_permitted: bool = False
    ontology_quarantined: bool = True
    claim_scope_cap: str = "engineering_runtime"


@dataclass
class SciencerState:
    datasets: list = field(default_factory=list)
    global_next_action: str = "unknown"
    mock_e2e_passed: bool = False
    contract_validation_passed: bool = False
    language_check_passed: bool = False
    matrix_present: bool = False
    loop_version: str = "p23.0"
    notes: list = field(default_factory=list)


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_dataset_state(dataset_id: str, outputs_root: Path) -> DatasetState:
    state = DatasetState(dataset_id=dataset_id)

    # Determine gate path (DS005620 uses legacy layout)
    if dataset_id.upper() == "DS005620":
        gate_path = outputs_root / "ds005620_real_execution_gate" / "ready_for_real_execution.json"
        op_path = outputs_root / "ds005620_real_artifact_operator" / "real_artifact_next_command.json"
        local_root = Path("data/DS005620")
    else:
        gate_path = outputs_root / dataset_id / "real_execution_gate" / "ready_for_real_execution.json"
        op_path = outputs_root / dataset_id / "real_artifact_operator" / "real_artifact_next_command.json"
        local_root = Path(f"data/{dataset_id}")

    state.local_data_present = local_root.exists()

    gate = _load_json(gate_path)
    if gate:
        state.gate_ready = bool(gate.get("ready_for_real_execution", False))
        state.gate_next_action = gate.get("next_action", "unknown")

    op = _load_json(op_path)
    if op:
        state.operator_next_action = op.get("next_action", "unknown")

    # Empirical readiness always blocked — hardcoded
    state.empirical_claims_permitted = False
    state.ontology_quarantined = True
    state.claim_scope_cap = "engineering_runtime"

    return state


def read_sciencer_state(
    outputs_root: str | Path = "outputs/btc_icft",
    dataset_ids: Optional[list[str]] = None,
) -> SciencerState:
    """Read current ScienceR-Dsim state from pipeline outputs."""
    root = Path(outputs_root)
    state = SciencerState()

    if dataset_ids is None:
        dataset_ids = ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]

    state.datasets = [_read_dataset_state(ds, root) for ds in dataset_ids]

    # Mock E2E
    mock_summary = _load_json(root / "ds005620_real_benchmark_execution_mock" / "validation_summary.json")
    if mock_summary:
        state.mock_e2e_passed = bool(mock_summary.get("all_passed", False))

    # Contract validation
    contract_summary = _load_json(root / "ds005620_real_benchmark_execution_mock" / "contract_validation_summary.json")
    if contract_summary:
        state.contract_validation_passed = bool(contract_summary.get("all_passed", False))

    # Language check
    lang_check = _load_json(root / "ds005620_generated_language_validation.json")
    if lang_check:
        state.language_check_passed = not bool(lang_check.get("violations_found", True))

    # Matrix
    matrix_path = root / "multi_dataset_real_execution" / "dataset_source_matrix.json"
    state.matrix_present = matrix_path.exists()

    state.global_next_action = compute_high_level_next_action(state)
    return state


def compute_high_level_next_action(state: SciencerState) -> str:
    """Return the highest-priority next action across the full system state."""
    if not state.mock_e2e_passed:
        return "run_mock_e2e"
    if not state.contract_validation_passed:
        return "fix_contract_validation"
    if not state.language_check_passed:
        return "fix_language_violations"
    if not state.matrix_present:
        return "build_multi_dataset_matrix"

    # Check per-dataset operator actions
    for ds in state.datasets:
        op_action = ds.operator_next_action
        if op_action not in ("", "unknown", "follow_real_execution_gate_next_action", "human_peer_review_required"):
            return f"dataset_operator:{ds.dataset_id}:{op_action}"

    # Gate actions
    for ds in state.datasets:
        gate_action = ds.gate_next_action
        if gate_action not in ("", "unknown", "human_peer_review_required", "manual_real_execution_ready_but_not_auto_run"):
            return f"dataset_gate:{ds.dataset_id}:{gate_action}"

    return "human_peer_review_required"
