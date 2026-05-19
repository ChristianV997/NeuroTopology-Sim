"""
Multi-dataset autonomous iteration runtime (P22).

Orchestrates safe per-dataset planning/inspection steps across all registered
datasets. Never executes real data, downloads, MNE extraction, Level M/T
extraction, or real benchmarks. Never auto-confirms peer review.

stdlib only.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sciencer_d.btc_icft.runtime.event_log import append_envelope
from sciencer_d.btc_icft.runtime.events import build_event
from sciencer_d.btc_icft.runtime.generic_real_artifact_operator import (
    build_generic_real_artifact_plan,
    write_generic_artifact_operator_outputs,
)
from sciencer_d.btc_icft.runtime.generic_real_execution_gate import (
    build_generic_real_execution_gate,
    write_generic_gate_outputs,
)
from sciencer_d.btc_icft.runtime.multi_dataset_paths import (
    DatasetProfile,
    build_dataset_output_roots,
    load_multi_dataset_source_manifest,
)
from sciencer_d.btc_icft.runtime.multi_dataset_real_execution_matrix import (
    build_multi_dataset_matrix,
    write_matrix_outputs,
)


_ITERATION_VERSION = "p22.0"
_SOURCE = "p22_multi_dataset_autonomous_iteration"

_FORBIDDEN_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]


@dataclass
class MultiDatasetIterationStep:
    step_id: str
    dataset_id: str
    display_name: str
    safe_to_auto_run: bool
    executes_real_data: bool
    downloads_data: bool
    requires_human_review: bool


@dataclass
class MultiDatasetIterationStepResult:
    step_id: str
    dataset_id: str
    status: str  # pending | skipped | succeeded | failed | blocked | manual_required
    started_at: Optional[str]
    finished_at: Optional[str]
    blockers: list
    warnings: list
    payload: dict = field(default_factory=dict)


@dataclass
class MultiDatasetIterationPlan:
    iteration_id: str
    iteration_version: str
    generated_at: str
    dry_run: bool
    datasets: list
    steps: list
    guardrails: dict


@dataclass
class MultiDatasetIterationState:
    iteration_id: str
    iteration_version: str
    started_at: str
    finished_at: Optional[str]
    dry_run: bool
    total_steps: int
    succeeded_steps: int
    failed_steps: int
    skipped_steps: int
    manual_steps: int
    n_datasets: int
    last_global_next_action: str
    last_iteration_status: str
    guardrails: dict


@dataclass
class MultiDatasetAutonomousIterationResult:
    state: MultiDatasetIterationState
    plan: MultiDatasetIterationPlan
    step_results: list
    matrix_paths: dict = field(default_factory=dict)
    output_paths: dict = field(default_factory=dict)


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_safe(text: str) -> list:
    lower = text.lower()
    return [p for p in _FORBIDDEN_PHRASES if p in lower]


def _emit(log_path: Optional[str], event_type: str, payload: dict, seq: int) -> None:
    if log_path is None:
        return
    try:
        env = build_event(event_type, payload, _SOURCE, sequence_id=seq)
        append_envelope(log_path, env)
    except Exception:
        pass


def _default_guardrails() -> dict:
    return {
        "executes_real_data": False,
        "downloads_data": False,
        "auto_confirms_peer_review": False,
        "auto_runs_mne_extraction": False,
        "auto_runs_level_m_extraction": False,
        "auto_runs_level_t_extraction": False,
        "auto_runs_real_benchmark": False,
        "auto_declares_label_mapping": False,
        "infers_labels": False,
        "fabricates_targets": False,
        "weakens_p18_3_gate": False,
        "weakens_p20_operator": False,
        "weakens_p21_iteration": False,
        "weakens_ontology_quarantine": False,
        "weakens_language_firewall": False,
    }


def _build_per_dataset_steps(profile: DatasetProfile) -> list:
    ds = profile.dataset_id
    return [
        MultiDatasetIterationStep(
            step_id=f"{ds}__inspect_local_availability",
            dataset_id=ds,
            display_name=f"Inspect local availability for {ds}",
            safe_to_auto_run=True,
            executes_real_data=False,
            downloads_data=False,
            requires_human_review=False,
        ),
        MultiDatasetIterationStep(
            step_id=f"{ds}__inspect_label_adapter",
            dataset_id=ds,
            display_name=f"Inspect label adapter readiness for {ds}",
            safe_to_auto_run=True,
            executes_real_data=False,
            downloads_data=False,
            requires_human_review=False,
        ),
        MultiDatasetIterationStep(
            step_id=f"{ds}__inspect_reader_readiness",
            dataset_id=ds,
            display_name=f"Inspect reader readiness for {ds}",
            safe_to_auto_run=True,
            executes_real_data=False,
            downloads_data=False,
            requires_human_review=False,
        ),
        MultiDatasetIterationStep(
            step_id=f"{ds}__generic_artifact_plan",
            dataset_id=ds,
            display_name=f"Run generic artifact planner for {ds}",
            safe_to_auto_run=True,
            executes_real_data=False,
            downloads_data=False,
            requires_human_review=False,
        ),
        MultiDatasetIterationStep(
            step_id=f"{ds}__generic_execution_gate",
            dataset_id=ds,
            display_name=f"Run generic real execution gate for {ds}",
            safe_to_auto_run=True,
            executes_real_data=False,
            downloads_data=False,
            requires_human_review=False,
        ),
        # Manual blocked steps — never executed
        MultiDatasetIterationStep(
            step_id=f"{ds}__manual_real_execution",
            dataset_id=ds,
            display_name=f"Manual real execution for {ds} (never auto-run)",
            safe_to_auto_run=False,
            executes_real_data=True,
            downloads_data=False,
            requires_human_review=True,
        ),
    ]


def _execute_step(
    step: MultiDatasetIterationStep,
    profile: DatasetProfile,
    *,
    dry_run: bool,
    out_root_per_ds: Path,
    event_log_path: Optional[str],
    sequence_id: int,
) -> MultiDatasetIterationStepResult:
    if not step.safe_to_auto_run:
        _emit(event_log_path, "manual_step.blocked", {
            "step_id": step.step_id,
            "reason": "not_safe_to_auto_run",
        }, sequence_id)
        return MultiDatasetIterationStepResult(
            step_id=step.step_id,
            dataset_id=step.dataset_id,
            status="manual_required",
            started_at=None,
            finished_at=None,
            blockers=["not_safe_to_auto_run"],
            warnings=[],
        )

    if dry_run:
        _emit(event_log_path, "step.skipped", {
            "step_id": step.step_id,
            "reason": "dry_run",
        }, sequence_id)
        return MultiDatasetIterationStepResult(
            step_id=step.step_id,
            dataset_id=step.dataset_id,
            status="pending",
            started_at=None,
            finished_at=None,
            blockers=[],
            warnings=[],
        )

    started = _ts_now()
    _emit(event_log_path, "step.started", {
        "step_id": step.step_id,
        "dataset_id": step.dataset_id,
    }, sequence_id)

    payload: dict = {}
    try:
        kind = step.step_id.split("__", 1)[1]
        if kind == "generic_artifact_plan":
            plan = build_generic_real_artifact_plan(profile)
            op_dir = out_root_per_ds / "artifact_operator"
            paths = write_generic_artifact_operator_outputs(plan, str(op_dir))
            payload = {
                "next_action": plan.next_action,
                "n_stages": len(plan.stages),
                "all_complete": plan.all_stages_complete,
                "output_paths": paths,
            }
        elif kind == "generic_execution_gate":
            gate = build_generic_real_execution_gate(profile)
            g_dir = out_root_per_ds / "execution_gate"
            paths = write_generic_gate_outputs(gate, str(g_dir))
            payload = {
                "ready_for_real_execution": gate.ready_for_real_execution,
                "next_action": gate.next_action,
                "dataset_specific_executor_available": gate.dataset_specific_executor_available,
                "output_paths": paths,
            }
        else:
            # inspect_* — no extra work beyond marking succeeded; matrix builder
            # already does the inspection. We just record success here.
            payload = {"inspected": kind}
    except Exception as exc:
        finished = _ts_now()
        _emit(event_log_path, "step.failed", {
            "step_id": step.step_id,
            "error": str(exc),
        }, sequence_id)
        return MultiDatasetIterationStepResult(
            step_id=step.step_id,
            dataset_id=step.dataset_id,
            status="failed",
            started_at=started,
            finished_at=finished,
            blockers=[str(exc)],
            warnings=[],
        )

    finished = _ts_now()
    _emit(event_log_path, "step.succeeded", {"step_id": step.step_id}, sequence_id)
    return MultiDatasetIterationStepResult(
        step_id=step.step_id,
        dataset_id=step.dataset_id,
        status="succeeded",
        started_at=started,
        finished_at=finished,
        blockers=[],
        warnings=[],
        payload=payload,
    )


def _build_report_md(
    state: MultiDatasetIterationState,
    plan: MultiDatasetIterationPlan,
    results: list,
    matrix_paths: dict,
) -> str:
    lines = [
        "# Multi-Dataset Autonomous Iteration (P22)",
        "",
        f"- iteration_id: `{state.iteration_id}`",
        f"- iteration_version: `{state.iteration_version}`",
        f"- dry_run: `{state.dry_run}`",
        f"- started_at: `{state.started_at}`",
        f"- finished_at: `{state.finished_at}`",
        f"- status: `{state.last_iteration_status}`",
        f"- datasets covered: `{state.n_datasets}`",
        "",
        "## Step counts",
        "",
        f"- total steps: `{state.total_steps}`",
        f"- succeeded: `{state.succeeded_steps}`",
        f"- failed: `{state.failed_steps}`",
        f"- skipped/pending: `{state.skipped_steps}`",
        f"- manual_required: `{state.manual_steps}`",
        "",
        "## Manual blocked steps",
        "",
    ]
    manual = [r for r in results if r.status == "manual_required"]
    if manual:
        for r in manual:
            lines.append(f"- **{r.step_id}**: manual_required (human action only)")
    else:
        lines.append("None.")
    lines += [
        "",
        "## Failed steps",
        "",
    ]
    failed = [r for r in results if r.status == "failed"]
    if failed:
        for r in failed:
            lines.append(f"- **{r.step_id}**: blockers={r.blockers}")
    else:
        lines.append("None.")
    lines += [
        "",
        "## Global next action",
        "",
        f"- next_action: `{state.last_global_next_action}`",
        "",
        "## Matrix outputs",
        "",
    ]
    for name, path in sorted(matrix_paths.items()):
        lines.append(f"- {name}: `{path}`")
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, val in state.guardrails.items():
        lines.append(f"- `{key}`: `{val}`")
    lines += [
        "",
        "## What this loop never does",
        "",
        "- Never executes real DS005620 or any other dataset EEG data.",
        "- Never downloads data.",
        "- Never runs MNE extraction on real data.",
        "- Never runs Level M or Level T extraction on real data.",
        "- Never runs the real P18.1 benchmark.",
        "- Never confirms peer review on behalf of a human.",
        "- Never declares label mappings; that requires human action.",
        "- Never weakens P18.3, P20, or P21 guardrails.",
        "- Never weakens ontology quarantine or language firewall.",
        "",
        "---",
        "",
        "*P22 generalizes the DS005620 real-execution planning pattern into a "
        "registry-driven multi-dataset framework that inspects local readiness, "
        "plans artifact preparation, computes next actions, and preserves manual "
        "real-data and human-review boundaries.*",
    ]
    md = "\n".join(lines)
    violations = _check_safe(md)
    if violations:
        raise ValueError(f"iteration_report.md contains banned phrases: {violations}")
    return md


def run_multi_dataset_autonomous_iteration(
    *,
    sources_manifest: Optional[str] = None,
    out_dir: str = "outputs/btc_icft/multi_dataset_autonomous_iteration",
    matrix_out_dir: str = "outputs/btc_icft/multi_dataset_real_execution",
    cwd: str = ".",
    dry_run: bool = False,
    dataset_ids: Optional[list] = None,
    max_files: int = 5000,
) -> MultiDatasetAutonomousIterationResult:
    started_at = _ts_now()
    iteration_id = str(uuid.uuid4())[:12]

    profiles = load_multi_dataset_source_manifest(sources_manifest)
    if dataset_ids:
        profiles = [p for p in profiles if p.dataset_id in dataset_ids]

    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = Path(cwd) / out_path
    out_path.mkdir(parents=True, exist_ok=True)
    event_log_path = str(out_path / "iteration_events.jsonl")

    # Build plan steps
    all_steps: list = []
    for p in profiles:
        all_steps.extend(_build_per_dataset_steps(p))

    plan = MultiDatasetIterationPlan(
        iteration_id=iteration_id,
        iteration_version=_ITERATION_VERSION,
        generated_at=started_at,
        dry_run=dry_run,
        datasets=[p.dataset_id for p in profiles],
        steps=all_steps,
        guardrails=_default_guardrails(),
    )

    seq = 0
    _emit(event_log_path, "iteration.started", {
        "iteration_id": iteration_id,
        "n_datasets": len(profiles),
        "dry_run": dry_run,
    }, seq)
    seq += 1

    profile_map = {p.dataset_id: p for p in profiles}
    results: list = []

    # Execute steps per dataset
    for step in all_steps:
        profile = profile_map[step.dataset_id]
        per_ds_root = out_path / step.dataset_id
        result = _execute_step(
            step,
            profile,
            dry_run=dry_run,
            out_root_per_ds=per_ds_root,
            event_log_path=event_log_path,
            sequence_id=seq,
        )
        seq += 1
        results.append(result)

    # Build and write matrix (always, even in dry-run)
    matrix = build_multi_dataset_matrix(profiles)
    matrix_paths = write_matrix_outputs(matrix, str(Path(cwd) / matrix_out_dir))

    finished_at = _ts_now()

    succeeded = sum(1 for r in results if r.status == "succeeded")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status in ("skipped", "pending"))
    manual = sum(1 for r in results if r.status == "manual_required")

    if dry_run:
        iter_status = "dry_run_complete"
    elif failed > 0:
        iter_status = "failed"
    elif succeeded >= len([s for s in all_steps if s.safe_to_auto_run]):
        iter_status = "succeeded"
    else:
        iter_status = "partial"

    state = MultiDatasetIterationState(
        iteration_id=iteration_id,
        iteration_version=_ITERATION_VERSION,
        started_at=started_at,
        finished_at=finished_at,
        dry_run=dry_run,
        total_steps=len(all_steps),
        succeeded_steps=succeeded,
        failed_steps=failed,
        skipped_steps=skipped,
        manual_steps=manual,
        n_datasets=len(profiles),
        last_global_next_action=matrix.global_next_action,
        last_iteration_status=iter_status,
        guardrails=_default_guardrails(),
    )

    iteration_result = MultiDatasetAutonomousIterationResult(
        state=state,
        plan=plan,
        step_results=results,
        matrix_paths=matrix_paths,
    )

    # Write outputs
    output_paths = _write_iteration_outputs(iteration_result, str(out_path))
    iteration_result.output_paths = output_paths

    _emit(event_log_path, "decision.computed", {
        "global_next_action": matrix.global_next_action,
    }, seq)
    seq += 1
    _emit(event_log_path, "iteration.completed", {
        "iteration_id": iteration_id,
        "status": iter_status,
        "next_action": matrix.global_next_action,
    }, seq)

    return iteration_result


def _write_iteration_outputs(
    result: MultiDatasetAutonomousIterationResult,
    out_dir: str,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}

    def _wj(name: str, obj: dict) -> str:
        p = out / name
        p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        return str(p)

    paths["iteration_state.json"] = _wj("iteration_state.json", asdict(result.state))

    plan_doc = {
        "iteration_id": result.plan.iteration_id,
        "iteration_version": result.plan.iteration_version,
        "generated_at": result.plan.generated_at,
        "dry_run": result.plan.dry_run,
        "datasets": result.plan.datasets,
        "steps": [asdict(s) for s in result.plan.steps],
        "guardrails": result.plan.guardrails,
    }
    paths["iteration_plan.json"] = _wj("iteration_plan.json", plan_doc)

    results_doc = {
        "iteration_id": result.state.iteration_id,
        "step_results": [asdict(r) for r in result.step_results],
    }
    paths["iteration_results.json"] = _wj("iteration_results.json", results_doc)

    decision_doc = {
        "iteration_id": result.state.iteration_id,
        "global_next_action": result.state.last_global_next_action,
        "last_iteration_status": result.state.last_iteration_status,
    }
    paths["iteration_decision_log.json"] = _wj("iteration_decision_log.json", decision_doc)

    next_actions_doc = {
        "iteration_id": result.state.iteration_id,
        "global_next_action": result.state.last_global_next_action,
        "per_dataset_results": [
            {
                "step_id": r.step_id,
                "dataset_id": r.dataset_id,
                "status": r.status,
                "blockers": r.blockers,
            }
            for r in result.step_results
        ],
    }
    paths["iteration_next_actions.json"] = _wj("iteration_next_actions.json", next_actions_doc)

    # iteration_artifact_index.json — surface key matrix outputs
    artifact_index = {
        "matrix_paths": result.matrix_paths,
        "per_dataset_iteration_roots": {
            ds_id: str(Path(out_dir) / ds_id)
            for ds_id in result.plan.datasets
        },
    }
    paths["iteration_artifact_index.json"] = _wj(
        "iteration_artifact_index.json", artifact_index
    )

    # iteration_report.md
    report = _build_report_md(
        result.state, result.plan, result.step_results, result.matrix_paths
    )
    p = out / "iteration_report.md"
    p.write_text(report, encoding="utf-8")
    paths["iteration_report.md"] = str(p)

    # Ensure events log exists
    events_path = out / "iteration_events.jsonl"
    if not events_path.exists():
        events_path.write_text("", encoding="utf-8")
    paths["iteration_events.jsonl"] = str(events_path)

    return paths
