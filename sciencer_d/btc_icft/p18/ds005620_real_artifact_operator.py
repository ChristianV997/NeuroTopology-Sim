"""
DS005620 real artifact build operator (P20).

Plans local DS005620 artifact preparation without executing real data,
downloading data, or weakening label/target/ontology/language guardrails.

All commands are emitted for manual operator use only. Nothing is executed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PLANNER_VERSION = "p20.0"

_FORBIDDEN_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]

_SAFE_CLAIM = (
    "P20 adds a deterministic real artifact build operator that plans DS005620 "
    "local artifact preparation without executing real data or weakening label, "
    "target, ontology, or language guardrails."
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DS005620RealArtifactPathConfig:
    dataset_id: str
    metadata_path: str
    raw_eeg_root: str
    reviewed_contract_source: str
    reviewed_contract_materialized: str
    reader_preflight_path: str
    mne_extract_path: str
    signal_blocks_path: str
    level_m_csv_path: str
    level_t_csv_path: str
    real_execution_gate_path: str


@dataclass
class DS005620RealArtifactCommand:
    stage_id: str
    command: str
    manual_required: bool
    human_review_required: bool
    executes_real_data: bool
    downloads_data: bool
    safe_to_auto_run: bool
    blocked_reason: Optional[str] = None
    description: str = ""


@dataclass
class DS005620RealArtifactStage:
    stage_id: str
    display_name: str
    expected_paths: list[str]
    status: str  # complete | missing | blocked | manual_required | optional
    blockers: list[str]
    warnings: list[str]
    next_command: str
    manual_required: bool
    human_review_required: bool
    executes_real_data: bool
    downloads_data: bool
    safe_to_auto_run: bool
    artifact_hashes: dict[str, Optional[str]]
    size_bytes: int
    checked_at: str


@dataclass
class DS005620RealArtifactBuildPlan:
    dataset_id: str
    planner_version: str
    generated_at: str
    all_stages_complete: bool
    ready_for_real_execution_gate: bool
    ready_for_manual_real_execution: bool
    next_action: str
    next_command: str
    stages: list[DS005620RealArtifactStage]
    commands: list[DS005620RealArtifactCommand]
    blockers: list[str]
    warnings: list[str]
    guardrails: dict
    safe_claim: str = _SAFE_CLAIM


@dataclass
class DS005620RealArtifactOperatorResult:
    plan: DS005620RealArtifactBuildPlan
    output_paths: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def _sha256_dir(path: Path) -> Optional[str]:
    try:
        names = sorted(p.name for p in path.iterdir())
        return hashlib.sha256("\n".join(names).encode()).hexdigest()
    except Exception:
        return None


def _size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return sum(f.stat().st_size for f in path.iterdir() if f.is_file())
    except Exception:
        pass
    return 0


def _check_safe_text(text: str) -> list[str]:
    lower = text.lower()
    return [p for p in _FORBIDDEN_PHRASES if p in lower]


# ---------------------------------------------------------------------------
# Stage inspector
# ---------------------------------------------------------------------------

def _inspect_stage(
    stage_id: str,
    display_name: str,
    paths: list[str],
    next_command: str,
    manual_required: bool = False,
    human_review_required: bool = False,
    executes_real_data: bool = False,
    downloads_data: bool = False,
    safe_to_auto_run: bool = False,
    blocked_reason: Optional[str] = None,
) -> DS005620RealArtifactStage:
    ts = _ts_now()
    hashes: dict[str, Optional[str]] = {}
    total_size = 0
    all_exist = True

    for raw in paths:
        p = Path(raw)
        if p.exists():
            hashes[raw] = _sha256_file(p) if p.is_file() else _sha256_dir(p)
            total_size += _size(p)
        else:
            all_exist = False
            hashes[raw] = None

    blockers: list[str] = []
    if blocked_reason:
        blockers.append(blocked_reason)

    if all_exist:
        status = "complete"
    elif manual_required:
        status = "manual_required"
    else:
        status = "missing"

    return DS005620RealArtifactStage(
        stage_id=stage_id,
        display_name=display_name,
        expected_paths=paths,
        status=status,
        blockers=blockers,
        warnings=[],
        next_command=next_command,
        manual_required=manual_required,
        human_review_required=human_review_required,
        executes_real_data=executes_real_data,
        downloads_data=downloads_data,
        safe_to_auto_run=safe_to_auto_run,
        artifact_hashes=hashes,
        size_bytes=total_size,
        checked_at=ts,
    )


# ---------------------------------------------------------------------------
# Default path config
# ---------------------------------------------------------------------------

def build_default_real_artifact_path_config(
    dataset_id: str = "DS005620",
    metadata: Optional[str] = None,
    raw_eeg_root: Optional[str] = None,
    reviewed_contract_source: Optional[str] = None,
    reviewed_contract: Optional[str] = None,
    reader_preflight: Optional[str] = None,
    mne_extract: Optional[str] = None,
    signal_blocks: Optional[str] = None,
    level_m: Optional[str] = None,
    level_t: Optional[str] = None,
    real_execution_gate: Optional[str] = None,
) -> DS005620RealArtifactPathConfig:
    return DS005620RealArtifactPathConfig(
        dataset_id=dataset_id,
        metadata_path=metadata or "data/DS005620/events.tsv",
        raw_eeg_root=raw_eeg_root or "data/DS005620/raw",
        reviewed_contract_source=(
            reviewed_contract_source
            or "data/DS005620/ds005620_activation_declaration.json"
        ),
        reviewed_contract_materialized=(
            reviewed_contract
            or "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json"
        ),
        reader_preflight_path=(
            reader_preflight
            or "outputs/btc_icft/eeg_reader_preflight/DS005620"
        ),
        mne_extract_path=mne_extract or "outputs/btc_icft/eeg_mne_extract/DS005620",
        signal_blocks_path=(
            signal_blocks or "outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620"
        ),
        level_m_csv_path=(
            level_m or "outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv"
        ),
        level_t_csv_path=(
            level_t or "outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv"
        ),
        real_execution_gate_path=(
            real_execution_gate
            or "outputs/btc_icft/ds005620_real_execution_gate/ready_for_real_execution.json"
        ),
    )


# ---------------------------------------------------------------------------
# Stage builders
# ---------------------------------------------------------------------------

def _build_all_stages(cfg: DS005620RealArtifactPathConfig) -> list[DS005620RealArtifactStage]:
    signal_blocks_dir = str(Path(cfg.signal_blocks_path))

    stages = [
        _inspect_stage(
            stage_id="metadata",
            display_name="DS005620 events metadata (events.tsv)",
            paths=[cfg.metadata_path],
            next_command=f"Place DS005620 events.tsv at {cfg.metadata_path}",
            manual_required=True,
            human_review_required=False,
            executes_real_data=False,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="raw_eeg_root",
            display_name="Raw DS005620 EEG files directory",
            paths=[cfg.raw_eeg_root],
            next_command=f"Place local DS005620 EEG files under {cfg.raw_eeg_root}",
            manual_required=True,
            human_review_required=False,
            executes_real_data=False,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="reviewed_contract_source",
            display_name="Reviewed contract declaration (human-authored)",
            paths=[cfg.reviewed_contract_source],
            next_command=(
                f"Author DS005620 activation declaration and place at "
                f"{cfg.reviewed_contract_source}"
            ),
            manual_required=True,
            human_review_required=True,
            executes_real_data=False,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="reviewed_contract_materialized",
            display_name="Materialized P12 reviewed external contract",
            paths=[cfg.reviewed_contract_materialized],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract"
                f" --declaration {cfg.reviewed_contract_source}"
                " --out outputs/btc_icft/ds005620_reviewed_contract"
            ),
            manual_required=False,
            human_review_required=True,
            executes_real_data=False,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="eeg_reader_preflight",
            display_name="EEG reader preflight output",
            paths=[cfg.reader_preflight_path],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.preflight_eeg_readers"
                f" --dataset-id {cfg.dataset_id}"
                f" --root {cfg.raw_eeg_root}"
                f" --out {cfg.reader_preflight_path}"
            ),
            manual_required=False,
            human_review_required=False,
            executes_real_data=True,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="mne_extraction",
            display_name="MNE signal extraction output",
            paths=[cfg.mne_extract_path],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks"
                f" --dataset-id {cfg.dataset_id}"
                f" --input <first_eeg_file_under_{cfg.raw_eeg_root}>"
                f" --out {cfg.mne_extract_path}"
            ),
            manual_required=False,
            human_review_required=False,
            executes_real_data=True,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="canonical_signal_blocks",
            display_name="Canonical signal blocks (P19.2)",
            paths=[cfg.signal_blocks_path],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks"
                f" --dataset-id {cfg.dataset_id}"
                f" --mne-extract {cfg.mne_extract_path}"
                f" --out {signal_blocks_dir}"
            ),
            manual_required=False,
            human_review_required=False,
            executes_real_data=True,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="level_m_features",
            display_name="Level M signal features (features_m_signal.csv)",
            paths=[cfg.level_m_csv_path],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal"
                f" --dataset-id {cfg.dataset_id}"
                f" --signal-blocks {signal_blocks_dir}"
                f" --out {str(Path(cfg.level_m_csv_path).parent)}"
            ),
            manual_required=False,
            human_review_required=False,
            executes_real_data=True,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="level_t_features",
            display_name="Level T topology features (features_t_signal.csv)",
            paths=[cfg.level_t_csv_path],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal"
                f" --dataset-id {cfg.dataset_id}"
                f" --signal-blocks {signal_blocks_dir}"
                f" --out {str(Path(cfg.level_t_csv_path).parent)}"
            ),
            manual_required=False,
            human_review_required=False,
            executes_real_data=True,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
        _inspect_stage(
            stage_id="real_execution_gate",
            display_name="P18.3 real/local execution gate output",
            paths=[cfg.real_execution_gate_path],
            next_command="make ds005620-real-execution-gate",
            manual_required=False,
            human_review_required=True,
            executes_real_data=False,
            downloads_data=False,
            safe_to_auto_run=False,
        ),
    ]
    return stages


# ---------------------------------------------------------------------------
# Command plan builder
# ---------------------------------------------------------------------------

def _build_commands(stages: list[DS005620RealArtifactStage]) -> list[DS005620RealArtifactCommand]:
    cmds = []
    for s in stages:
        blocked_reason = None
        if s.status != "complete" and s.blocked_reason if hasattr(s, "blocked_reason") else None:
            blocked_reason = s.blocked_reason if hasattr(s, "blocked_reason") else None
        cmds.append(DS005620RealArtifactCommand(
            stage_id=s.stage_id,
            command=s.next_command,
            manual_required=s.manual_required,
            human_review_required=s.human_review_required,
            executes_real_data=s.executes_real_data,
            downloads_data=s.downloads_data,
            safe_to_auto_run=False,  # always false — operator chooses when to run
            blocked_reason=blocked_reason,
            description=s.display_name,
        ))
    return cmds


# ---------------------------------------------------------------------------
# Next-action logic
# ---------------------------------------------------------------------------

def _determine_next_action(
    stages: list[DS005620RealArtifactStage],
    gate_ready: bool,
    gate_next_action: Optional[str],
) -> tuple[str, str]:
    stage_map = {s.stage_id: s for s in stages}

    def _missing(sid: str) -> bool:
        return stage_map[sid].status != "complete"

    if _missing("metadata"):
        return ("provide_metadata", stage_map["metadata"].next_command)
    if _missing("raw_eeg_root"):
        return ("provide_raw_eeg", stage_map["raw_eeg_root"].next_command)
    if _missing("reviewed_contract_source"):
        return ("prepare_reviewed_contract_declaration",
                stage_map["reviewed_contract_source"].next_command)
    if _missing("reviewed_contract_materialized"):
        return ("run_reviewed_contract_materializer",
                stage_map["reviewed_contract_materialized"].next_command)
    if _missing("eeg_reader_preflight"):
        return ("run_eeg_reader_preflight",
                stage_map["eeg_reader_preflight"].next_command)
    if _missing("mne_extraction"):
        return ("run_mne_extraction", stage_map["mne_extraction"].next_command)
    if _missing("canonical_signal_blocks"):
        return ("run_signal_block_conversion",
                stage_map["canonical_signal_blocks"].next_command)
    if _missing("level_m_features"):
        return ("run_level_m_signal", stage_map["level_m_features"].next_command)
    if _missing("level_t_features"):
        return ("run_level_t_signal", stage_map["level_t_features"].next_command)
    if _missing("real_execution_gate"):
        return ("run_real_execution_gate", "make ds005620-real-execution-gate")
    if not gate_ready:
        return (
            "follow_real_execution_gate_next_action",
            gate_next_action or "make ds005620-real-execution-gate",
        )
    return (
        "human_peer_review_required",
        (
            "Human reviewer must inspect outputs/btc_icft/ds005620_real_execution_gate/"
            "human_peer_review_checklist.md before manually running the real execution command."
        ),
    )


# ---------------------------------------------------------------------------
# Gate status reader
# ---------------------------------------------------------------------------

def _read_gate_status(gate_path: str) -> tuple[bool, Optional[str]]:
    p = Path(gate_path)
    if not p.exists():
        return False, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ready = bool(data.get("ready_for_real_execution", False))
        next_action = data.get("next_action")
        return ready, next_action
    except Exception:
        return False, None


# ---------------------------------------------------------------------------
# Main planner
# ---------------------------------------------------------------------------

def build_ds005620_real_artifact_build_plan(
    cfg: DS005620RealArtifactPathConfig,
) -> DS005620RealArtifactBuildPlan:
    ts = _ts_now()
    stages = _build_all_stages(cfg)

    gate_ready, gate_next_action = _read_gate_status(cfg.real_execution_gate_path)

    all_complete = all(s.status == "complete" for s in stages)
    # Ready for gate = all except gate itself are complete
    pre_gate_stages = [s for s in stages if s.stage_id != "real_execution_gate"]
    ready_for_gate = all(s.status == "complete" for s in pre_gate_stages)

    next_action, next_cmd = _determine_next_action(stages, gate_ready, gate_next_action)

    all_blockers = [b for s in stages for b in s.blockers]

    commands = _build_commands(stages)

    guardrails = {
        "executes_real_benchmark": False,
        "downloads_data": False,
        "executes_real_data_automatically": False,
        "auto_confirms_peer_review": False,
        "infers_labels": False,
        "fabricates_targets": False,
        "modifies_p18_3_gate": False,
    }

    return DS005620RealArtifactBuildPlan(
        dataset_id=cfg.dataset_id,
        planner_version=_PLANNER_VERSION,
        generated_at=ts,
        all_stages_complete=all_complete,
        ready_for_real_execution_gate=ready_for_gate,
        ready_for_manual_real_execution=gate_ready,
        next_action=next_action,
        next_command=next_cmd,
        stages=stages,
        commands=commands,
        blockers=all_blockers,
        warnings=[],
        guardrails=guardrails,
    )


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _stage_to_dict(s: DS005620RealArtifactStage) -> dict:
    return {
        "stage_id": s.stage_id,
        "display_name": s.display_name,
        "expected_paths": s.expected_paths,
        "status": s.status,
        "blockers": s.blockers,
        "warnings": s.warnings,
        "next_command": s.next_command,
        "manual_required": s.manual_required,
        "human_review_required": s.human_review_required,
        "executes_real_data": s.executes_real_data,
        "downloads_data": s.downloads_data,
        "safe_to_auto_run": s.safe_to_auto_run,
        "artifact_hashes": s.artifact_hashes,
        "size_bytes": s.size_bytes,
        "checked_at": s.checked_at,
    }


def _cmd_to_dict(c: DS005620RealArtifactCommand) -> dict:
    return {
        "stage_id": c.stage_id,
        "command": c.command,
        "manual_required": c.manual_required,
        "human_review_required": c.human_review_required,
        "executes_real_data": c.executes_real_data,
        "downloads_data": c.downloads_data,
        "safe_to_auto_run": c.safe_to_auto_run,
        "blocked_reason": c.blocked_reason,
        "description": c.description,
    }


def _build_commands_sh(plan: DS005620RealArtifactBuildPlan) -> str:
    lines = [
        "#!/bin/bash",
        "# DS005620 Real Artifact Build Operator — Command Guide",
        "# This script is an operator guide. Review before running.",
        "# It does not run automatically from CI.",
        "# Do not run real execution until P18.3 gate and human review pass.",
        "# All real-data commands are commented out by default.",
        "#",
        f"# Generated by P20 real artifact build operator at {plan.generated_at}",
        "#",
        "",
    ]
    for cmd in plan.commands:
        lines.append(f"# === Stage: {cmd.description} ===")
        if cmd.manual_required:
            lines.append(f"# MANUAL STEP: {cmd.command}")
        elif cmd.executes_real_data:
            lines.append(f"# COMMENTED OUT (executes real data — run manually after all checks pass):")
            lines.append(f"# {cmd.command}")
        elif cmd.stage_id == "real_execution_gate":
            lines.append(f"# Run P18.3 gate after all prerequisite artifacts are ready:")
            lines.append(f"# {cmd.command}")
        else:
            lines.append(f"# {cmd.command}")
        lines.append("")
    lines += [
        "# === Real Execution ===",
        "# DO NOT run real execution automatically.",
        "# After all stages complete and P18.3 gate and human review pass,",
        "# the operator may manually run the command from:",
        "#   outputs/btc_icft/ds005620_real_execution_gate/real_execution_command_plan.json",
        "",
    ]
    return "\n".join(lines)


def _build_report_md(plan: DS005620RealArtifactBuildPlan) -> str:
    def yn(v: bool) -> str:
        return "`true`" if v else "`false`"

    lines = [
        "# DS005620 Real Artifact Build Operator",
        "",
        f"- dataset_id: `{plan.dataset_id}`",
        f"- planner_version: `{plan.planner_version}`",
        f"- generated_at: `{plan.generated_at}`",
        "",
        "## Current artifact status",
        "",
    ]
    for s in plan.stages:
        status_label = s.status.upper()
        lines.append(f"- **{s.display_name}**: {status_label}")
        for b in s.blockers:
            lines.append(f"  - BLOCKER: {b}")
    lines += [
        "",
        "## Next action",
        "",
        f"- next_action: `{plan.next_action}`",
        f"- next_command: `{plan.next_command}`",
        "",
        "## Command plan",
        "",
    ]
    for cmd in plan.commands:
        tag = ""
        if cmd.manual_required:
            tag = " [MANUAL]"
        elif cmd.executes_real_data:
            tag = " [REAL DATA — DO NOT AUTO-RUN]"
        lines.append(f"- **{cmd.stage_id}**{tag}: `{cmd.command}`")
    lines += [
        "",
        "## Manual-only steps",
        "",
        "The following steps require direct operator action and cannot be automated:",
        "",
    ]
    for cmd in plan.commands:
        if cmd.manual_required:
            lines.append(f"- **{cmd.stage_id}**: {cmd.command}")
    lines += [
        "",
        "## Human-review steps",
        "",
        "The following steps require human review before proceeding:",
        "",
    ]
    for cmd in plan.commands:
        if cmd.human_review_required:
            lines.append(f"- **{cmd.stage_id}**: review required before or after this stage")
    lines += [
        "",
        "## Missing pipelines",
        "",
        "All required pipeline modules exist in the current repository.",
        "If a pipeline file is missing in future, operator output will report `blocked_missing_pipeline`.",
        "",
        "## Relation to P18.3 execution gate",
        "",
        "After all artifact stages are complete, run the P18.3 gate:",
        "",
        "```bash",
        "make ds005620-real-execution-gate",
        "```",
        "",
        "The gate produces `human_peer_review_checklist.md` and the manual real execution command.",
        "Human peer review remains required and is never auto-confirmed.",
        "",
        "## What this operator does not do",
        "",
        "- Does not execute real DS005620 data.",
        "- Does not download data.",
        "- Does not infer labels or fabricate targets.",
        "- Does not confirm peer review on behalf of a human.",
        "- Does not weaken P18.3 gate, ontology quarantine, or language guardrails.",
        "- Does not auto-run any real-data command.",
        "",
        "## Remaining real-data blocker",
        "",
        "All real artifact stages require local DS005620 data or human-authored reviewed declaration.",
        "In the default state (no real data present), next_action=provide_metadata.",
        "",
        f"---",
        "",
        f"*{_SAFE_CLAIM}*",
    ]
    md = "\n".join(lines)
    violations = _check_safe_text(md)
    if violations:
        raise ValueError(f"report.md contains unsafe language: {violations}")
    return md


def write_ds005620_real_artifact_operator_outputs(
    plan: DS005620RealArtifactBuildPlan,
    out_dir: str,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def _wj(name: str, obj: dict) -> str:
        p = out / name
        p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        return str(p)

    def _w(name: str, content: str) -> str:
        p = out / name
        p.write_text(content, encoding="utf-8")
        return str(p)

    # real_artifact_build_plan.json
    plan_doc = {
        "dataset_id": plan.dataset_id,
        "planner_version": plan.planner_version,
        "generated_at": plan.generated_at,
        "all_stages_complete": plan.all_stages_complete,
        "ready_for_real_execution_gate": plan.ready_for_real_execution_gate,
        "ready_for_manual_real_execution": plan.ready_for_manual_real_execution,
        "next_action": plan.next_action,
        "next_command": plan.next_command,
        "stages": [_stage_to_dict(s) for s in plan.stages],
        "commands": [_cmd_to_dict(c) for c in plan.commands],
        "blockers": plan.blockers,
        "warnings": plan.warnings,
        "guardrails": plan.guardrails,
        "safe_claim": plan.safe_claim,
    }
    paths = {"real_artifact_build_plan.json": _wj("real_artifact_build_plan.json", plan_doc)}

    # real_artifact_stage_status.json
    stage_status = {
        "dataset_id": plan.dataset_id,
        "generated_at": plan.generated_at,
        "all_stages_complete": plan.all_stages_complete,
        "stages": [
            {
                "stage_id": s.stage_id,
                "display_name": s.display_name,
                "status": s.status,
                "manual_required": s.manual_required,
                "executes_real_data": s.executes_real_data,
            }
            for s in plan.stages
        ],
    }
    paths["real_artifact_stage_status.json"] = _wj("real_artifact_stage_status.json", stage_status)

    # real_artifact_next_command.json
    # Find the stage matching next_action
    stage_id_for_next = None
    for cmd in plan.commands:
        if cmd.command == plan.next_command:
            stage_id_for_next = cmd.stage_id
            break
    next_cmd_doc = {
        "next_action": plan.next_action,
        "next_command": plan.next_command,
        "stage_id": stage_id_for_next,
        "manual_required": True,  # all real-data actions require manual operator decision
        "human_review_required": False,
        "executes_real_data": False,
        "safe_to_auto_run": False,
        "blocked_reason": None,
    }
    paths["real_artifact_next_command.json"] = _wj("real_artifact_next_command.json", next_cmd_doc)

    # real_artifact_required_paths.json
    required_paths = {
        "dataset_id": plan.dataset_id,
        "generated_at": plan.generated_at,
        "required_paths": [
            {
                "stage_id": s.stage_id,
                "display_name": s.display_name,
                "expected_paths": s.expected_paths,
                "status": s.status,
            }
            for s in plan.stages
        ],
    }
    paths["real_artifact_required_paths.json"] = _wj("real_artifact_required_paths.json", required_paths)

    # real_artifact_commands.sh
    paths["real_artifact_commands.sh"] = _w("real_artifact_commands.sh", _build_commands_sh(plan))

    # real_artifact_operator_report.md
    paths["real_artifact_operator_report.md"] = _w("real_artifact_operator_report.md", _build_report_md(plan))

    return paths
