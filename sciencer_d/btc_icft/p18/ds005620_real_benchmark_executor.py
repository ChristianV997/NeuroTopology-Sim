"""P18.1 — DS005620 guarded real benchmark executor.

Orchestrates P12 (align_eeg_labels --external-contract) -> P13 (inject_eeg_targets)
-> P11 (run_eeg_signal_mt) for the real/local DS005620 benchmark chain.

Guarantees:
  - dry-run by default
  - --execute requires --peer-reviewed-contract-confirmed
  - never infers labels, never fabricates targets, never modifies source P12/P11/P13
  - P11 always consumes the P13 labeled M features, not raw Level M
  - default subprocess runner is dependency-injected (tests use a fake runner)

Public API
----------
DS005620ExecutionPaths
DS005620StagePlan
DS005620StageResult
DS005620RealBenchmarkExecutionResult
build_execution_paths(...)
build_stage_plan(...)
inspect_stage_prerequisites(...)
run_stage(...)
run_ds005620_real_benchmark_execution(...)
write_ds005620_real_benchmark_outputs(...)
build_execution_omega_event(...)
validate_safe_text(...)
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

_SAFE_CLAIM = (
    "The DS005620 benchmark chain can be orchestrated end-to-end in guarded "
    "mock/local mode using reviewed external labels and explicit target "
    "injection without inferring labels or fabricating targets."
)

_BANNED_PHRASES: tuple[str, ...] = (
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
)

_FORBIDDEN_CLAIMS: list[str] = [
    "No consciousness proof.",
    "No self or soul claim.",
    "No liberation or enlightenment claim.",
    "No afterlife claim.",
    "No ontology proof.",
    "No label inference.",
    "No target fabrication.",
    "No automatic contract activation by executor.",
    "No P11 promotion gate modification.",
    "No legacy mt_real semantics change.",
    "No source P12/P13 contract modification.",
    "No sedated/no_experience shortcut.",
    "No unresponsive/unconscious shortcut.",
]

_STDIO_PREVIEW_LIMIT = 4000


def validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase!r}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DS005620ExecutionPaths:
    reviewed_contract: str
    metadata: str
    signal_blocks: str
    level_m: str
    level_t: str
    p12_out: str
    p13_out: str
    p11_out: str
    artifact_root: str


@dataclass
class DS005620StagePlan:
    stage_id: str
    stage_name: str
    command: list[str]
    requires: list[str]
    expected_outputs: list[str]


@dataclass
class DS005620StageResult:
    stage_id: str
    stage_name: str
    command: list[str]
    ready_to_run: bool
    would_execute: bool
    executed: bool
    skipped: bool
    succeeded: bool
    exit_code: Optional[int]
    blockers: list[str]
    expected_outputs: list[str]
    actual_outputs: list[str]
    stdout_preview: str
    stderr_preview: str
    duration_seconds: Optional[float]


@dataclass
class DS005620RealBenchmarkExecutionResult:
    dataset_id: str
    mode: str
    dry_run: bool
    execute_requested: bool
    peer_reviewed_contract_confirmed: bool
    p12_executed: bool
    p13_executed: bool
    p11_executed: bool
    p12_succeeded: bool
    p13_succeeded: bool
    p11_succeeded: bool
    benchmark_completed: bool
    artifact_root: str
    execution_blockers: list[str]
    warnings: list[str]
    stages: list[dict]
    paths: dict
    omega_event: dict
    safe_claim: str = _SAFE_CLAIM
    forbidden_claims: list[str] = field(default_factory=lambda: _FORBIDDEN_CLAIMS[:])


# ---------------------------------------------------------------------------
# Path & plan builders
# ---------------------------------------------------------------------------

def build_execution_paths(
    artifact_root: str,
    reviewed_contract: str,
    metadata: str,
    signal_blocks: str,
    level_m: str,
    level_t: str,
    p12_out: Optional[str] = None,
    p13_out: Optional[str] = None,
    p11_out: Optional[str] = None,
) -> DS005620ExecutionPaths:
    root = Path(artifact_root)
    p12 = p12_out or str(root / "stage_outputs" / "p12_eeg_labels")
    p13 = p13_out or str(root / "stage_outputs" / "p13_eeg_targets")
    p11 = p11_out or str(root / "stage_outputs" / "p11_signal_mt")
    return DS005620ExecutionPaths(
        reviewed_contract=reviewed_contract,
        metadata=metadata,
        signal_blocks=signal_blocks,
        level_m=level_m,
        level_t=level_t,
        p12_out=p12,
        p13_out=p13,
        p11_out=p11,
        artifact_root=str(root),
    )


def build_stage_plan(
    paths: DS005620ExecutionPaths,
    dataset_id: str = "DS005620",
    python_exe: Optional[str] = None,
) -> list[DS005620StagePlan]:
    py = python_exe or sys.executable

    level_m_csv = str(Path(paths.level_m) / "features_m_signal.csv")
    p12_alignment_csv = str(Path(paths.p12_out) / "label_alignment.csv")
    p13_labeled_csv = str(Path(paths.p13_out) / "features_m_signal_labeled.csv")
    level_t_csv = str(Path(paths.level_t) / "features_t_signal.csv")
    p11_metrics = str(Path(paths.p11_out) / "metrics_signal_mt.json")

    p12 = DS005620StagePlan(
        stage_id="P12",
        stage_name="align_eeg_labels (external reviewed contract)",
        command=[
            py, "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels",
            "--dataset-id", dataset_id,
            "--signal-features", level_m_csv,
            "--metadata", paths.metadata,
            "--external-contract", paths.reviewed_contract,
            "--out", paths.p12_out,
        ],
        requires=[paths.reviewed_contract, paths.metadata, level_m_csv],
        expected_outputs=[p12_alignment_csv],
    )
    p13 = DS005620StagePlan(
        stage_id="P13",
        stage_name="inject_eeg_targets",
        command=[
            py, "-m", "sciencer_d.btc_icft.pipelines.inject_eeg_targets",
            "--dataset-id", dataset_id,
            "--m-features", level_m_csv,
            "--label-alignment", p12_alignment_csv,
            "--out", paths.p13_out,
        ],
        requires=[level_m_csv, p12_alignment_csv],
        expected_outputs=[p13_labeled_csv],
    )
    p11 = DS005620StagePlan(
        stage_id="P11",
        stage_name="run_eeg_signal_mt (target-aware)",
        command=[
            py, "-m", "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
            "--dataset-id", dataset_id,
            "--m-features", p13_labeled_csv,
            "--t-features", level_t_csv,
            "--out", paths.p11_out,
        ],
        requires=[p13_labeled_csv, level_t_csv],
        expected_outputs=[p11_metrics],
    )
    return [p12, p13, p11]


# ---------------------------------------------------------------------------
# Prerequisite inspection
# ---------------------------------------------------------------------------

def inspect_stage_prerequisites(stage: DS005620StagePlan) -> list[str]:
    blockers: list[str] = []
    for req in stage.requires:
        if not Path(req).exists():
            blockers.append(f"{stage.stage_id} prerequisite missing: {req}")
    return blockers


def _truncate(text: str) -> str:
    if text is None:
        return ""
    if len(text) <= _STDIO_PREVIEW_LIMIT:
        return text
    return text[:_STDIO_PREVIEW_LIMIT] + "\n... [truncated]"


# ---------------------------------------------------------------------------
# Runner abstraction
# ---------------------------------------------------------------------------

Runner = Callable[[list[str]], dict]


def default_subprocess_runner(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }


# ---------------------------------------------------------------------------
# Stage runner
# ---------------------------------------------------------------------------

def run_stage(
    stage: DS005620StagePlan,
    runner: Runner,
    dry_run: bool,
    upstream_failed: bool,
    continue_on_failure: bool,
    skip_due_to_stop_after: bool = False,
) -> DS005620StageResult:
    blockers = inspect_stage_prerequisites(stage)
    ready_to_run = len(blockers) == 0

    if skip_due_to_stop_after:
        return DS005620StageResult(
            stage_id=stage.stage_id,
            stage_name=stage.stage_name,
            command=stage.command,
            ready_to_run=ready_to_run,
            would_execute=False,
            executed=False,
            skipped=True,
            succeeded=False,
            exit_code=None,
            blockers=blockers,
            expected_outputs=stage.expected_outputs,
            actual_outputs=[],
            stdout_preview="",
            stderr_preview="",
            duration_seconds=None,
        )

    if dry_run:
        return DS005620StageResult(
            stage_id=stage.stage_id,
            stage_name=stage.stage_name,
            command=stage.command,
            ready_to_run=ready_to_run,
            would_execute=ready_to_run,
            executed=False,
            skipped=False,
            succeeded=False,
            exit_code=None,
            blockers=blockers,
            expected_outputs=stage.expected_outputs,
            actual_outputs=[],
            stdout_preview="",
            stderr_preview="",
            duration_seconds=None,
        )

    if upstream_failed and not continue_on_failure:
        return DS005620StageResult(
            stage_id=stage.stage_id,
            stage_name=stage.stage_name,
            command=stage.command,
            ready_to_run=ready_to_run,
            would_execute=False,
            executed=False,
            skipped=True,
            succeeded=False,
            exit_code=None,
            blockers=blockers + ["skipped_due_to_upstream_failure"],
            expected_outputs=stage.expected_outputs,
            actual_outputs=[],
            stdout_preview="",
            stderr_preview="",
            duration_seconds=None,
        )

    if not ready_to_run:
        return DS005620StageResult(
            stage_id=stage.stage_id,
            stage_name=stage.stage_name,
            command=stage.command,
            ready_to_run=False,
            would_execute=False,
            executed=False,
            skipped=True,
            succeeded=False,
            exit_code=None,
            blockers=blockers,
            expected_outputs=stage.expected_outputs,
            actual_outputs=[],
            stdout_preview="",
            stderr_preview="",
            duration_seconds=None,
        )

    t0 = time.time()
    result = runner(stage.command)
    duration = time.time() - t0
    exit_code = int(result.get("returncode", 1))
    succeeded = exit_code == 0
    actual_outputs = [p for p in stage.expected_outputs if Path(p).exists()]

    return DS005620StageResult(
        stage_id=stage.stage_id,
        stage_name=stage.stage_name,
        command=stage.command,
        ready_to_run=True,
        would_execute=True,
        executed=True,
        skipped=False,
        succeeded=succeeded and len(actual_outputs) == len(stage.expected_outputs),
        exit_code=exit_code,
        blockers=[] if succeeded else [f"{stage.stage_id} exited with code {exit_code}"],
        expected_outputs=stage.expected_outputs,
        actual_outputs=actual_outputs,
        stdout_preview=_truncate(result.get("stdout", "")),
        stderr_preview=_truncate(result.get("stderr", "")),
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# Top-level executor
# ---------------------------------------------------------------------------

def run_ds005620_real_benchmark_execution(
    paths: DS005620ExecutionPaths,
    *,
    dataset_id: str = "DS005620",
    execute: bool = False,
    peer_reviewed_contract_confirmed: bool = False,
    mock_e2e: bool = False,
    stop_after: Optional[str] = None,
    continue_on_stage_failure: bool = False,
    runner: Optional[Runner] = None,
    python_exe: Optional[str] = None,
) -> DS005620RealBenchmarkExecutionResult:
    """Execute the guarded P12 -> P13 -> P11 chain.

    Defaults to dry-run. `execute=True` additionally requires
    `peer_reviewed_contract_confirmed=True`.
    """
    runner = runner or default_subprocess_runner

    execution_blockers: list[str] = []
    warnings: list[str] = []

    if execute and not peer_reviewed_contract_confirmed:
        execution_blockers.append(
            "execute_requested_without_peer_reviewed_contract_confirmation"
        )

    dry_run = not (execute and peer_reviewed_contract_confirmed)

    if stop_after is not None and stop_after not in {"p12", "p13", "p11"}:
        execution_blockers.append(f"invalid_stop_after_value:{stop_after}")
        stop_after = None

    if mock_e2e:
        mode = "mock_e2e"
    elif dry_run:
        mode = "dry_run"
    else:
        mode = "execute"

    plan = build_stage_plan(paths, dataset_id=dataset_id, python_exe=python_exe)

    Path(paths.p12_out).mkdir(parents=True, exist_ok=True)
    Path(paths.p13_out).mkdir(parents=True, exist_ok=True)
    Path(paths.p11_out).mkdir(parents=True, exist_ok=True)

    stage_results: list[DS005620StageResult] = []
    upstream_failed = False
    seen_stop = False

    stop_after_id = None
    if stop_after == "p12":
        stop_after_id = "P12"
    elif stop_after == "p13":
        stop_after_id = "P13"
    elif stop_after == "p11":
        stop_after_id = "P11"

    for stage in plan:
        if seen_stop:
            r = run_stage(
                stage, runner, dry_run=dry_run, upstream_failed=upstream_failed,
                continue_on_failure=continue_on_stage_failure,
                skip_due_to_stop_after=True,
            )
            stage_results.append(r)
            continue

        r = run_stage(
            stage, runner, dry_run=dry_run, upstream_failed=upstream_failed,
            continue_on_failure=continue_on_stage_failure,
        )
        stage_results.append(r)

        if r.executed and not r.succeeded:
            upstream_failed = True

        if stop_after_id is not None and stage.stage_id == stop_after_id:
            seen_stop = True

    p12 = stage_results[0]
    p13 = stage_results[1]
    p11 = stage_results[2]

    benchmark_completed = (
        p12.succeeded and p13.succeeded and p11.succeeded and not dry_run
    )

    omega = build_execution_omega_event_from(
        dataset_id=dataset_id,
        p12_executed=p12.executed,
        p13_executed=p13.executed,
        p11_executed=p11.executed,
        benchmark_completed=benchmark_completed,
    )

    return DS005620RealBenchmarkExecutionResult(
        dataset_id=dataset_id,
        mode=mode,
        dry_run=dry_run,
        execute_requested=execute,
        peer_reviewed_contract_confirmed=peer_reviewed_contract_confirmed,
        p12_executed=p12.executed,
        p13_executed=p13.executed,
        p11_executed=p11.executed,
        p12_succeeded=p12.succeeded,
        p13_succeeded=p13.succeeded,
        p11_succeeded=p11.succeeded,
        benchmark_completed=benchmark_completed,
        artifact_root=paths.artifact_root,
        execution_blockers=execution_blockers,
        warnings=warnings,
        stages=[asdict(s) for s in stage_results],
        paths=asdict(paths),
        omega_event=omega,
    )


# ---------------------------------------------------------------------------
# Omega event
# ---------------------------------------------------------------------------

def build_execution_omega_event_from(
    dataset_id: str,
    p12_executed: bool,
    p13_executed: bool,
    p11_executed: bool,
    benchmark_completed: bool,
) -> dict:
    validate_safe_text(_SAFE_CLAIM)
    payload = (
        f"p18_1:{dataset_id}:{p12_executed}:{p13_executed}:{p11_executed}:"
        f"{benchmark_completed}:{_SAFE_CLAIM}"
    )
    return {
        "event_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "event_type": "ds005620_real_benchmark_execution",
        "dataset_id": dataset_id,
        "p12_executed": p12_executed,
        "p13_executed": p13_executed,
        "p11_executed": p11_executed,
        "benchmark_completed": benchmark_completed,
        "labels_inferred": False,
        "targets_fabricated": False,
        "source_contracts_modified": False,
        "legacy_mt_real_modified": False,
        "contracts_activated_by_executor": False,
        "p11_promotion_gate_modified": False,
        "consciousness_claims_made": False,
        "safe_claim": _SAFE_CLAIM,
        "forbidden_claims": _FORBIDDEN_CLAIMS[:],
    }


def build_execution_omega_event(
    result: DS005620RealBenchmarkExecutionResult,
) -> dict:
    return result.omega_event


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def _command_to_str(cmd: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in cmd)


def write_ds005620_real_benchmark_outputs(
    result: DS005620RealBenchmarkExecutionResult,
    out_dir: str,
) -> dict[str, str]:
    """Write the six P18.1 output artifacts."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # 1. ds005620_real_benchmark_execution.json
    exec_summary = {
        "dataset_id": result.dataset_id,
        "mode": result.mode,
        "dry_run": result.dry_run,
        "execute_requested": result.execute_requested,
        "peer_reviewed_contract_confirmed": result.peer_reviewed_contract_confirmed,
        "p12_executed": result.p12_executed,
        "p13_executed": result.p13_executed,
        "p11_executed": result.p11_executed,
        "p12_succeeded": result.p12_succeeded,
        "p13_succeeded": result.p13_succeeded,
        "p11_succeeded": result.p11_succeeded,
        "benchmark_completed": result.benchmark_completed,
        "artifact_root": result.artifact_root,
        "execution_blockers": result.execution_blockers,
        "warnings": result.warnings,
        "safe_claim": result.safe_claim,
    }
    p = out / "ds005620_real_benchmark_execution.json"
    p.write_text(json.dumps(exec_summary, indent=2), encoding="utf-8")
    outputs["ds005620_real_benchmark_execution"] = str(p)

    # 2. stage_execution_plan.json
    plan_payload = {
        "stages": [
            {
                "stage_id": s["stage_id"],
                "stage_name": s["stage_name"],
                "command": s["command"],
                "command_str": _command_to_str(s["command"]),
                "ready_to_run": s["ready_to_run"],
                "expected_outputs": s["expected_outputs"],
            }
            for s in result.stages
        ],
        "paths": result.paths,
    }
    p = out / "stage_execution_plan.json"
    p.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
    outputs["stage_execution_plan"] = str(p)

    # 3. stage_results.json
    p = out / "stage_results.json"
    p.write_text(
        json.dumps({"stages": result.stages}, indent=2),
        encoding="utf-8",
    )
    outputs["stage_results"] = str(p)

    # 4. execution_blockers.json
    stage_blockers: list[str] = []
    for s in result.stages:
        stage_blockers.extend(s.get("blockers") or [])
    all_blockers = list(result.execution_blockers) + stage_blockers
    p = out / "execution_blockers.json"
    p.write_text(
        json.dumps(
            {
                "execution_blockers": result.execution_blockers,
                "stage_blockers": stage_blockers,
                "all_blockers": all_blockers,
                "blocker_counts": len(all_blockers),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    outputs["execution_blockers"] = str(p)

    # 5. omega_event.json
    p = out / "omega_event.json"
    p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")
    outputs["omega_event"] = str(p)

    # 6. report.md
    report = _build_report_text(result)
    validate_safe_text(report)
    p = out / "report.md"
    p.write_text(report, encoding="utf-8")
    outputs["report"] = str(p)

    return outputs


def _build_report_text(result: DS005620RealBenchmarkExecutionResult) -> str:
    lines = [
        "# DS005620 Real Benchmark Execution (P18.1)",
        "",
        "## Stage",
        "",
        "P18.1 guarded executor — orchestrates P12 -> P13 -> P11 against "
        "reviewed external labels and explicit P12-derived targets. "
        "No labels are inferred. No targets are fabricated.",
        "",
        "## Mode",
        "",
        f"- mode: {result.mode}",
        f"- dry_run: {result.dry_run}",
        f"- execute_requested: {result.execute_requested}",
        f"- peer_reviewed_contract_confirmed: {result.peer_reviewed_contract_confirmed}",
        f"- artifact_root: {result.artifact_root}",
        "",
        "## Stage results",
        "",
        "| Stage | Ready | Executed | Succeeded | Exit | Duration (s) |",
        "|---|---|---|---|---|---|",
    ]
    for s in result.stages:
        dur = s.get("duration_seconds")
        dur_str = f"{dur:.3f}" if isinstance(dur, (int, float)) else "—"
        lines.append(
            f"| {s['stage_id']} | {s['ready_to_run']} | {s['executed']} | "
            f"{s['succeeded']} | {s.get('exit_code')} | {dur_str} |"
        )

    lines += [
        "",
        "## Stage commands",
        "",
    ]
    for s in result.stages:
        lines += [
            f"### {s['stage_id']} — {s['stage_name']}",
            "",
            "```bash",
            _command_to_str(s["command"]),
            "```",
            "",
            f"- expected_outputs: {s['expected_outputs']}",
            f"- actual_outputs: {s['actual_outputs']}",
        ]
        if s.get("blockers"):
            lines.append(f"- blockers: {s['blockers']}")
        lines.append("")

    lines += [
        "## Execution blockers",
        "",
    ]
    if result.execution_blockers:
        for b in result.execution_blockers:
            lines.append(f"- {b}")
    else:
        lines.append("None at the executor level.")

    lines += [
        "",
        "## Benchmark completed",
        "",
        f"- benchmark_completed: {result.benchmark_completed}",
        "",
        "## Safe claim",
        "",
        result.safe_claim,
        "",
        "## Forbidden claims",
        "",
    ]
    for fc in result.forbidden_claims:
        lines.append(f"- {fc}")

    lines += [
        "",
        "## What this run does not claim",
        "",
        "This artifact is an engineering smoke test of a labeled-residual "
        "benchmark over human-reviewed external targets. It makes no "
        "metaphysical, soteriological, or experiential claims about any "
        "subject. See the forbidden-claims list above for the explicit "
        "negative space.",
        "",
        "## Next required step",
        "",
        "After successful mock E2E, run against real/local DS005620 artifacts "
        "with --execute --peer-reviewed-contract-confirmed and submit results "
        "for independent review. A separate paper-skeleton PR should describe "
        "the controlled empirical protocol.",
    ]

    return "\n".join(lines) + "\n"
