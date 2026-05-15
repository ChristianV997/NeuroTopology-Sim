"""
Generic real artifact build operator (P22).

Generalizes the DS005620 P20 operator to work on any registered dataset.
Inspects local prerequisite artifacts and emits per-stage status plus the
next manual command. Never executes real data, never downloads, never
infers labels, never auto-confirms peer review.

stdlib only.
"""
from __future__ import annotations

import hashlib
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


_PLANNER_VERSION = "p22.0"

_FORBIDDEN_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]


@dataclass
class GenericDatasetArtifactStage:
    stage_id: str
    display_name: str
    expected_paths: list
    status: str
    blockers: list
    warnings: list
    next_command: str
    manual_required: bool
    human_review_required: bool
    executes_real_data: bool
    downloads_data: bool
    safe_to_auto_run: bool
    artifact_hashes: dict
    checked_at: str


@dataclass
class GenericDatasetArtifactCommand:
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
class GenericDatasetArtifactPlan:
    dataset_id: str
    planner_version: str
    generated_at: str
    profile_supported: bool
    all_stages_complete: bool
    ready_for_real_execution_gate: bool
    next_action: str
    next_command: str
    stages: list
    commands: list
    blockers: list
    warnings: list
    guardrails: dict


@dataclass
class GenericDatasetArtifactOperatorResult:
    plan: GenericDatasetArtifactPlan
    output_paths: dict = field(default_factory=dict)


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_path(p: Path) -> Optional[str]:
    try:
        if p.is_file():
            return hashlib.sha256(p.read_bytes()).hexdigest()
        if p.is_dir():
            names = sorted(x.name for x in p.iterdir())
            return hashlib.sha256("\n".join(names).encode()).hexdigest()
    except Exception:
        return None
    return None


def _check_safe(text: str) -> list:
    lower = text.lower()
    return [p for p in _FORBIDDEN_PHRASES if p in lower]


def _inspect(
    stage_id: str,
    display_name: str,
    paths: list,
    next_command: str,
    *,
    manual_required: bool = False,
    human_review_required: bool = False,
    executes_real_data: bool = False,
    downloads_data: bool = False,
    safe_to_auto_run: bool = False,
    blocked_reason: Optional[str] = None,
) -> GenericDatasetArtifactStage:
    hashes: dict = {}
    all_exist = True
    for raw in paths:
        p = Path(raw)
        if p.exists():
            hashes[raw] = _hash_path(p)
        else:
            all_exist = False
            hashes[raw] = None

    blockers: list = []
    if blocked_reason:
        blockers.append(blocked_reason)

    if blocked_reason:
        status = "blocked"
    elif all_exist:
        status = "complete"
    elif manual_required:
        status = "manual_required"
    else:
        status = "missing"

    return GenericDatasetArtifactStage(
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
        checked_at=_ts_now(),
    )


def _build_stages(
    profile: DatasetProfile,
    cfg: DatasetRealPathConfig,
) -> list:
    ds = profile.dataset_id
    stages = []

    # 1. local_root
    stages.append(_inspect(
        stage_id="local_root",
        display_name="Local dataset root directory",
        paths=[cfg.local_root],
        next_command=f"Place local {ds} dataset under {cfg.local_root}",
        manual_required=True,
    ))

    # 2. metadata
    stages.append(_inspect(
        stage_id="metadata",
        display_name=f"{ds} events metadata file",
        paths=[cfg.metadata_path],
        next_command=f"Place {ds} metadata at {cfg.metadata_path}",
        manual_required=True,
    ))

    # 3. raw_eeg
    stages.append(_inspect(
        stage_id="raw_eeg",
        display_name=f"{ds} raw EEG files",
        paths=[cfg.raw_eeg_root],
        next_command=f"Place local {ds} EEG files under {cfg.raw_eeg_root}",
        manual_required=True,
    ))

    # 4. label_contract_declaration
    stages.append(_inspect(
        stage_id="label_contract_declaration",
        display_name="Human-authored activation declaration",
        paths=[cfg.reviewed_contract_source],
        next_command=(
            f"Author {ds} activation declaration and place at "
            f"{cfg.reviewed_contract_source}"
        ),
        manual_required=True,
        human_review_required=True,
    ))

    # 5. reviewed_contract (materialized)
    if ds == "DS005620":
        materialize_cmd = (
            "python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract "
            f"--declaration {cfg.reviewed_contract_source} "
            "--out outputs/btc_icft/ds005620_reviewed_contract"
        )
        ms = _inspect(
            stage_id="reviewed_contract",
            display_name="Materialized reviewed contract",
            paths=[cfg.reviewed_contract_materialized],
            next_command=materialize_cmd,
            human_review_required=True,
        )
    else:
        ms = _inspect(
            stage_id="reviewed_contract",
            display_name="Materialized reviewed contract",
            paths=[cfg.reviewed_contract_materialized],
            next_command=(
                f"Implement {ds}-specific reviewed contract materializer; "
                "no generic materializer is wired yet."
            ),
            human_review_required=True,
            blocked_reason="blocked_dataset_specific_support_required",
        )
        ms.status = "blocked_dataset_specific_support_required"
    stages.append(ms)

    # 6. reader_preflight
    stages.append(_inspect(
        stage_id="reader_preflight",
        display_name="EEG reader preflight output",
        paths=[cfg.reader_preflight_path],
        next_command=(
            "python -m sciencer_d.btc_icft.pipelines.preflight_eeg_readers "
            f"--dataset-id {ds} --root {cfg.raw_eeg_root} "
            f"--out {cfg.reader_preflight_path}"
        ),
        executes_real_data=True,
    ))

    # 7. mne_extraction
    if ds == "DS005620":
        mne_cmd = (
            "python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks "
            f"--dataset-id {ds} --input <first_eeg_file> "
            f"--out {cfg.mne_extract_path}"
        )
        ms = _inspect(
            stage_id="mne_extraction",
            display_name="MNE signal extraction output",
            paths=[cfg.mne_extract_path],
            next_command=mne_cmd,
            executes_real_data=True,
        )
    else:
        ms = _inspect(
            stage_id="mne_extraction",
            display_name="MNE signal extraction output",
            paths=[cfg.mne_extract_path],
            next_command=(
                f"Implement {ds}-specific MNE extraction wrapper; "
                "no generic real extractor is wired yet."
            ),
            executes_real_data=True,
            blocked_reason="blocked_dataset_specific_support_required",
        )
        ms.status = "blocked_dataset_specific_support_required"
    stages.append(ms)

    # 8. canonical_signal_blocks
    if ds == "DS005620":
        cb_cmd = (
            "python -m sciencer_d.btc_icft.pipelines.convert_mne_to_signal_blocks "
            f"--dataset-id {ds} --mne-extract {cfg.mne_extract_path} "
            f"--out {cfg.signal_blocks_path}"
        )
        ms = _inspect(
            stage_id="canonical_signal_blocks",
            display_name="Canonical signal blocks (P19.2)",
            paths=[cfg.signal_blocks_path],
            next_command=cb_cmd,
            executes_real_data=True,
        )
    else:
        ms = _inspect(
            stage_id="canonical_signal_blocks",
            display_name="Canonical signal blocks (P19.2)",
            paths=[cfg.signal_blocks_path],
            next_command=(
                f"Implement {ds}-specific signal-block conversion; "
                "no generic real converter is wired yet."
            ),
            executes_real_data=True,
            blocked_reason="blocked_dataset_specific_support_required",
        )
        ms.status = "blocked_dataset_specific_support_required"
    stages.append(ms)

    # 9. level_m_features
    if ds == "DS005620":
        lm_cmd = (
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal "
            f"--dataset-id {ds} --signal-blocks {cfg.signal_blocks_path} "
            f"--out {str(Path(cfg.level_m_csv_path).parent)}"
        )
        ms = _inspect(
            stage_id="level_m_features",
            display_name="Level M signal features",
            paths=[cfg.level_m_csv_path],
            next_command=lm_cmd,
            executes_real_data=True,
        )
    else:
        ms = _inspect(
            stage_id="level_m_features",
            display_name="Level M signal features",
            paths=[cfg.level_m_csv_path],
            next_command=(
                f"Implement {ds}-specific Level M feature extraction; "
                "no generic real extractor is wired yet."
            ),
            executes_real_data=True,
            blocked_reason="blocked_dataset_specific_support_required",
        )
        ms.status = "blocked_dataset_specific_support_required"
    stages.append(ms)

    # 10. level_t_features
    if ds == "DS005620":
        lt_cmd = (
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal "
            f"--dataset-id {ds} --signal-blocks {cfg.signal_blocks_path} "
            f"--out {str(Path(cfg.level_t_csv_path).parent)}"
        )
        ms = _inspect(
            stage_id="level_t_features",
            display_name="Level T topology features",
            paths=[cfg.level_t_csv_path],
            next_command=lt_cmd,
            executes_real_data=True,
        )
    else:
        ms = _inspect(
            stage_id="level_t_features",
            display_name="Level T topology features",
            paths=[cfg.level_t_csv_path],
            next_command=(
                f"Implement {ds}-specific Level T topology extraction; "
                "no generic real extractor is wired yet."
            ),
            executes_real_data=True,
            blocked_reason="blocked_dataset_specific_support_required",
        )
        ms.status = "blocked_dataset_specific_support_required"
    stages.append(ms)

    # 11. real_execution_gate
    if ds == "DS005620":
        stages.append(_inspect(
            stage_id="real_execution_gate",
            display_name="Real/local execution gate output",
            paths=[cfg.real_execution_gate_path],
            next_command="make ds005620-real-execution-gate",
            human_review_required=True,
        ))
    else:
        stages.append(_inspect(
            stage_id="real_execution_gate",
            display_name="Real/local execution gate output",
            paths=[cfg.real_execution_gate_path],
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution "
                "(generic gate runs as part of this planner)"
            ),
            human_review_required=True,
        ))

    return stages


def _build_commands(stages: list) -> list:
    cmds = []
    for s in stages:
        cmds.append(GenericDatasetArtifactCommand(
            stage_id=s.stage_id,
            command=s.next_command,
            manual_required=s.manual_required,
            human_review_required=s.human_review_required,
            executes_real_data=s.executes_real_data,
            downloads_data=s.downloads_data,
            safe_to_auto_run=False,
            blocked_reason=s.blockers[0] if s.blockers else None,
            description=s.display_name,
        ))
    return cmds


def _determine_next_action(stages: list) -> tuple:
    smap = {s.stage_id: s for s in stages}

    def _ok(sid: str) -> bool:
        return smap[sid].status == "complete"

    def _blocked(sid: str) -> bool:
        return smap[sid].status == "blocked_dataset_specific_support_required"

    if not _ok("local_root"):
        return ("provide_local_root", smap["local_root"].next_command)
    if not _ok("metadata"):
        return ("provide_metadata", smap["metadata"].next_command)
    if not _ok("raw_eeg"):
        return ("provide_raw_eeg", smap["raw_eeg"].next_command)
    if not _ok("label_contract_declaration"):
        return (
            "prepare_label_contract_declaration",
            smap["label_contract_declaration"].next_command,
        )
    if _blocked("reviewed_contract"):
        return (
            "implement_dataset_specific_contract_materializer",
            smap["reviewed_contract"].next_command,
        )
    if not _ok("reviewed_contract"):
        return ("run_reviewed_contract_materializer", smap["reviewed_contract"].next_command)
    if not _ok("reader_preflight"):
        return ("run_reader_preflight", smap["reader_preflight"].next_command)
    if _blocked("mne_extraction"):
        return (
            "implement_dataset_specific_executor",
            smap["mne_extraction"].next_command,
        )
    if not _ok("mne_extraction"):
        return ("run_mne_extraction", smap["mne_extraction"].next_command)
    if not _ok("canonical_signal_blocks"):
        return (
            "run_signal_block_conversion",
            smap["canonical_signal_blocks"].next_command,
        )
    if not _ok("level_m_features"):
        return ("run_level_m_signal", smap["level_m_features"].next_command)
    if not _ok("level_t_features"):
        return ("run_level_t_signal", smap["level_t_features"].next_command)
    if not _ok("real_execution_gate"):
        return ("run_real_execution_gate", smap["real_execution_gate"].next_command)
    return ("human_peer_review_required",
            "Human reviewer must inspect gate outputs before any manual real execution.")


def build_generic_real_artifact_plan(
    profile: DatasetProfile,
) -> GenericDatasetArtifactPlan:
    cfg = build_dataset_path_config(profile)
    stages = _build_stages(profile, cfg)
    commands = _build_commands(stages)

    pre_gate = [s for s in stages if s.stage_id != "real_execution_gate"]
    ready_for_gate = all(s.status == "complete" for s in pre_gate)
    all_complete = all(s.status == "complete" for s in stages)

    next_action, next_cmd = _determine_next_action(stages)

    all_blockers = []
    for s in stages:
        for b in s.blockers:
            all_blockers.append(f"{s.stage_id}:{b}")

    return GenericDatasetArtifactPlan(
        dataset_id=profile.dataset_id,
        planner_version=_PLANNER_VERSION,
        generated_at=_ts_now(),
        profile_supported=profile.generic_artifact_operator_supported,
        all_stages_complete=all_complete,
        ready_for_real_execution_gate=ready_for_gate,
        next_action=next_action,
        next_command=next_cmd,
        stages=stages,
        commands=commands,
        blockers=all_blockers,
        warnings=[],
        guardrails={
            "executes_real_data_automatically": False,
            "downloads_data": False,
            "auto_confirms_peer_review": False,
            "infers_labels": False,
            "fabricates_targets": False,
            "modifies_p18_3_gate": False,
        },
    )


def stage_to_dict(s: GenericDatasetArtifactStage) -> dict:
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
        "checked_at": s.checked_at,
    }


def command_to_dict(c: GenericDatasetArtifactCommand) -> dict:
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


def plan_to_dict(plan: GenericDatasetArtifactPlan) -> dict:
    return {
        "dataset_id": plan.dataset_id,
        "planner_version": plan.planner_version,
        "generated_at": plan.generated_at,
        "profile_supported": plan.profile_supported,
        "all_stages_complete": plan.all_stages_complete,
        "ready_for_real_execution_gate": plan.ready_for_real_execution_gate,
        "next_action": plan.next_action,
        "next_command": plan.next_command,
        "stages": [stage_to_dict(s) for s in plan.stages],
        "commands": [command_to_dict(c) for c in plan.commands],
        "blockers": plan.blockers,
        "warnings": plan.warnings,
        "guardrails": plan.guardrails,
    }


def write_generic_artifact_operator_outputs(
    plan: GenericDatasetArtifactPlan,
    out_dir: str,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}

    doc = plan_to_dict(plan)
    p = out / "real_artifact_build_plan.json"
    p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    paths["real_artifact_build_plan.json"] = str(p)

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
    p = out / "real_artifact_stage_status.json"
    p.write_text(json.dumps(stage_status, indent=2) + "\n", encoding="utf-8")
    paths["real_artifact_stage_status.json"] = str(p)

    next_cmd_doc = {
        "dataset_id": plan.dataset_id,
        "next_action": plan.next_action,
        "next_command": plan.next_command,
        "manual_required": True,
        "human_review_required": False,
        "executes_real_data": False,
        "safe_to_auto_run": False,
    }
    p = out / "real_artifact_next_command.json"
    p.write_text(json.dumps(next_cmd_doc, indent=2) + "\n", encoding="utf-8")
    paths["real_artifact_next_command.json"] = str(p)

    return paths
