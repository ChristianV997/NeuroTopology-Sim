"""
Multi-dataset real-execution status matrix (P22).

For each registered dataset, compute a structured per-dataset status across:
- source
- local data availability
- label contract readiness
- reader readiness
- artifact operator status
- real execution gate status
- autonomous iteration readiness
- empirical readiness
- ontology scope
- next action

Never executes real data, downloads, or auto-confirms peer review.

stdlib only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sciencer_d.btc_icft.runtime.generic_real_artifact_operator import (
    build_generic_real_artifact_plan,
    plan_to_dict,
)
from sciencer_d.btc_icft.runtime.generic_real_execution_gate import (
    build_generic_real_execution_gate,
    gate_result_to_dict,
)
from sciencer_d.btc_icft.runtime.multi_dataset_paths import (
    DatasetProfile,
    build_dataset_output_roots,
    build_dataset_path_config,
    load_multi_dataset_source_manifest,
)


_MATRIX_VERSION = "p22.0"

_FORBIDDEN_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]

_REQUIRED_CONTROLS = [
    "nulls.json",
    "ablations.json",
    "leakage_report.json",
    "artifact_report.json",
]


@dataclass
class DatasetSourceStatus:
    dataset_id: str
    title: str
    source_hint: str
    source_url_hint: str
    expected_modality: str
    canonical_local_roots: list
    notes: str


@dataclass
class DatasetLocalDataStatus:
    dataset_id: str
    local_root_resolved: Optional[str]
    metadata_present: bool
    raw_eeg_present: bool
    n_metadata_candidates_found: int
    n_raw_eeg_files_found: int
    readiness_status: str  # missing_local_root | metadata_present_no_raw_eeg |
                            # raw_eeg_present_no_metadata | local_data_present | empty_local_root


@dataclass
class DatasetLabelContractStatus:
    dataset_id: str
    label_contract_required: bool
    declaration_present: bool
    materialized_present: bool
    static_gate_passed: bool
    blockers: list
    readiness_status: str


@dataclass
class DatasetReaderReadinessStatus:
    dataset_id: str
    preflight_output_present: bool
    expected_extensions: list
    raw_eeg_files_observed: int


@dataclass
class DatasetArtifactOperatorStatus:
    dataset_id: str
    operator_supported: bool
    all_stages_complete: bool
    ready_for_real_execution_gate: bool
    n_stages: int
    n_complete: int
    n_blocked: int
    next_action: str
    next_command: str


@dataclass
class DatasetRealExecutionGateStatus:
    dataset_id: str
    gate_supported: bool
    ready_for_real_execution: bool
    contract_static_gate_passed: bool
    dataset_specific_executor_available: bool
    peer_review_required: bool
    peer_review_confirmed_by_human: bool
    can_use_execute_flag: bool
    next_action: str
    next_command: str


@dataclass
class DatasetAutonomousIterationStatus:
    dataset_id: str
    iteration_supported: bool
    output_present: bool
    output_root: str
    last_iteration_status: Optional[str]
    last_next_action: Optional[str]


@dataclass
class DatasetEmpiricalReadinessStatus:
    dataset_id: str
    real_execution_completed: bool
    controls_present: dict
    all_controls_present: bool
    empirical_claims_permitted: bool
    readiness_status: str  # blocked_no_real_execution | blocked_missing_controls | ready_with_human_review


@dataclass
class DatasetOntologyScopeStatus:
    dataset_id: str
    claim_scope_cap: str  # engineering_runtime
    promotion_state: str  # engineering_validated
    ontology_quarantined: bool
    next_required_step: str


@dataclass
class DatasetNextAction:
    dataset_id: str
    next_action: str
    next_command: str
    safe_to_auto_run: bool
    requires_human_review: bool
    executes_real_data: bool
    downloads_data: bool


@dataclass
class MultiDatasetRealExecutionMatrix:
    matrix_version: str
    generated_at: str
    datasets: dict
    global_next_action: str
    global_next_command: str
    n_datasets: int
    n_with_local_data: int
    n_ready_for_real_execution: int
    safe_claim: str


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_safe(text: str) -> list:
    lower = text.lower()
    return [p for p in _FORBIDDEN_PHRASES if p in lower]


# ---------------------------------------------------------------------------
# Per-dataset inspectors
# ---------------------------------------------------------------------------

def _inspect_source(profile: DatasetProfile) -> DatasetSourceStatus:
    return DatasetSourceStatus(
        dataset_id=profile.dataset_id,
        title=profile.title,
        source_hint=profile.source_hint,
        source_url_hint=profile.source_url_hint,
        expected_modality=profile.expected_modality,
        canonical_local_roots=list(profile.canonical_local_roots),
        notes=profile.notes,
    )


def _inspect_local_data(profile: DatasetProfile) -> DatasetLocalDataStatus:
    cfg = build_dataset_path_config(profile)
    ds = profile.dataset_id

    # Resolve local root
    local_root_resolved = None
    for candidate in profile.canonical_local_roots:
        if Path(candidate).exists():
            local_root_resolved = candidate
            break

    if local_root_resolved is None:
        return DatasetLocalDataStatus(
            dataset_id=ds,
            local_root_resolved=None,
            metadata_present=False,
            raw_eeg_present=False,
            n_metadata_candidates_found=0,
            n_raw_eeg_files_found=0,
            readiness_status="missing_local_root",
        )

    root = Path(local_root_resolved)

    # Search metadata candidates
    metadata_found = 0
    for pattern in profile.metadata_candidates:
        for p in root.rglob(pattern):
            if p.is_file():
                metadata_found += 1

    # Search raw EEG files
    raw_files = 0
    exts = {e.lower() for e in profile.raw_eeg_extensions}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts and p.suffix.lower() not in {".csv", ".tsv"}:
            # Exclude pure-text metadata-like files from "raw EEG"
            raw_files += 1

    metadata_present = metadata_found > 0
    raw_present = raw_files > 0

    if not metadata_present and not raw_present:
        status = "empty_local_root"
    elif metadata_present and not raw_present:
        status = "metadata_present_no_raw_eeg"
    elif raw_present and not metadata_present:
        status = "raw_eeg_present_no_metadata"
    else:
        status = "local_data_present"

    return DatasetLocalDataStatus(
        dataset_id=ds,
        local_root_resolved=local_root_resolved,
        metadata_present=metadata_present,
        raw_eeg_present=raw_present,
        n_metadata_candidates_found=metadata_found,
        n_raw_eeg_files_found=raw_files,
        readiness_status=status,
    )


def _inspect_label_contract(profile: DatasetProfile) -> DatasetLabelContractStatus:
    cfg = build_dataset_path_config(profile)
    ds = profile.dataset_id

    declaration_present = Path(cfg.reviewed_contract_source).exists()
    materialized_present = Path(cfg.reviewed_contract_materialized).exists()

    # Reuse static gate from generic gate
    from sciencer_d.btc_icft.runtime.generic_real_execution_gate import (
        _contract_static_checks,
    )

    static_passed = False
    blockers: list = []
    if materialized_present:
        static_passed, contract_blockers, _ = _contract_static_checks(
            cfg.reviewed_contract_materialized, ds
        )
        blockers.extend(contract_blockers)

    if not declaration_present:
        status = "declaration_missing"
    elif not materialized_present:
        status = "needs_materialization"
    elif not static_passed:
        status = "static_gate_failed"
    else:
        status = "contract_active"

    return DatasetLabelContractStatus(
        dataset_id=ds,
        label_contract_required=profile.label_contract_required,
        declaration_present=declaration_present,
        materialized_present=materialized_present,
        static_gate_passed=static_passed,
        blockers=blockers,
        readiness_status=status,
    )


def _inspect_reader_readiness(profile: DatasetProfile) -> DatasetReaderReadinessStatus:
    cfg = build_dataset_path_config(profile)
    ds = profile.dataset_id

    preflight_present = Path(cfg.reader_preflight_path).exists()
    raw_observed = 0
    if Path(cfg.raw_eeg_root).exists():
        exts = {e.lower() for e in profile.raw_eeg_extensions}
        for p in Path(cfg.raw_eeg_root).rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                raw_observed += 1

    return DatasetReaderReadinessStatus(
        dataset_id=ds,
        preflight_output_present=preflight_present,
        expected_extensions=list(profile.raw_eeg_extensions),
        raw_eeg_files_observed=raw_observed,
    )


def _inspect_artifact_operator(profile: DatasetProfile) -> DatasetArtifactOperatorStatus:
    plan = build_generic_real_artifact_plan(profile)
    n_stages = len(plan.stages)
    n_complete = sum(1 for s in plan.stages if s.status == "complete")
    n_blocked = sum(
        1 for s in plan.stages
        if s.status in ("blocked", "blocked_dataset_specific_support_required")
    )
    return DatasetArtifactOperatorStatus(
        dataset_id=profile.dataset_id,
        operator_supported=profile.generic_artifact_operator_supported,
        all_stages_complete=plan.all_stages_complete,
        ready_for_real_execution_gate=plan.ready_for_real_execution_gate,
        n_stages=n_stages,
        n_complete=n_complete,
        n_blocked=n_blocked,
        next_action=plan.next_action,
        next_command=plan.next_command,
    )


def _inspect_real_execution_gate(
    profile: DatasetProfile,
) -> DatasetRealExecutionGateStatus:
    g = build_generic_real_execution_gate(profile)
    return DatasetRealExecutionGateStatus(
        dataset_id=profile.dataset_id,
        gate_supported=profile.generic_execution_gate_supported,
        ready_for_real_execution=g.ready_for_real_execution,
        contract_static_gate_passed=g.reviewed_contract_static_gate_passed,
        dataset_specific_executor_available=g.dataset_specific_executor_available,
        peer_review_required=g.peer_review_required,
        peer_review_confirmed_by_human=g.peer_review_confirmed_by_human,
        can_use_execute_flag=g.can_use_execute_flag,
        next_action=g.next_action,
        next_command=g.next_command,
    )


def _inspect_autonomous_iteration(
    profile: DatasetProfile,
) -> DatasetAutonomousIterationStatus:
    roots = build_dataset_output_roots(profile.dataset_id)
    out_root = Path(roots.autonomous_iteration_root)
    state_path = out_root / "iteration_state.json"
    last_status = None
    last_action = None
    present = state_path.exists()
    if present:
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            last_status = data.get("last_iteration_status")
            last_action = data.get("last_next_action")
        except Exception:
            pass

    return DatasetAutonomousIterationStatus(
        dataset_id=profile.dataset_id,
        iteration_supported=profile.autonomous_iteration_supported,
        output_present=present,
        output_root=str(out_root),
        last_iteration_status=last_status,
        last_next_action=last_action,
    )


def _inspect_empirical_readiness(
    profile: DatasetProfile,
    gate_status: DatasetRealExecutionGateStatus,
) -> DatasetEmpiricalReadinessStatus:
    # Empirical readiness requires real execution + all 4 controls.
    # Real execution is never auto-run, so this is always blocked in default state.
    ds = profile.dataset_id
    if ds == "DS005620":
        exec_root = Path("outputs/btc_icft/ds005620_real_benchmark_execution")
    else:
        exec_root = Path(f"outputs/btc_icft/{ds}/real_benchmark_execution")

    # We consider real execution completed only if a non-mock execution artifact exists
    # The mock E2E run uses _mock suffix, so this is the non-mock root.
    real_completed = (exec_root / "ds005620_real_benchmark_execution.json").exists() if ds == "DS005620" else False

    controls: dict = {}
    for c in _REQUIRED_CONTROLS:
        controls[c] = (exec_root / c).exists()

    all_controls = all(controls.values()) and real_completed

    if not real_completed:
        status = "blocked_no_real_execution"
    elif not all(controls.values()):
        status = "blocked_missing_controls"
    else:
        status = "ready_with_human_review"

    return DatasetEmpiricalReadinessStatus(
        dataset_id=ds,
        real_execution_completed=real_completed,
        controls_present=controls,
        all_controls_present=all_controls,
        empirical_claims_permitted=False,  # always False; never auto-promote
        readiness_status=status,
    )


def _inspect_ontology_scope(profile: DatasetProfile) -> DatasetOntologyScopeStatus:
    # Ontology scope is always capped at engineering_runtime in default state.
    return DatasetOntologyScopeStatus(
        dataset_id=profile.dataset_id,
        claim_scope_cap="engineering_runtime",
        promotion_state="engineering_validated",
        ontology_quarantined=True,
        next_required_step=(
            "Ontology promotion remains blocked. Real execution + controls "
            "+ independent mechanism evidence required before any scope upgrade."
        ),
    )


def _compute_next_action(
    profile: DatasetProfile,
    local: DatasetLocalDataStatus,
    contract: DatasetLabelContractStatus,
    operator: DatasetArtifactOperatorStatus,
    gate: DatasetRealExecutionGateStatus,
) -> DatasetNextAction:
    ds = profile.dataset_id

    if local.readiness_status == "missing_local_root":
        return DatasetNextAction(
            dataset_id=ds,
            next_action="provide_local_root",
            next_command=(
                f"Place local {ds} dataset at one of: "
                f"{profile.canonical_local_roots}"
            ),
            safe_to_auto_run=False,
            requires_human_review=False,
            executes_real_data=False,
            downloads_data=False,
        )
    if local.readiness_status == "empty_local_root":
        return DatasetNextAction(
            dataset_id=ds,
            next_action="populate_local_root",
            next_command=(
                f"Place {ds} metadata and raw EEG files under "
                f"{local.local_root_resolved}"
            ),
            safe_to_auto_run=False,
            requires_human_review=False,
            executes_real_data=False,
            downloads_data=False,
        )
    if not local.metadata_present:
        return DatasetNextAction(
            dataset_id=ds,
            next_action="provide_metadata",
            next_command=f"Place {ds} metadata file under {local.local_root_resolved}",
            safe_to_auto_run=False,
            requires_human_review=False,
            executes_real_data=False,
            downloads_data=False,
        )
    if not local.raw_eeg_present:
        return DatasetNextAction(
            dataset_id=ds,
            next_action="provide_raw_eeg",
            next_command=f"Place {ds} raw EEG files under {local.local_root_resolved}",
            safe_to_auto_run=False,
            requires_human_review=False,
            executes_real_data=False,
            downloads_data=False,
        )
    if not contract.declaration_present:
        return DatasetNextAction(
            dataset_id=ds,
            next_action="prepare_label_contract_declaration",
            next_command=(
                f"Author {ds} activation declaration; binary mapping requires "
                "human declaration (no inference allowed)."
            ),
            safe_to_auto_run=False,
            requires_human_review=True,
            executes_real_data=False,
            downloads_data=False,
        )
    if not contract.materialized_present:
        return DatasetNextAction(
            dataset_id=ds,
            next_action="materialize_reviewed_contract",
            next_command=operator.next_command,
            safe_to_auto_run=False,
            requires_human_review=True,
            executes_real_data=False,
            downloads_data=False,
        )
    if not contract.static_gate_passed:
        return DatasetNextAction(
            dataset_id=ds,
            next_action="fix_reviewed_contract",
            next_command=(
                f"Resolve static contract blockers for {ds}: {contract.blockers}"
            ),
            safe_to_auto_run=False,
            requires_human_review=True,
            executes_real_data=False,
            downloads_data=False,
        )
    if not gate.dataset_specific_executor_available:
        return DatasetNextAction(
            dataset_id=ds,
            next_action="implement_dataset_specific_executor",
            next_command=(
                f"Implement {ds}-specific real benchmark executor. "
                "Generic executor not yet wired for this dataset."
            ),
            safe_to_auto_run=False,
            requires_human_review=False,
            executes_real_data=False,
            downloads_data=False,
        )
    if not gate.ready_for_real_execution:
        return DatasetNextAction(
            dataset_id=ds,
            next_action=gate.next_action,
            next_command=gate.next_command,
            safe_to_auto_run=False,
            requires_human_review=False,
            executes_real_data=False,
            downloads_data=False,
        )
    return DatasetNextAction(
        dataset_id=ds,
        next_action="human_peer_review_required",
        next_command=(
            f"Complete peer review checklist before manually running "
            f"real {ds} benchmark."
        ),
        safe_to_auto_run=False,
        requires_human_review=True,
        executes_real_data=False,
        downloads_data=False,
    )


# ---------------------------------------------------------------------------
# Build matrix
# ---------------------------------------------------------------------------

def build_multi_dataset_matrix(
    profiles: list,
    dataset_ids: Optional[list] = None,
) -> MultiDatasetRealExecutionMatrix:
    if dataset_ids:
        profiles = [p for p in profiles if p.dataset_id in dataset_ids]

    datasets: dict = {}
    n_local = 0
    n_ready_exec = 0

    for profile in profiles:
        src = _inspect_source(profile)
        local = _inspect_local_data(profile)
        contract = _inspect_label_contract(profile)
        reader = _inspect_reader_readiness(profile)
        operator = _inspect_artifact_operator(profile)
        gate = _inspect_real_execution_gate(profile)
        iteration = _inspect_autonomous_iteration(profile)
        empirical = _inspect_empirical_readiness(profile, gate)
        ontology = _inspect_ontology_scope(profile)
        next_action = _compute_next_action(profile, local, contract, operator, gate)

        if local.readiness_status == "local_data_present":
            n_local += 1
        if gate.ready_for_real_execution:
            n_ready_exec += 1

        datasets[profile.dataset_id] = {
            "source": asdict(src),
            "local_data": asdict(local),
            "label_contract": asdict(contract),
            "reader_readiness": asdict(reader),
            "artifact_operator": asdict(operator),
            "real_execution_gate": asdict(gate),
            "autonomous_iteration": asdict(iteration),
            "empirical_readiness": asdict(empirical),
            "ontology_scope": asdict(ontology),
            "next_action": asdict(next_action),
        }

    # Global next action: choose highest-leverage action by frequency / priority.
    # Priority order: provide_local_root > provide_metadata > provide_raw_eeg >
    # prepare_label_contract_declaration > implement_dataset_specific_executor >
    # human_peer_review_required
    priority = [
        "provide_local_root",
        "populate_local_root",
        "provide_metadata",
        "provide_raw_eeg",
        "prepare_label_contract_declaration",
        "materialize_reviewed_contract",
        "fix_reviewed_contract",
        "implement_dataset_specific_executor",
        "run_real_execution_gate",
        "human_peer_review_required",
    ]
    action_counts: dict = {}
    for ds_data in datasets.values():
        a = ds_data["next_action"]["next_action"]
        action_counts[a] = action_counts.get(a, 0) + 1

    global_action = None
    for a in priority:
        if action_counts.get(a, 0) > 0:
            global_action = a
            break
    if global_action is None and datasets:
        global_action = list(datasets.values())[0]["next_action"]["next_action"]
    if global_action is None:
        global_action = "no_action"

    if global_action == "provide_local_root":
        global_command = "Place local dataset roots for missing datasets (see per-dataset entries)."
    elif global_action == "provide_metadata":
        global_command = "Place metadata files for datasets missing metadata (see per-dataset entries)."
    elif global_action == "implement_dataset_specific_executor":
        global_command = (
            "Implement dataset-specific real benchmark executor for non-DS005620 datasets."
        )
    elif global_action == "human_peer_review_required":
        global_command = "Complete peer review checklist for ready datasets."
    else:
        global_command = "Follow per-dataset next_command (see next_actions.json)."

    return MultiDatasetRealExecutionMatrix(
        matrix_version=_MATRIX_VERSION,
        generated_at=_ts_now(),
        datasets=datasets,
        global_next_action=global_action,
        global_next_command=global_command,
        n_datasets=len(datasets),
        n_with_local_data=n_local,
        n_ready_for_real_execution=n_ready_exec,
        safe_claim=(
            "P22 generalizes the DS005620 real-execution planning pattern into a "
            "registry-driven multi-dataset framework that inspects local readiness, "
            "plans artifact preparation, computes next actions, and preserves manual "
            "real-data and human-review boundaries."
        ),
    )


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def _build_report_md(matrix: MultiDatasetRealExecutionMatrix) -> str:
    lines = [
        "# Multi-Dataset Real-Execution Framework (P22)",
        "",
        f"- matrix_version: `{matrix.matrix_version}`",
        f"- generated_at: `{matrix.generated_at}`",
        f"- datasets covered: `{matrix.n_datasets}`",
        f"- datasets with local data: `{matrix.n_with_local_data}`",
        f"- datasets ready for real execution: `{matrix.n_ready_for_real_execution}`",
        "",
        "## Datasets",
        "",
    ]
    for ds_id, d in matrix.datasets.items():
        lines.append(f"### {ds_id}")
        src = d["source"]
        lines.append(f"- source: {src['source_hint']}")
        lines.append(f"- title: {src['title']}")
        lines.append(f"- local_data: {d['local_data']['readiness_status']}")
        lines.append(f"- label_contract: {d['label_contract']['readiness_status']}")
        lines.append(f"- artifact_operator: {d['artifact_operator']['next_action']}")
        lines.append(f"- real_execution_gate: {d['real_execution_gate']['next_action']}")
        lines.append(
            "- dataset_specific_executor_available: "
            f"{d['real_execution_gate']['dataset_specific_executor_available']}"
        )
        lines.append(f"- empirical_readiness: {d['empirical_readiness']['readiness_status']}")
        lines.append(f"- ontology_scope: {d['ontology_scope']['claim_scope_cap']}")
        lines.append(f"- next_action: `{d['next_action']['next_action']}`")
        lines.append("")
    lines += [
        "## Global next action",
        "",
        f"- next_action: `{matrix.global_next_action}`",
        f"- next_command: {matrix.global_next_command}",
        "",
        "## Guardrails",
        "",
        "- No data downloads (no dandi/openneuro/wget/curl/aws).",
        "- No automatic real DS005620 or other dataset execution.",
        "- No automatic MNE extraction on real data.",
        "- No automatic Level M/T extraction on real data.",
        "- No automatic peer-review confirmation.",
        "- No label inference. No target fabrication.",
        "- No empirical promotion from local data presence or mock E2E.",
        "- No ontology candidate promotion. All claims remain quarantined.",
        "",
        "---",
        "",
        f"*{matrix.safe_claim}*",
    ]
    md = "\n".join(lines)
    violations = _check_safe(md)
    if violations:
        raise ValueError(f"report.md contains banned phrases: {violations}")
    return md


def write_matrix_outputs(
    matrix: MultiDatasetRealExecutionMatrix,
    out_dir: str,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}

    def _wj(name: str, obj: dict) -> str:
        p = out / name
        p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        return str(p)

    # 1. dataset_source_matrix.json
    src_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["source"] for ds, d in matrix.datasets.items()},
    }
    paths["dataset_source_matrix.json"] = _wj("dataset_source_matrix.json", src_doc)

    # 2. local_data_availability_matrix.json
    local_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["local_data"] for ds, d in matrix.datasets.items()},
    }
    paths["local_data_availability_matrix.json"] = _wj(
        "local_data_availability_matrix.json", local_doc
    )

    # 3. label_contract_readiness_matrix.json
    lc_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["label_contract"] for ds, d in matrix.datasets.items()},
    }
    paths["label_contract_readiness_matrix.json"] = _wj(
        "label_contract_readiness_matrix.json", lc_doc
    )

    # 4. eeg_reader_readiness_matrix.json
    rr_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["reader_readiness"] for ds, d in matrix.datasets.items()},
    }
    paths["eeg_reader_readiness_matrix.json"] = _wj(
        "eeg_reader_readiness_matrix.json", rr_doc
    )

    # 5. artifact_operator_matrix.json
    ao_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["artifact_operator"] for ds, d in matrix.datasets.items()},
    }
    paths["artifact_operator_matrix.json"] = _wj(
        "artifact_operator_matrix.json", ao_doc
    )

    # 6. real_execution_gate_matrix.json
    re_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["real_execution_gate"] for ds, d in matrix.datasets.items()},
    }
    paths["real_execution_gate_matrix.json"] = _wj(
        "real_execution_gate_matrix.json", re_doc
    )

    # 7. autonomous_iteration_matrix.json
    ai_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["autonomous_iteration"] for ds, d in matrix.datasets.items()},
    }
    paths["autonomous_iteration_matrix.json"] = _wj(
        "autonomous_iteration_matrix.json", ai_doc
    )

    # 8. empirical_readiness_matrix.json
    er_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["empirical_readiness"] for ds, d in matrix.datasets.items()},
    }
    paths["empirical_readiness_matrix.json"] = _wj(
        "empirical_readiness_matrix.json", er_doc
    )

    # 9. ontology_scope_matrix.json
    os_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "datasets": {ds: d["ontology_scope"] for ds, d in matrix.datasets.items()},
    }
    paths["ontology_scope_matrix.json"] = _wj("ontology_scope_matrix.json", os_doc)

    # 10. next_actions.json
    na_doc = {
        "matrix_version": matrix.matrix_version,
        "generated_at": matrix.generated_at,
        "global_next_action": matrix.global_next_action,
        "global_next_command": matrix.global_next_command,
        "per_dataset": {ds: d["next_action"] for ds, d in matrix.datasets.items()},
    }
    paths["next_actions.json"] = _wj("next_actions.json", na_doc)

    # 11. operator_report.md
    report = _build_report_md(matrix)
    p = out / "operator_report.md"
    p.write_text(report, encoding="utf-8")
    paths["operator_report.md"] = str(p)

    return paths
