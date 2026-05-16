"""
ScienceR-Dsim state reader for the local agent research loop (P23/P24).

Reads output files from prior pipeline runs to compute the current system state
and suggest the highest-priority next action. P24 adds first-class reading
of P22 multi-dataset outputs.

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
class MultiDatasetState:
    """State read from P22 multi-dataset outputs."""
    global_next_action: str = "not_available"
    per_dataset_next_actions: dict = field(default_factory=dict)
    empirical_readiness: dict = field(default_factory=dict)
    ontology_scope: dict = field(default_factory=dict)
    iteration_state: dict = field(default_factory=dict)
    iteration_next_actions: dict = field(default_factory=dict)
    matrix_present: bool = False
    iteration_present: bool = False


@dataclass
class SciencerState:
    datasets: list = field(default_factory=list)
    global_next_action: str = "unknown"
    mock_e2e_passed: bool = False
    contract_validation_passed: bool = False
    language_check_passed: bool = False
    language_violations_found: bool = False
    matrix_present: bool = False
    multi_dataset: MultiDatasetState = field(default_factory=MultiDatasetState)
    loop_version: str = "p24.0"
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


def _read_multi_dataset_state(outputs_root: Path) -> MultiDatasetState:
    """Read P22 multi-dataset outputs. Returns not_available fields if missing."""
    mds = MultiDatasetState()

    matrix_root = outputs_root / "multi_dataset_real_execution"
    iteration_root = outputs_root / "multi_dataset_autonomous_iteration"

    mds.matrix_present = (matrix_root / "dataset_source_matrix.json").exists()
    mds.iteration_present = (iteration_root / "iteration_state.json").exists()

    # Multi-dataset matrix next actions
    next_actions = _load_json(matrix_root / "next_actions.json")
    if next_actions:
        mds.global_next_action = next_actions.get("global_next_action", "not_available")
        mds.per_dataset_next_actions = next_actions.get("per_dataset", {})

    # Empirical readiness matrix — always blocked, never permitted
    empirical = _load_json(matrix_root / "empirical_readiness_matrix.json")
    if empirical:
        mds.empirical_readiness = empirical

    # Ontology scope matrix
    ontology = _load_json(matrix_root / "ontology_scope_matrix.json")
    if ontology:
        mds.ontology_scope = ontology

    # Autonomous iteration state
    iter_state = _load_json(iteration_root / "iteration_state.json")
    if iter_state:
        mds.iteration_state = iter_state

    # Autonomous iteration next actions
    iter_next = _load_json(iteration_root / "iteration_next_actions.json")
    if iter_next:
        mds.iteration_next_actions = iter_next

    return mds


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
        state.language_violations_found = bool(lang_check.get("violations_found", False))

    # P22 Multi-dataset state
    state.multi_dataset = _read_multi_dataset_state(root)
    state.matrix_present = state.multi_dataset.matrix_present

    state.global_next_action = compute_high_level_next_action(state)
    return state


def compute_high_level_next_action(state: SciencerState) -> str:
    """
    Return the highest-priority next action across the full system state.

    Priority (P24):
    1. language violation detected
    2. failed local-agent safe step (not tracked here; caller sets)
    3. multi-dataset global_next_action (if present and actionable)
    4. DS005620 per-dataset next action
    5. human_review_required
    6. dataset_specific_executor_required
    7. controls_required
    8. mock_runtime_complete
    9. no_action_available
    """
    # 1. Language safety (highest priority)
    if state.language_violations_found:
        return "fix_language_violations"

    # 3. Multi-dataset global next action from P22 (when available and actionable)
    if state.multi_dataset.matrix_present:
        mds_action = state.multi_dataset.global_next_action
        if mds_action and mds_action not in ("not_available", "unknown", ""):
            # Pass through multi-dataset actions, but strip dataset-specific executor notes
            if mds_action not in ("human_peer_review_required", "implement_dataset_specific_executor"):
                return mds_action

    # 4. DS005620 per-dataset operator action
    for ds in state.datasets:
        op_action = ds.operator_next_action
        if op_action not in ("", "unknown", "follow_real_execution_gate_next_action", "human_peer_review_required"):
            return f"dataset_operator:{ds.dataset_id}:{op_action}"

    # Gate actions
    for ds in state.datasets:
        gate_action = ds.gate_next_action
        if gate_action not in ("", "unknown", "human_peer_review_required", "manual_real_execution_ready_but_not_auto_run"):
            return f"dataset_gate:{ds.dataset_id}:{gate_action}"

    # Check multi-dataset iteration next actions
    if state.multi_dataset.iteration_next_actions:
        global_iter = state.multi_dataset.iteration_next_actions.get("global_next_action", "")
        if global_iter and global_iter not in ("", "unknown", "complete_mock_runtime_ready_for_real_artifact_work"):
            if "implement_dataset_specific_executor" in global_iter:
                return "dataset_specific_executor_required"
            return global_iter

    # 5. Human review required
    if state.multi_dataset.matrix_present:
        mds_action = state.multi_dataset.global_next_action
        if mds_action == "human_peer_review_required":
            return "human_peer_review_required"

    # 6. Dataset-specific executor
    if state.multi_dataset.matrix_present:
        mds_action = state.multi_dataset.global_next_action
        if mds_action == "implement_dataset_specific_executor":
            return "dataset_specific_executor_required"

    # 8. Mock runtime complete — no blockers
    if state.matrix_present:
        return "mock_runtime_complete"

    # 9. No actionable state available
    return "no_action_available"
