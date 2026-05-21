"""
DS005620 Autonomous Iteration Runtime (P21).

Runs safe mock/validation/planning/gate steps in order, records decisions,
and stops at manual real-data or human-review boundaries.

DOES NOT:
- Execute real DS005620 data
- Download data
- Infer labels
- Fabricate targets
- Confirm peer review
- Weaken P18.3 gate or P20 operator
- Weaken ontology quarantine or language firewall
- Emit empirical claims from mock E2E or artifact readiness
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sciencer_d.btc_icft.runtime.events import build_event, envelope_to_dict
from sciencer_d.btc_icft.runtime.event_log import append_envelope

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ITERATION_VERSION = "p21.0"
_SOURCE = "p21_autonomous_iteration"
_SAFE_CLAIM = (
    "P21 adds a safe autonomous iteration runtime that executes mock/planning/validation "
    "steps, records decisions, and stops at manual real-data or human-review boundaries."
)
_FORBIDDEN_PHRASES = [
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
    "topology proves liberation",
    "eeg proves consciousness",
]
_FORBIDDEN_COMMAND_SUBSTRINGS = [
    "--execute --peer-reviewed-contract-confirmed",
    "dandi download",
    "openneuro download",
    "wget",
    "curl",
    "aws s3 cp",
]

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DS005620IterationStep:
    step_id: str
    display_name: str
    command: str
    safe_to_auto_run: bool
    executes_real_data: bool
    downloads_data: bool
    requires_human_review: bool
    required: bool
    expected_outputs: list


@dataclass
class DS005620IterationStepResult:
    step_id: str
    status: str  # pending | skipped | succeeded | failed | blocked | manual_required
    started_at: Optional[str]
    finished_at: Optional[str]
    exit_code: Optional[int]
    stdout_tail: str
    stderr_tail: str
    blockers: list
    warnings: list


@dataclass
class DS005620IterationPlan:
    iteration_id: str
    dataset_id: str
    generated_at: str
    dry_run: bool
    steps: list
    guardrails: dict
    safe_claim: str


@dataclass
class DS005620IterationDecision:
    final_next_action: str
    final_next_command: str
    decision_inputs: dict
    decision_reasons: list
    blocked_by: list
    warnings: list
    computed_at: str


@dataclass
class DS005620IterationState:
    iteration_id: str
    dataset_id: str
    started_at: str
    finished_at: Optional[str]
    dry_run: bool
    iteration_version: str
    total_steps: int
    safe_auto_steps: int
    manual_steps: int
    executed_steps: int
    succeeded_steps: int
    failed_steps: int
    skipped_steps: int
    blocked_steps: int
    last_next_action: str
    last_iteration_status: str  # running | succeeded | failed | partial | dry_run_complete
    guardrails: dict


@dataclass
class DS005620AutonomousIterationResult:
    state: DS005620IterationState
    plan: DS005620IterationPlan
    step_results: list
    decision: DS005620IterationDecision
    output_paths: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_safe_text(text: str) -> list:
    lower = text.lower()
    return [p for p in _FORBIDDEN_PHRASES if p in lower]


def _is_command_forbidden(command: str) -> bool:
    for s in _FORBIDDEN_COMMAND_SUBSTRINGS:
        if s in command:
            return True
    return False


def _read_json_safe(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Default Step Builder
# ---------------------------------------------------------------------------


def _build_default_steps(
    *,
    skip_mock: bool = False,
    skip_real_planning: bool = False,
) -> list:
    steps = []

    if not skip_mock:
        steps.append(
            DS005620IterationStep(
                step_id="ds005620_e2e_mock",
                display_name="Mock E2E benchmark",
                command="make ds005620-e2e-mock",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "ds005620_real_benchmark_execution.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="validate_e2e",
                display_name="Validate E2E",
                command="make validate-ds005620-e2e",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="validate_e2e_json",
                display_name="Validate E2E JSON",
                command="make validate-ds005620-e2e-json",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "validation_summary.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="validate_contracts",
                display_name="Validate contracts",
                command="make validate-ds005620-contracts",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "contract_validation_summary.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="ci_evidence_report",
                display_name="CI evidence report",
                command="make ds005620-ci-evidence-report",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "ci_evidence_report.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="artifact_manifest",
                display_name="Artifact manifest",
                command="make ds005620-build-manifest",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "artifact_manifest.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="ontology_eval",
                display_name="Ontology evaluation (mock)",
                command="make ds005620-ontology-eval-mock",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_ontology_evaluation_mock/"
                    "ontology_claim_evaluation.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="evidence_export",
                display_name="Evidence export",
                command="make ds005620-export-evidence",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "evidence_packet.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="paper_skeleton",
                display_name="Paper skeleton",
                command="make ds005620-paper-skeleton",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                    "paper_skeleton.md"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="runtime_inspection",
                display_name="Runtime inspection",
                command="make ds005620-inspect-runtime",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/science_runtime_inspection/runtime_state.json"
                ],
            )
        )

    # Always included
    steps.append(
        DS005620IterationStep(
            step_id="generated_language_check",
            display_name="Generated language check",
            command="make ds005620-generated-language-check",
            safe_to_auto_run=True,
            executes_real_data=False,
            downloads_data=False,
            requires_human_review=False,
            required=True,
            expected_outputs=[
                "outputs/btc_icft/ds005620_generated_language_validation.json"
            ],
        )
    )

    if not skip_real_planning:
        steps.append(
            DS005620IterationStep(
                step_id="real_local_preflight",
                display_name="Real/local preflight check",
                command="make ds005620-preflight",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="real_artifact_plan",
                display_name="Real artifact plan",
                command="make ds005620-real-artifact-plan",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_artifact_operator/"
                    "real_artifact_next_command.json"
                ],
            )
        )
        steps.append(
            DS005620IterationStep(
                step_id="real_execution_gate",
                display_name="Real execution gate",
                command="make ds005620-real-execution-gate",
                safe_to_auto_run=True,
                executes_real_data=False,
                downloads_data=False,
                requires_human_review=False,
                required=True,
                expected_outputs=[
                    "outputs/btc_icft/ds005620_real_execution_gate/"
                    "ready_for_real_execution.json"
                ],
            )
        )

    # Always included last
    steps.append(
        DS005620IterationStep(
            step_id="manual_real_execution",
            display_name="Manual real execution (human-gated — never auto-run)",
            command="",
            safe_to_auto_run=False,
            executes_real_data=True,
            downloads_data=False,
            requires_human_review=True,
            required=False,
            expected_outputs=[],
        )
    )

    return steps


# ---------------------------------------------------------------------------
# Plan Builder
# ---------------------------------------------------------------------------


def build_default_iteration_plan(
    *,
    iteration_id: Optional[str] = None,
    skip_mock: bool = False,
    skip_real_planning: bool = False,
    dry_run: bool = False,
) -> DS005620IterationPlan:
    if iteration_id is None:
        iteration_id = str(uuid.uuid4())[:12]

    steps = _build_default_steps(
        skip_mock=skip_mock,
        skip_real_planning=skip_real_planning,
    )

    guardrails = {
        "executes_real_data": False,
        "downloads_data": False,
        "auto_confirms_peer_review": False,
        "executes_real_benchmark": False,
        "auto_runs_mne_extraction": False,
        "auto_runs_level_m_extraction": False,
        "auto_runs_level_t_extraction": False,
        "infers_labels": False,
        "fabricates_targets": False,
        "weakens_p18_3_gate": False,
        "weakens_p20_operator": False,
        "weakens_ontology_quarantine": False,
        "weakens_language_firewall": False,
    }

    return DS005620IterationPlan(
        iteration_id=iteration_id,
        dataset_id="ds005620",
        generated_at=_ts_now(),
        dry_run=dry_run,
        steps=steps,
        guardrails=guardrails,
        safe_claim=_SAFE_CLAIM,
    )


# ---------------------------------------------------------------------------
# Safe Command Runner
# ---------------------------------------------------------------------------


def run_safe_command(command: str, cwd: str, timeout_s: int) -> tuple:
    """
    Run a safe shell command. Returns (exit_code, stdout_tail, stderr_tail).
    Raises ValueError if command is forbidden.
    """
    if _is_command_forbidden(command):
        raise ValueError(f"Command is forbidden: {command!r}")
    parts = shlex.split(command)
    try:
        result = subprocess.run(
            parts,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        stdout_tail = "\n".join(result.stdout.splitlines()[-30:])
        stderr_tail = "\n".join(result.stderr.splitlines()[-30:])
        return result.returncode, stdout_tail, stderr_tail
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout_s}s"
    except Exception as exc:
        return 1, "", str(exc)


# ---------------------------------------------------------------------------
# Step Executor
# ---------------------------------------------------------------------------


def _execute_step(
    step: DS005620IterationStep,
    cwd: str,
    timeout_s: int,
    dry_run: bool,
    event_log_path: Optional[str],
    sequence_id: int,
    _runner=None,
) -> DS005620IterationStepResult:
    now = _ts_now()

    def _emit(event_type: str, payload: dict) -> None:
        if event_log_path is None:
            return
        try:
            env = build_event(
                event_type=event_type,
                source=_SOURCE,
                payload=payload,
            )
            append_envelope(env, event_log_path)
        except Exception:
            pass

    # Manual/human-review gate — never auto-run
    if step.requires_human_review and not step.safe_to_auto_run:
        _emit(
            "manual_step.blocked",
            {
                "step_id": step.step_id,
                "command": step.command,
                "status": "manual_required",
                "reason": "requires_human_review",
                "sequence_id": sequence_id,
            },
        )
        return DS005620IterationStepResult(
            step_id=step.step_id,
            status="manual_required",
            started_at=None,
            finished_at=None,
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            blockers=["requires_human_review"],
            warnings=[],
        )

    if not step.safe_to_auto_run:
        _emit(
            "manual_step.blocked",
            {
                "step_id": step.step_id,
                "command": step.command,
                "status": "manual_required",
                "reason": "not_safe_to_auto_run",
                "sequence_id": sequence_id,
            },
        )
        return DS005620IterationStepResult(
            step_id=step.step_id,
            status="manual_required",
            started_at=None,
            finished_at=None,
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            blockers=["not_safe_to_auto_run"],
            warnings=[],
        )

    if step.executes_real_data and not step.safe_to_auto_run:
        return DS005620IterationStepResult(
            step_id=step.step_id,
            status="blocked",
            started_at=None,
            finished_at=None,
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            blockers=["executes_real_data"],
            warnings=[],
        )

    # Dry-run: plan only, no execution
    if dry_run and step.safe_to_auto_run:
        _emit(
            "step.skipped",
            {
                "step_id": step.step_id,
                "command": step.command,
                "status": "pending",
                "reason": "dry_run",
                "sequence_id": sequence_id,
            },
        )
        return DS005620IterationStepResult(
            step_id=step.step_id,
            status="pending",
            started_at=None,
            finished_at=None,
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            blockers=[],
            warnings=[],
        )

    # Execute safe step
    if step.safe_to_auto_run and not dry_run:
        if _is_command_forbidden(step.command):
            return DS005620IterationStepResult(
                step_id=step.step_id,
                status="blocked",
                started_at=None,
                finished_at=None,
                exit_code=None,
                stdout_tail="",
                stderr_tail="",
                blockers=["forbidden_command"],
                warnings=[],
            )

        started_at = _ts_now()
        _emit(
            "step.started",
            {
                "step_id": step.step_id,
                "command": step.command,
                "status": "running",
                "sequence_id": sequence_id,
            },
        )

        runner = _runner if _runner is not None else run_safe_command
        exit_code, stdout_tail, stderr_tail = runner(step.command, cwd, timeout_s)
        finished_at = _ts_now()

        if exit_code == 0:
            status = "succeeded"
            _emit(
                "step.succeeded",
                {
                    "step_id": step.step_id,
                    "command": step.command,
                    "status": "succeeded",
                    "exit_code": exit_code,
                    "sequence_id": sequence_id,
                },
            )
        else:
            status = "failed"
            _emit(
                "step.failed",
                {
                    "step_id": step.step_id,
                    "command": step.command,
                    "status": "failed",
                    "exit_code": exit_code,
                    "sequence_id": sequence_id,
                    "stderr_tail": stderr_tail[-200:],
                },
            )

        return DS005620IterationStepResult(
            step_id=step.step_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            blockers=[] if status == "succeeded" else ["exit_code_nonzero"],
            warnings=[],
        )

    # Fallback (should not reach here normally)
    return DS005620IterationStepResult(
        step_id=step.step_id,
        status="skipped",
        started_at=None,
        finished_at=None,
        exit_code=None,
        stdout_tail="",
        stderr_tail="",
        blockers=[],
        warnings=["unhandled_execution_path"],
    )


# ---------------------------------------------------------------------------
# Decision Logic
# ---------------------------------------------------------------------------


def compute_iteration_decision(
    step_results: list,
    cwd: str,
) -> DS005620IterationDecision:
    cwd_path = Path(cwd)

    val_summary_path = str(
        cwd_path
        / "outputs/btc_icft/ds005620_real_benchmark_execution_mock/validation_summary.json"
    )
    contract_summary_path = str(
        cwd_path
        / "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
        "contract_validation_summary.json"
    )
    language_validation_path = str(
        cwd_path / "outputs/btc_icft/ds005620_generated_language_validation.json"
    )
    real_artifact_next_cmd_path = str(
        cwd_path
        / "outputs/btc_icft/ds005620_real_artifact_operator/real_artifact_next_command.json"
    )
    gate_status_path = str(
        cwd_path
        / "outputs/btc_icft/ds005620_real_execution_gate/ready_for_real_execution.json"
    )
    ontology_decision_path = str(
        cwd_path
        / "outputs/btc_icft/ds005620_ontology_evaluation_mock/ontology_promotion_decision.json"
    )

    validation_summary = _read_json_safe(val_summary_path)
    contract_summary = _read_json_safe(contract_summary_path)
    language_validation = _read_json_safe(language_validation_path)
    real_artifact_next_cmd = _read_json_safe(real_artifact_next_cmd_path)
    gate_status = _read_json_safe(gate_status_path)
    ontology_decision = _read_json_safe(ontology_decision_path)

    decision_inputs = {
        "validation_summary_present": bool(validation_summary),
        "contract_summary_present": bool(contract_summary),
        "language_validation_present": bool(language_validation),
        "real_artifact_next_cmd_present": bool(real_artifact_next_cmd),
        "gate_status_present": bool(gate_status),
        "ontology_decision_present": bool(ontology_decision),
    }

    decision_reasons = []
    blocked_by = []
    warnings = []

    # Compute blocked_by and warnings from step results
    for r in step_results:
        # Find the step result — check if required (we need plan context)
        # We identify required steps by their expected mandatory nature;
        # blocked_by tracks failed required steps.
        if r.status == "failed":
            blocked_by.append(r.step_id)
        elif r.status in ("blocked",):
            warnings.append(f"Step {r.step_id} was blocked")

    # 1. Failed required step
    failed_required = [
        r for r in step_results if r.status == "failed"
    ]
    if failed_required:
        step_ids = [r.step_id for r in failed_required]
        decision_reasons.append(
            f"Required steps failed: {step_ids}. Must fix before proceeding."
        )
        return DS005620IterationDecision(
            final_next_action="fix_failed_safe_step",
            final_next_command=(
                "Review failed step outputs and re-run "
                "make ds005620-autonomous-iteration"
            ),
            decision_inputs=decision_inputs,
            decision_reasons=decision_reasons,
            blocked_by=blocked_by,
            warnings=warnings,
            computed_at=_ts_now(),
        )

    # 2. Language violations
    violations = language_validation.get("violations", [])
    if violations and isinstance(violations, list) and len(violations) > 0:
        decision_reasons.append(
            f"Language violations detected: {len(violations)} violation(s). "
            "Must resolve before proceeding."
        )
        return DS005620IterationDecision(
            final_next_action="blocked_language_violation",
            final_next_command=(
                "Review outputs/btc_icft/ds005620_generated_language_validation.json "
                "and fix language violations"
            ),
            decision_inputs=decision_inputs,
            decision_reasons=decision_reasons,
            blocked_by=blocked_by + ["language_violations"],
            warnings=warnings,
            computed_at=_ts_now(),
        )

    # 3. Contract violation
    contract_passed = contract_summary.get("passed", None)
    contract_status = contract_summary.get("contract_status", None)
    if contract_summary and (
        contract_passed is False or contract_status == "failed"
    ):
        decision_reasons.append(
            "Contract validation failed. Must fix contract violations before proceeding."
        )
        return DS005620IterationDecision(
            final_next_action="blocked_contract_violation",
            final_next_command=(
                "Review outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
                "contract_validation_summary.json and fix contract violations"
            ),
            decision_inputs=decision_inputs,
            decision_reasons=decision_reasons,
            blocked_by=blocked_by + ["contract_violation"],
            warnings=warnings,
            computed_at=_ts_now(),
        )

    # 4. Real artifact next command
    if real_artifact_next_cmd and "next_action" in real_artifact_next_cmd:
        next_action = real_artifact_next_cmd["next_action"]
        next_command = real_artifact_next_cmd.get("next_command", "")
        decision_reasons.append(
            f"Real artifact operator specifies next_action={next_action!r}."
        )
        return DS005620IterationDecision(
            final_next_action=next_action,
            final_next_command=next_command,
            decision_inputs=decision_inputs,
            decision_reasons=decision_reasons,
            blocked_by=blocked_by,
            warnings=warnings,
            computed_at=_ts_now(),
        )

    # 5. Gate ready but human review required
    if gate_status and gate_status.get("ready_for_real_execution") is True:
        decision_reasons.append(
            "Real execution gate is ready but human peer review is still required "
            "before any real data execution."
        )
        return DS005620IterationDecision(
            final_next_action="human_peer_review_required",
            final_next_command=(
                "Gate is ready. A human must confirm peer-reviewed contract before "
                "real execution. Do NOT auto-run."
            ),
            decision_inputs=decision_inputs,
            decision_reasons=decision_reasons,
            blocked_by=blocked_by,
            warnings=warnings,
            computed_at=_ts_now(),
        )

    # 6. Gate specifies next_action
    if gate_status and "next_action" in gate_status:
        next_action = gate_status["next_action"]
        next_command = gate_status.get("next_command", "")
        decision_reasons.append(
            f"Real execution gate specifies next_action={next_action!r}."
        )
        return DS005620IterationDecision(
            final_next_action=next_action,
            final_next_command=next_command,
            decision_inputs=decision_inputs,
            decision_reasons=decision_reasons,
            blocked_by=blocked_by,
            warnings=warnings,
            computed_at=_ts_now(),
        )

    # 7. Default
    decision_reasons.append(
        "All safe mock/planning/validation steps complete. "
        "Mock runtime is ready. Real artifact work requires human operator."
    )
    return DS005620IterationDecision(
        final_next_action="complete_mock_runtime_ready_for_real_artifact_work",
        final_next_command=(
            "All safe steps complete. Proceed to real artifact work with human oversight."
        ),
        decision_inputs=decision_inputs,
        decision_reasons=decision_reasons,
        blocked_by=blocked_by,
        warnings=warnings,
        computed_at=_ts_now(),
    )


# ---------------------------------------------------------------------------
# Iteration State Builder
# ---------------------------------------------------------------------------


def _build_iteration_state(
    iteration_id: str,
    plan: DS005620IterationPlan,
    step_results: list,
    decision: DS005620IterationDecision,
    started_at: str,
    finished_at: str,
    dry_run: bool,
) -> DS005620IterationState:
    total_steps = len(plan.steps)
    safe_auto_steps = sum(1 for s in plan.steps if s.safe_to_auto_run)
    manual_steps = sum(1 for s in plan.steps if not s.safe_to_auto_run)

    succeeded_steps = sum(1 for r in step_results if r.status == "succeeded")
    failed_steps = sum(1 for r in step_results if r.status == "failed")
    skipped_steps = sum(
        1 for r in step_results if r.status in ("skipped", "pending")
    )
    blocked_steps = sum(
        1 for r in step_results if r.status in ("blocked", "manual_required")
    )
    executed_steps = succeeded_steps + failed_steps

    # Determine iteration status
    if dry_run:
        last_iteration_status = "dry_run_complete"
    else:
        # Check if any required step failed
        plan_step_ids_required = {s.step_id for s in plan.steps if s.required}
        any_required_failed = any(
            r for r in step_results
            if r.status == "failed" and r.step_id in plan_step_ids_required
        )
        if any_required_failed:
            last_iteration_status = "failed"
        elif succeeded_steps > 0 and failed_steps == 0 and skipped_steps == 0:
            last_iteration_status = "succeeded"
        else:
            last_iteration_status = "partial"

    return DS005620IterationState(
        iteration_id=iteration_id,
        dataset_id="ds005620",
        started_at=started_at,
        finished_at=finished_at,
        dry_run=dry_run,
        iteration_version=_ITERATION_VERSION,
        total_steps=total_steps,
        safe_auto_steps=safe_auto_steps,
        manual_steps=manual_steps,
        executed_steps=executed_steps,
        succeeded_steps=succeeded_steps,
        failed_steps=failed_steps,
        skipped_steps=skipped_steps,
        blocked_steps=blocked_steps,
        last_next_action=decision.final_next_action,
        last_iteration_status=last_iteration_status,
        guardrails=plan.guardrails,
    )


# ---------------------------------------------------------------------------
# Artifact Index Builder
# ---------------------------------------------------------------------------


def _build_artifact_index(cwd: str) -> dict:
    base = Path(cwd)

    paths = {
        "mock_execution_root": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock"
        ),
        "validation_summary": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
            "validation_summary.json"
        ),
        "contract_summary": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
            "contract_validation_summary.json"
        ),
        "ci_evidence_report": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
            "ci_evidence_report.json"
        ),
        "artifact_manifest": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
            "artifact_manifest.json"
        ),
        "ontology_evaluation_root": (
            "outputs/btc_icft/ds005620_ontology_evaluation_mock"
        ),
        "evidence_packet": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
            "evidence_packet.json"
        ),
        "paper_skeleton": (
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/"
            "paper_skeleton.md"
        ),
        "runtime_inspection_root": (
            "outputs/btc_icft/science_runtime_inspection"
        ),
        "generated_language_validation": (
            "outputs/btc_icft/ds005620_generated_language_validation.json"
        ),
        "real_local_preflight_root": (
            "outputs/btc_icft/ds005620_real_local_preflight"
        ),
        "real_artifact_operator_root": (
            "outputs/btc_icft/ds005620_real_artifact_operator"
        ),
        "real_execution_gate_root": (
            "outputs/btc_icft/ds005620_real_execution_gate"
        ),
    }

    index = {}
    for key, rel_path in paths.items():
        full_path = base / rel_path
        index[key] = {
            "path": str(full_path),
            "exists": full_path.exists(),
        }
    return index


# ---------------------------------------------------------------------------
# Report Builder
# ---------------------------------------------------------------------------


def _build_report_md(
    state: DS005620IterationState,
    plan: DS005620IterationPlan,
    step_results: list,
    decision: DS005620IterationDecision,
    artifact_index: dict,
) -> str:
    lines = []

    lines.append("# DS005620 Autonomous Iteration Runtime (P21)")
    lines.append("")
    lines.append(f"- **iteration_id**: {state.iteration_id}")
    lines.append(f"- **version**: {state.iteration_version}")
    lines.append(f"- **generated_at**: {state.finished_at or _ts_now()}")
    lines.append(f"- **dry_run**: {state.dry_run}")
    lines.append(f"- **status**: {state.last_iteration_status}")
    lines.append("")

    # Safe steps executed
    lines.append("## Safe steps executed")
    lines.append("")
    executed = [r for r in step_results if r.status in ("succeeded", "failed")]
    if executed:
        for r in executed:
            icon = "OK" if r.status == "succeeded" else "FAIL"
            lines.append(f"- [{icon}] `{r.step_id}` — status: {r.status}")
    else:
        lines.append("- (none executed)")
    lines.append("")

    # Steps pending (dry-run)
    pending = [r for r in step_results if r.status == "pending"]
    if pending:
        lines.append("## Steps pending (dry-run)")
        lines.append("")
        for r in pending:
            lines.append(f"- `{r.step_id}`")
        lines.append("")

    # Manual steps not executed
    manual = [r for r in step_results if r.status == "manual_required"]
    if manual:
        lines.append("## Manual steps not executed")
        lines.append("")
        for r in manual:
            lines.append(f"- `{r.step_id}` — requires human review")
        lines.append("")

    # Failed steps
    failed = [r for r in step_results if r.status == "failed"]
    if failed:
        lines.append("## Failed steps")
        lines.append("")
        for r in failed:
            blockers_str = ", ".join(r.blockers) if r.blockers else "(none)"
            lines.append(f"- `{r.step_id}` — blockers: {blockers_str}")
        lines.append("")

    # Current artifact state
    lines.append("## Current artifact state")
    lines.append("")
    for key, info in artifact_index.items():
        exists_str = "exists" if info["exists"] else "missing"
        lines.append(f"- **{key}**: {exists_str} (`{info['path']}`)")
    lines.append("")

    # Current ontology claim scope
    lines.append("## Current ontology claim scope")
    lines.append("")
    lines.append(
        "engineering_runtime (mock E2E only); no empirical promotion"
    )
    lines.append("")

    # Current generated-language status
    lines.append("## Current generated-language status")
    lines.append("")
    lang_val_path = artifact_index.get("generated_language_validation", {}).get("path", "")
    violations = []
    if lang_val_path:
        lang_data = _read_json_safe(lang_val_path)
        violations = lang_data.get("violations", [])
    if violations:
        lines.append(f"VIOLATIONS DETECTED ({len(violations)}):")
        for v in violations:
            lines.append(f"  - {v}")
    else:
        lines.append(
            "Scan complete. No empirical or ontology claims detected in generated outputs."
        )
    lines.append("")

    # Real/local readiness
    lines.append("## Real/local readiness")
    lines.append("")
    gate_info = artifact_index.get("real_execution_gate_root", {})
    gate_exists = gate_info.get("exists", False)
    lines.append(
        f"- real_execution_gate_root: {'exists' if gate_exists else 'missing'}"
    )
    lines.append("")

    # Next action
    lines.append("## Next action")
    lines.append("")
    lines.append(f"- **action**: `{decision.final_next_action}`")
    lines.append(f"- **command**: `{decision.final_next_command}`")
    if decision.decision_reasons:
        lines.append("")
        lines.append("**Reasons:**")
        for reason in decision.decision_reasons:
            lines.append(f"- {reason}")
    lines.append("")

    # Guardrails
    lines.append("## Guardrails")
    lines.append("")
    for key, val in state.guardrails.items():
        lines.append(f"- **{key}**: {val}")
    lines.append("")

    # What this loop does not do
    lines.append("## What this loop does not do")
    lines.append("")
    lines.append("- Does not execute real DS005620 data")
    lines.append("- Does not download data")
    lines.append("- Does not infer labels")
    lines.append("- Does not fabricate targets")
    lines.append("- Does not confirm peer review")
    lines.append("- Does not weaken any guardrail")
    lines.append("")

    report = "\n".join(lines)

    # Safety check: forbidden phrases must not appear in the report
    found = _check_safe_text(report)
    if found:
        raise ValueError(
            f"Report contains forbidden phrases: {found}. Aborting report generation."
        )

    return report


# ---------------------------------------------------------------------------
# Serialization Helpers
# ---------------------------------------------------------------------------


def _step_to_dict(s: DS005620IterationStep) -> dict:
    return {
        "step_id": s.step_id,
        "display_name": s.display_name,
        "command": s.command,
        "safe_to_auto_run": s.safe_to_auto_run,
        "executes_real_data": s.executes_real_data,
        "downloads_data": s.downloads_data,
        "requires_human_review": s.requires_human_review,
        "required": s.required,
        "expected_outputs": s.expected_outputs,
    }


def _result_to_dict(r: DS005620IterationStepResult) -> dict:
    return {
        "step_id": r.step_id,
        "status": r.status,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "exit_code": r.exit_code,
        "stdout_tail": r.stdout_tail,
        "stderr_tail": r.stderr_tail,
        "blockers": r.blockers,
        "warnings": r.warnings,
    }


def _state_to_dict(state: DS005620IterationState) -> dict:
    return {
        "iteration_id": state.iteration_id,
        "dataset_id": state.dataset_id,
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "dry_run": state.dry_run,
        "iteration_version": state.iteration_version,
        "total_steps": state.total_steps,
        "safe_auto_steps": state.safe_auto_steps,
        "manual_steps": state.manual_steps,
        "executed_steps": state.executed_steps,
        "succeeded_steps": state.succeeded_steps,
        "failed_steps": state.failed_steps,
        "skipped_steps": state.skipped_steps,
        "blocked_steps": state.blocked_steps,
        "last_next_action": state.last_next_action,
        "last_iteration_status": state.last_iteration_status,
        "guardrails": state.guardrails,
    }


def _plan_to_dict(plan: DS005620IterationPlan) -> dict:
    return {
        "iteration_id": plan.iteration_id,
        "dataset_id": plan.dataset_id,
        "generated_at": plan.generated_at,
        "dry_run": plan.dry_run,
        "steps": [_step_to_dict(s) for s in plan.steps],
        "guardrails": plan.guardrails,
        "safe_claim": plan.safe_claim,
    }


def _decision_to_dict(d: DS005620IterationDecision) -> dict:
    return {
        "final_next_action": d.final_next_action,
        "final_next_command": d.final_next_command,
        "decision_inputs": d.decision_inputs,
        "decision_reasons": d.decision_reasons,
        "blocked_by": d.blocked_by,
        "warnings": d.warnings,
        "computed_at": d.computed_at,
    }


# ---------------------------------------------------------------------------
# Output Writer
# ---------------------------------------------------------------------------


def write_iteration_outputs(
    result: DS005620AutonomousIterationResult,
    out_dir: str,
) -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    artifact_index = _build_artifact_index(
        str(Path(out_dir).parent.parent.parent)
        if "outputs/btc_icft" in out_dir
        else "."
    )

    # Build report
    report_md = _build_report_md(
        state=result.state,
        plan=result.plan,
        step_results=result.step_results,
        decision=result.decision,
        artifact_index=artifact_index,
    )

    output_paths = {}

    def _write(filename: str, content: str) -> str:
        p = out_path / filename
        p.write_text(content, encoding="utf-8")
        output_paths[filename] = str(p.resolve())
        return str(p.resolve())

    # 1. iteration_state.json
    _write("iteration_state.json", json.dumps(_state_to_dict(result.state), indent=2))

    # 2. iteration_plan.json
    _write("iteration_plan.json", json.dumps(_plan_to_dict(result.plan), indent=2))

    # 3. iteration_results.json
    _write(
        "iteration_results.json",
        json.dumps([_result_to_dict(r) for r in result.step_results], indent=2),
    )

    # 4. iteration_decision_log.json
    _write(
        "iteration_decision_log.json",
        json.dumps(_decision_to_dict(result.decision), indent=2),
    )

    # 5. iteration_next_action.json
    next_action_payload = {
        "next_action": result.decision.final_next_action,
        "next_command": result.decision.final_next_command,
        "blocked_by": result.decision.blocked_by,
        "warnings": result.decision.warnings,
    }
    _write("iteration_next_action.json", json.dumps(next_action_payload, indent=2))

    # 6. iteration_artifact_index.json
    _write("iteration_artifact_index.json", json.dumps(artifact_index, indent=2))

    # 7. iteration_report.md
    _write("iteration_report.md", report_md)

    # 8. iteration_events.jsonl — ensure it exists (may already have been written)
    events_path = out_path / "iteration_events.jsonl"
    if not events_path.exists():
        events_path.write_text("", encoding="utf-8")
    output_paths["iteration_events.jsonl"] = str(events_path.resolve())

    return output_paths


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------


def run_ds005620_autonomous_iteration(
    *,
    out_dir: str = "outputs/btc_icft/ds005620_autonomous_iteration",
    cwd: str = ".",
    dry_run: bool = False,
    continue_on_error: bool = False,
    timeout_s: int = 300,
    max_steps: Optional[int] = None,
    skip_mock: bool = False,
    skip_real_planning: bool = False,
    _command_runner=None,
) -> DS005620AutonomousIterationResult:
    # 1. Build plan
    plan = build_default_iteration_plan(
        skip_mock=skip_mock,
        skip_real_planning=skip_real_planning,
        dry_run=dry_run,
    )
    iteration_id = plan.iteration_id
    started_at = _ts_now()

    # Resolve out_dir as absolute for event_log_path
    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = Path(cwd) / out_path
    out_path.mkdir(parents=True, exist_ok=True)
    event_log_path = str(out_path / "iteration_events.jsonl")

    # 2. Emit iteration.started
    try:
        env = build_event(
            event_type="iteration.started",
            source=_SOURCE,
            payload={
                "iteration_id": iteration_id,
                "dataset_id": "ds005620",
                "iteration_version": _ITERATION_VERSION,
                "dry_run": dry_run,
                "total_planned_steps": len(plan.steps),
            },
        )
        append_envelope(env, event_log_path)
    except Exception:
        pass

    # 3. Execute steps
    step_results = []
    steps = plan.steps
    stopped_early = False

    for idx, step in enumerate(steps):
        if max_steps is not None and idx >= max_steps:
            # Remaining steps are skipped
            for remaining_step in steps[idx:]:
                try:
                    env = build_event(
                        event_type="step.skipped",
                        source=_SOURCE,
                        payload={
                            "step_id": remaining_step.step_id,
                            "reason": "max_steps_reached",
                        },
                    )
                    append_envelope(env, event_log_path)
                except Exception:
                    pass
                step_results.append(
                    DS005620IterationStepResult(
                        step_id=remaining_step.step_id,
                        status="skipped",
                        started_at=None,
                        finished_at=None,
                        exit_code=None,
                        stdout_tail="",
                        stderr_tail="",
                        blockers=[],
                        warnings=["max_steps_reached"],
                    )
                )
            stopped_early = True
            break

        result = _execute_step(
            step=step,
            cwd=cwd,
            timeout_s=timeout_s,
            dry_run=dry_run,
            event_log_path=event_log_path,
            sequence_id=idx,
            _runner=_command_runner,
        )
        step_results.append(result)

        # Stop on required failure unless continue_on_error
        if result.status == "failed" and step.required and not continue_on_error:
            stopped_early = True
            # Remaining steps after this one
            remaining_start = idx + 1
            for remaining_step in steps[remaining_start:]:
                try:
                    env = build_event(
                        event_type="step.skipped",
                        source=_SOURCE,
                        payload={
                            "step_id": remaining_step.step_id,
                            "reason": "stopped_on_required_failure",
                        },
                    )
                    append_envelope(env, event_log_path)
                except Exception:
                    pass
                step_results.append(
                    DS005620IterationStepResult(
                        step_id=remaining_step.step_id,
                        status="skipped",
                        started_at=None,
                        finished_at=None,
                        exit_code=None,
                        stdout_tail="",
                        stderr_tail="",
                        blockers=[],
                        warnings=["stopped_on_required_failure"],
                    )
                )
            break

    # 4. Compute decision
    decision = compute_iteration_decision(step_results=step_results, cwd=cwd)

    # 5. Emit decision.computed
    try:
        env = build_event(
            event_type="decision.computed",
            source=_SOURCE,
            payload={
                "iteration_id": iteration_id,
                "final_next_action": decision.final_next_action,
                "blocked_by": decision.blocked_by,
                "warnings": decision.warnings,
            },
        )
        append_envelope(env, event_log_path)
    except Exception:
        pass

    finished_at = _ts_now()

    # 6. Build state
    state = _build_iteration_state(
        iteration_id=iteration_id,
        plan=plan,
        step_results=step_results,
        decision=decision,
        started_at=started_at,
        finished_at=finished_at,
        dry_run=dry_run,
    )

    # 7. Build artifact index
    artifact_index = _build_artifact_index(cwd)

    # 8. Build result
    result_obj = DS005620AutonomousIterationResult(
        state=state,
        plan=plan,
        step_results=step_results,
        decision=decision,
        output_paths={},
    )

    # 9. Write outputs
    output_paths = write_iteration_outputs(result_obj, str(out_path))
    result_obj.output_paths = output_paths

    # 10. Emit iteration.completed
    try:
        env = build_event(
            event_type="iteration.completed",
            source=_SOURCE,
            payload={
                "iteration_id": iteration_id,
                "last_iteration_status": state.last_iteration_status,
                "last_next_action": state.last_next_action,
                "succeeded_steps": state.succeeded_steps,
                "failed_steps": state.failed_steps,
                "skipped_steps": state.skipped_steps,
                "output_paths": list(output_paths.keys()),
            },
        )
        append_envelope(env, event_log_path)
    except Exception:
        pass

    return result_obj
