"""
DS005620 real/local execution gate (P18.3).

Inspects whether a human operator may proceed toward a real DS005620 run.
Does NOT execute real data, download data, infer labels, or confirm human review.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_STRICT_JOIN_KEYS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
]

_FORBIDDEN_PHRASES = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]

_SAFE_CLAIM = (
    "P18.3 adds a deterministic real/local execution gate that inspects DS005620 "
    "prerequisites and prepares human-reviewed execution commands without running "
    "real data or weakening label/target/ontology guardrails."
)

_CHECKLIST_ITEMS = [
    {"id": "C01", "text": "Metadata provenance verified by reviewer."},
    {"id": "C02", "text": "explicit_label_column verified against metadata by reviewer."},
    {"id": "C03", "text": "positive_values verified by human reviewer."},
    {"id": "C04", "text": "negative_values verified by human reviewer."},
    {"id": "C05", "text": "Both label classes confirmed present in metadata by reviewer."},
    {"id": "C06", "text": "No sedation/experience shortcut labels used (not filename-derived, not topology-derived, not artifact-derived)."},
    {"id": "C07", "text": "No responsiveness/state shortcut labels used."},
    {"id": "C08", "text": "No filename-derived labels confirmed absent."},
    {"id": "C09", "text": "No topology-derived labels confirmed absent."},
    {"id": "C10", "text": "No artifact-derived labels confirmed absent."},
    {"id": "C11", "text": "Join keys verified to match P12/P13/P11 expectations."},
    {"id": "C12", "text": "Contract JSON reviewed and confirmed structurally sound by reviewer."},
    {"id": "C13", "text": "P12 alignment expected to use only explicit labels from reviewed contract."},
    {"id": "C14", "text": "P13 target injection expected to use only P12 alignment outputs."},
    {"id": "C15", "text": "P11 expected to consume P13 features_m_signal_labeled.csv only."},
    {"id": "C16", "text": "Real execution does not validate empirical claims without null comparisons, ablations, leakage checks, and artifact reports."},
    {"id": "C17", "text": "Ontology evaluation scope remains limited by claim-scope rules after real execution."},
    {"id": "C18", "text": "Substrate/theory/ontology candidates remain under claim-scope quarantine without independent mechanism evidence."},
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DS005620RealLocalPathConfig:
    dataset_id: str
    metadata_path: str
    reviewed_contract_path: str
    mne_extract_path: str
    signal_blocks_path: str
    level_m_csv_path: str
    level_t_csv_path: str
    execution_root: str


@dataclass
class DS005620ArtifactGateCheck:
    group_id: str
    display_name: str
    expected_paths: list[str]
    required: bool
    exists: bool
    ready: bool
    blockers: list[str]
    warnings: list[str]
    next_command: str
    artifact_hashes: dict[str, Optional[str]]
    size_bytes: int
    checked_at: str


@dataclass
class DS005620ContractReviewGate:
    contract_path: str
    exists: bool
    static_gate_passed: bool
    blockers: list[str]
    warnings: list[str]
    dataset_id: Optional[str]
    contract_status: Optional[str]
    explicit_label_column: Optional[str]
    positive_value_count: int
    negative_value_count: int
    join_keys_present: list[str]
    join_keys_missing: list[str]
    requires_human_review: bool = True
    human_review_confirmed_by_gate: bool = False


@dataclass
class DS005620RealExecutionCommandPlan:
    command: str
    command_parts: list[str]
    requires_human_confirmation: bool = True
    not_executed_by_gate: bool = True
    can_run_now: bool = False
    description: str = ""


@dataclass
class DS005620RealExecutionGateResult:
    dataset_id: str
    ready_for_real_execution: bool
    ready_for_p18_1_execute: bool
    reviewed_contract_static_gate_passed: bool
    all_required_artifacts_present: bool
    peer_review_required: bool
    peer_review_confirmed_by_human: bool
    can_use_execute_flag: bool
    can_use_peer_reviewed_contract_confirmed_flag: bool
    blockers: list[str]
    warnings: list[str]
    next_action: str
    next_command: str
    real_execution_command: str
    generated_at: str
    artifact_checks: list[DS005620ArtifactGateCheck] = field(default_factory=list)
    contract_gate: Optional[DS005620ContractReviewGate] = None
    command_plan: Optional[DS005620RealExecutionCommandPlan] = None
    missing_groups: list[str] = field(default_factory=list)
    safe_claim: str = _SAFE_CLAIM


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


def _sha256_dir_listing(path: Path) -> Optional[str]:
    try:
        names = sorted(p.name for p in path.iterdir())
        return hashlib.sha256("\n".join(names).encode()).hexdigest()
    except Exception:
        return None


def _size_bytes(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            return sum(f.stat().st_size for f in path.iterdir() if f.is_file())
    except Exception:
        pass
    return 0


def validate_gate_safe_text(text: str) -> list[str]:
    lower = text.lower()
    return [p for p in _FORBIDDEN_PHRASES if p in lower]


# ---------------------------------------------------------------------------
# Artifact group inspection
# ---------------------------------------------------------------------------

def inspect_real_local_artifact_group(
    group_id: str,
    display_name: str,
    paths: list[str],
    required: bool,
    next_command: str,
) -> DS005620ArtifactGateCheck:
    ts = _ts_now()
    blockers: list[str] = []
    warnings: list[str] = []
    hashes: dict[str, Optional[str]] = {}
    total_size = 0

    all_exist = True
    for raw in paths:
        p = Path(raw)
        if p.exists():
            if p.is_file():
                hashes[raw] = _sha256_file(p)
            elif p.is_dir():
                hashes[raw] = _sha256_dir_listing(p)
            total_size += _size_bytes(p)
        else:
            all_exist = False
            hashes[raw] = None
            if required:
                blockers.append(f"missing: {raw}")

    ready = all_exist and not blockers

    return DS005620ArtifactGateCheck(
        group_id=group_id,
        display_name=display_name,
        expected_paths=paths,
        required=required,
        exists=all_exist,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        next_command=next_command,
        artifact_hashes=hashes,
        size_bytes=total_size,
        checked_at=ts,
    )


# ---------------------------------------------------------------------------
# Reviewed contract static gate
# ---------------------------------------------------------------------------

def inspect_reviewed_contract_static_gate(contract_path: str) -> DS005620ContractReviewGate:
    p = Path(contract_path)
    blockers: list[str] = []
    warnings: list[str] = []

    if not p.exists():
        return DS005620ContractReviewGate(
            contract_path=contract_path,
            exists=False,
            static_gate_passed=False,
            blockers=["reviewed_contract not found"],
            warnings=[],
            dataset_id=None,
            contract_status=None,
            explicit_label_column=None,
            positive_value_count=0,
            negative_value_count=0,
            join_keys_present=[],
            join_keys_missing=list(_STRICT_JOIN_KEYS),
        )

    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return DS005620ContractReviewGate(
            contract_path=contract_path,
            exists=True,
            static_gate_passed=False,
            blockers=[f"contract parse error: {exc}"],
            warnings=[],
            dataset_id=None,
            contract_status=None,
            explicit_label_column=None,
            positive_value_count=0,
            negative_value_count=0,
            join_keys_present=[],
            join_keys_missing=list(_STRICT_JOIN_KEYS),
        )

    ds_id = payload.get("dataset_id")
    if ds_id != "DS005620":
        blockers.append(f"dataset_id is {ds_id!r}, expected 'DS005620'")

    status = payload.get("contract_status", "")
    if status != "active_reviewed_external_contract":
        blockers.append(f"contract_status is {status!r}, expected 'active_reviewed_external_contract'")

    label_col = payload.get("explicit_label_column", "")
    if not label_col:
        blockers.append("explicit_label_column missing or empty")

    pos_vals = payload.get("positive_values", [])
    neg_vals = payload.get("negative_values", [])
    if not pos_vals:
        blockers.append("positive_values missing or empty")
    if not neg_vals:
        blockers.append("negative_values missing or empty")

    pos_set = set(pos_vals)
    neg_set = set(neg_vals)
    overlap = pos_set & neg_set
    if overlap:
        blockers.append(f"positive_values and negative_values overlap: {sorted(overlap)}")

    jk = payload.get("join_keys", [])
    jk_set = set(jk)
    present = [k for k in _STRICT_JOIN_KEYS if k in jk_set]
    missing = [k for k in _STRICT_JOIN_KEYS if k not in jk_set]
    if missing:
        blockers.append(f"join_keys missing required keys: {missing}")

    # Shortcut indicators — any of these being true blocks the gate
    shortcut_checks = [
        ("label_inference_enabled", True),
        ("targets_fabricated", True),
        ("filename_derived_labels", True),
        ("topology_derived_labels", True),
        ("artifact_derived_labels", True),
        ("automatic_activation", True),
    ]
    for key, bad_val in shortcut_checks:
        if payload.get(key) == bad_val:
            blockers.append(f"shortcut indicator set: {key}={bad_val}")

    # Safe-language check on the serialized contract
    violations = validate_gate_safe_text(json.dumps(payload))
    for v in violations:
        blockers.append(f"unsafe language in contract: {v!r}")

    return DS005620ContractReviewGate(
        contract_path=contract_path,
        exists=True,
        static_gate_passed=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
        dataset_id=ds_id,
        contract_status=status,
        explicit_label_column=label_col or None,
        positive_value_count=len(pos_vals),
        negative_value_count=len(neg_vals),
        join_keys_present=present,
        join_keys_missing=missing,
    )


# ---------------------------------------------------------------------------
# Command plan
# ---------------------------------------------------------------------------

def build_real_execution_command_plan(cfg: DS005620RealLocalPathConfig) -> DS005620RealExecutionCommandPlan:
    parts = [
        "python", "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
        "--dataset-id", cfg.dataset_id,
        "--reviewed-contract", cfg.reviewed_contract_path,
        "--metadata", cfg.metadata_path,
        "--level-m", str(Path(cfg.level_m_csv_path).parent),
        "--level-t", str(Path(cfg.level_t_csv_path).parent),
        "--out", cfg.execution_root,
        "--execute",
        "--peer-reviewed-contract-confirmed",
    ]
    cmd = " \\\n  ".join(parts)
    return DS005620RealExecutionCommandPlan(
        command=cmd,
        command_parts=parts,
        requires_human_confirmation=True,
        not_executed_by_gate=True,
        can_run_now=False,
        description=(
            "Manual real execution command. DO NOT RUN automatically. "
            "Requires human peer-review confirmation of all checklist items first."
        ),
    )


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

def build_default_real_local_path_config(
    dataset_id: str = "DS005620",
    metadata: Optional[str] = None,
    reviewed_contract: Optional[str] = None,
    mne_extract: Optional[str] = None,
    signal_blocks: Optional[str] = None,
    level_m: Optional[str] = None,
    level_t: Optional[str] = None,
    execution_root: Optional[str] = None,
) -> DS005620RealLocalPathConfig:
    return DS005620RealLocalPathConfig(
        dataset_id=dataset_id,
        metadata_path=metadata or "data/DS005620/events.tsv",
        reviewed_contract_path=(
            reviewed_contract
            or "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json"
        ),
        mne_extract_path=mne_extract or "outputs/btc_icft/eeg_mne_extract/DS005620",
        signal_blocks_path=(
            signal_blocks
            or "outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620"
        ),
        level_m_csv_path=(
            level_m
            or "outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv"
        ),
        level_t_csv_path=(
            level_t
            or "outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv"
        ),
        execution_root=(
            execution_root
            or "outputs/btc_icft/ds005620_real_benchmark_execution"
        ),
    )


# ---------------------------------------------------------------------------
# Next-action logic
# ---------------------------------------------------------------------------

_NEXT_ACTIONS = [
    "provide_metadata",
    "run_p17_1_reviewed_contract_materializer",
    "fix_reviewed_contract",
    "run_p19_1_mne_extraction",
    "run_p19_2_signal_block_conversion",
    "run_p9_level_m_signal",
    "run_p10_level_t_signal",
    "human_peer_review_required",
]


def _determine_next_action(
    checks: dict[str, DS005620ArtifactGateCheck],
    contract_gate: DS005620ContractReviewGate,
) -> tuple[str, str]:
    if not checks["metadata"].ready:
        return (
            "provide_metadata",
            "Place DS005620 metadata at data/DS005620/events.tsv",
        )
    if not checks["reviewed_contract"].exists:
        return (
            "run_p17_1_reviewed_contract_materializer",
            (
                "python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract"
                " # See docs/ds005620_real_local_operator_runbook.md Step 2"
            ),
        )
    if not contract_gate.static_gate_passed:
        return (
            "fix_reviewed_contract",
            "Review blockers in human_peer_review_checklist.md and regenerate p12_external_contract.json",
        )
    if not checks["mne_extract"].ready:
        return (
            "run_p19_1_mne_extraction",
            "python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks --dataset-id DS005620",
        )
    if not checks["signal_blocks"].ready:
        return (
            "run_p19_2_signal_block_conversion",
            "python -m sciencer_d.btc_icft.pipelines.convert_mne_signal_blocks --dataset-id DS005620",
        )
    if not checks["level_m"].ready:
        return (
            "run_p9_level_m_signal",
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal --dataset-id DS005620",
        )
    if not checks["level_t"].ready:
        return (
            "run_p10_level_t_signal",
            "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal --dataset-id DS005620",
        )
    return (
        "human_peer_review_required",
        (
            "Human reviewer must inspect human_peer_review_checklist.md "
            "before manually running the real execution command."
        ),
    )


# ---------------------------------------------------------------------------
# Main gate builder
# ---------------------------------------------------------------------------

def build_real_local_execution_gate(cfg: DS005620RealLocalPathConfig) -> DS005620RealExecutionGateResult:
    ts = _ts_now()

    # --- Artifact checks ---
    checks_list = [
        inspect_real_local_artifact_group(
            group_id="metadata",
            display_name="DS005620 metadata (events.tsv)",
            paths=[cfg.metadata_path],
            required=True,
            next_command="Place DS005620 metadata at data/DS005620/events.tsv",
        ),
        inspect_real_local_artifact_group(
            group_id="reviewed_contract",
            display_name="Reviewed external label contract (P17.1)",
            paths=[cfg.reviewed_contract_path],
            required=True,
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract"
            ),
        ),
        inspect_real_local_artifact_group(
            group_id="mne_extract",
            display_name="MNE signal extraction output directory",
            paths=[cfg.mne_extract_path],
            required=True,
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks --dataset-id DS005620"
            ),
        ),
        inspect_real_local_artifact_group(
            group_id="signal_blocks",
            display_name="Canonical signal blocks directory",
            paths=[cfg.signal_blocks_path],
            required=True,
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.convert_mne_signal_blocks --dataset-id DS005620"
            ),
        ),
        inspect_real_local_artifact_group(
            group_id="level_m",
            display_name="Level M signal features (features_m_signal.csv)",
            paths=[cfg.level_m_csv_path],
            required=True,
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal --dataset-id DS005620"
            ),
        ),
        inspect_real_local_artifact_group(
            group_id="level_t",
            display_name="Level T topology features (features_t_signal.csv)",
            paths=[cfg.level_t_csv_path],
            required=True,
            next_command=(
                "python -m sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal --dataset-id DS005620"
            ),
        ),
    ]

    checks = {c.group_id: c for c in checks_list}
    missing_groups = [c.group_id for c in checks_list if not c.ready]

    # --- Contract static gate ---
    contract_gate = inspect_reviewed_contract_static_gate(cfg.reviewed_contract_path)

    # --- Next action ---
    next_action, next_cmd = _determine_next_action(checks, contract_gate)

    # --- Aggregate blockers ---
    all_required_present = all(c.ready for c in checks_list if c.required)
    blockers: list[str] = []
    for c in checks_list:
        blockers.extend(c.blockers)
    blockers.extend(contract_gate.blockers)

    warnings: list[str] = []

    # Readiness: only when all artifacts present and contract static gate passes
    artifact_ready = all_required_present and contract_gate.static_gate_passed
    # But peer review is always still required — gate never auto-confirms it
    ready_for_execution = artifact_ready  # artifact/static only — NOT human-confirmed

    # Build command plan (always — so operators can see the exact command)
    command_plan = build_real_execution_command_plan(cfg)

    return DS005620RealExecutionGateResult(
        dataset_id=cfg.dataset_id,
        ready_for_real_execution=ready_for_execution,
        ready_for_p18_1_execute=ready_for_execution,
        reviewed_contract_static_gate_passed=contract_gate.static_gate_passed,
        all_required_artifacts_present=all_required_present,
        peer_review_required=True,
        peer_review_confirmed_by_human=False,
        can_use_execute_flag=False,
        can_use_peer_reviewed_contract_confirmed_flag=False,
        blockers=blockers,
        warnings=warnings,
        next_action=next_action,
        next_command=next_cmd,
        real_execution_command=command_plan.command,
        generated_at=ts,
        artifact_checks=checks_list,
        contract_gate=contract_gate,
        command_plan=command_plan,
        missing_groups=missing_groups,
        safe_claim=_SAFE_CLAIM,
    )


# ---------------------------------------------------------------------------
# Checklist builders
# ---------------------------------------------------------------------------

def _build_checklist_json(result: DS005620RealExecutionGateResult) -> dict:
    return {
        "dataset_id": result.dataset_id,
        "peer_review_required": True,
        "human_review_confirmed_by_gate": False,
        "all_required_artifacts_present": result.all_required_artifacts_present,
        "reviewed_contract_static_gate_passed": result.reviewed_contract_static_gate_passed,
        "checklist": _CHECKLIST_ITEMS,
        "generated_at": result.generated_at,
        "safe_claim": _SAFE_CLAIM,
    }


def _build_checklist_md(result: DS005620RealExecutionGateResult) -> str:
    lines = [
        "# DS005620 Human Peer Review Checklist",
        "",
        "**This checklist must be completed by a human reviewer before real execution.**",
        "",
        f"- dataset_id: `{result.dataset_id}`",
        f"- all_required_artifacts_present: `{result.all_required_artifacts_present}`",
        f"- reviewed_contract_static_gate_passed: `{result.reviewed_contract_static_gate_passed}`",
        f"- peer_review_confirmed_by_gate: `False`",
        "",
        "## Checklist Items",
        "",
    ]
    for item in _CHECKLIST_ITEMS:
        lines.append(f"- [ ] **{item['id']}**: {item['text']}")
    lines += [
        "",
        "## Important",
        "",
        "Completing this checklist does not automatically enable execution.",
        "The human reviewer must manually run the real execution command after confirming all items.",
        "",
        "## What this gate does not do",
        "",
        "- Does not execute real data.",
        "- Does not download data.",
        "- Does not infer labels.",
        "- Does not confirm peer review on behalf of a human reviewer.",
        "- Does not guarantee empirical validity — that requires null comparisons, ablations, leakage checks, and artifact reports.",
        "",
        "## Ontology scope reminder",
        "",
        "After real execution, ontology evaluation is still limited by claim-scope rules.",
        "Substrate/theory/ontology candidates remain under quarantine without independent mechanism evidence.",
        "",
        f"---",
        "",
        f"*Generated by P18.3 real/local execution gate — {result.generated_at}*",
    ]
    md = "\n".join(lines)
    violations = validate_gate_safe_text(md)
    if violations:
        raise ValueError(f"checklist markdown contains unsafe language: {violations}")
    return md


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report_md(result: DS005620RealExecutionGateResult) -> str:
    def yn(v: bool) -> str:
        return "`true`" if v else "`false`"

    lines = [
        "# DS005620 Real/Local Execution Gate",
        "",
        f"- dataset_id: `{result.dataset_id}`",
        f"- generated_at: `{result.generated_at}`",
        "",
        "## Artifact readiness",
        "",
    ]
    for c in result.artifact_checks:
        status = "READY" if c.ready else "MISSING"
        lines.append(f"- **{c.display_name}**: {status}")
        for b in c.blockers:
            lines.append(f"  - BLOCKER: {b}")
    lines += [
        "",
        "## Contract static gate",
        "",
        f"- exists: {yn(result.contract_gate.exists if result.contract_gate else False)}",
        f"- static_gate_passed: {yn(result.reviewed_contract_static_gate_passed)}",
    ]
    if result.contract_gate and result.contract_gate.blockers:
        lines.append("- blockers:")
        for b in result.contract_gate.blockers:
            lines.append(f"  - {b}")
    lines += [
        "",
        "## Human review requirement",
        "",
        "- peer_review_required: `true`",
        "- peer_review_confirmed_by_human: `false`",
        "- can_use_execute_flag: `false`",
        "- can_use_peer_reviewed_contract_confirmed_flag: `false`",
        "",
        "**Human reviewer must inspect `human_peer_review_checklist.md` before proceeding.**",
        "",
        "## Next action",
        "",
        f"- next_action: `{result.next_action}`",
        f"- next_command: `{result.next_command}`",
        "",
        "## Manual real execution command",
        "",
        "The command below is for manual use only after human peer review.",
        "It is NOT executed automatically by this gate.",
        "",
        "```bash",
        result.real_execution_command,
        "```",
        "",
        "## What this gate does not do",
        "",
        "- Does not execute real DS005620 data.",
        "- Does not download any data.",
        "- Does not infer labels or fabricate targets.",
        "- Does not confirm peer review on behalf of a human reviewer.",
        "- Does not modify ontology quarantine or claim scope.",
        "",
        "## Empirical controls still required",
        "",
        "Even after real execution, empirical validity requires:",
        "- Null comparisons",
        "- Ablation studies",
        "- Leakage reports",
        "- Artifact reports",
        "",
        "## Ontology claim scope reminder",
        "",
        "After real execution, ontology evaluation is still limited by claim-scope rules.",
        "Substrate/theory/ontology candidates remain under quarantine without independent mechanism evidence.",
        "",
        f"---",
        "",
        f"*{_SAFE_CLAIM}*",
    ]
    md = "\n".join(lines)
    violations = validate_gate_safe_text(md)
    if violations:
        raise ValueError(f"report.md contains unsafe language: {violations}")
    return md


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def write_real_local_execution_gate_outputs(
    result: DS005620RealExecutionGateResult,
    out_dir: str,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def _w(name: str, content: str) -> str:
        p = out / name
        p.write_text(content, encoding="utf-8")
        return str(p)

    def _wj(name: str, obj: dict) -> str:
        return _w(name, json.dumps(obj, indent=2) + "\n")

    # ready_for_real_execution.json
    ready_doc = {
        "dataset_id": result.dataset_id,
        "ready_for_real_execution": result.ready_for_real_execution,
        "ready_for_p18_1_execute": result.ready_for_p18_1_execute,
        "reviewed_contract_static_gate_passed": result.reviewed_contract_static_gate_passed,
        "all_required_artifacts_present": result.all_required_artifacts_present,
        "peer_review_required": True,
        "peer_review_confirmed_by_human": False,
        "can_use_execute_flag": False,
        "can_use_peer_reviewed_contract_confirmed_flag": False,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "next_action": result.next_action,
        "next_command": result.next_command,
        "real_execution_command": result.real_execution_command,
        "generated_at": result.generated_at,
        "safe_claim": result.safe_claim,
    }
    paths = {"ready_for_real_execution.json": _wj("ready_for_real_execution.json", ready_doc)}

    # real_execution_gate.json (detailed)
    def _check_to_dict(c: DS005620ArtifactGateCheck) -> dict:
        return {
            "group_id": c.group_id,
            "display_name": c.display_name,
            "expected_paths": c.expected_paths,
            "required": c.required,
            "exists": c.exists,
            "ready": c.ready,
            "blockers": c.blockers,
            "warnings": c.warnings,
            "next_command": c.next_command,
            "artifact_hashes": c.artifact_hashes,
            "size_bytes": c.size_bytes,
            "checked_at": c.checked_at,
        }

    gate_doc = {
        "dataset_id": result.dataset_id,
        "ready_for_real_execution": result.ready_for_real_execution,
        "all_required_artifacts_present": result.all_required_artifacts_present,
        "reviewed_contract_static_gate_passed": result.reviewed_contract_static_gate_passed,
        "peer_review_required": True,
        "peer_review_confirmed_by_human": False,
        "can_use_execute_flag": False,
        "can_use_peer_reviewed_contract_confirmed_flag": False,
        "next_action": result.next_action,
        "next_command": result.next_command,
        "missing_groups": result.missing_groups,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "artifact_checks": [_check_to_dict(c) for c in result.artifact_checks],
        "contract_gate": {
            "contract_path": result.contract_gate.contract_path if result.contract_gate else None,
            "exists": result.contract_gate.exists if result.contract_gate else False,
            "static_gate_passed": result.contract_gate.static_gate_passed if result.contract_gate else False,
            "blockers": result.contract_gate.blockers if result.contract_gate else [],
            "warnings": result.contract_gate.warnings if result.contract_gate else [],
            "dataset_id": result.contract_gate.dataset_id if result.contract_gate else None,
            "contract_status": result.contract_gate.contract_status if result.contract_gate else None,
            "explicit_label_column": result.contract_gate.explicit_label_column if result.contract_gate else None,
            "positive_value_count": result.contract_gate.positive_value_count if result.contract_gate else 0,
            "negative_value_count": result.contract_gate.negative_value_count if result.contract_gate else 0,
            "join_keys_present": result.contract_gate.join_keys_present if result.contract_gate else [],
            "join_keys_missing": result.contract_gate.join_keys_missing if result.contract_gate else [],
            "requires_human_review": True,
            "human_review_confirmed_by_gate": False,
        },
        "generated_at": result.generated_at,
        "safe_claim": result.safe_claim,
    }
    paths["real_execution_gate.json"] = _wj("real_execution_gate.json", gate_doc)

    # real_execution_command_plan.json
    cp = result.command_plan
    plan_doc = {
        "command": cp.command if cp else result.real_execution_command,
        "command_parts": cp.command_parts if cp else [],
        "requires_human_confirmation": True,
        "not_executed_by_gate": True,
        "can_run_now": False,
        "description": cp.description if cp else "",
    }
    paths["real_execution_command_plan.json"] = _wj("real_execution_command_plan.json", plan_doc)

    # human_peer_review_checklist.json / .md
    checklist_json = _build_checklist_json(result)
    paths["human_peer_review_checklist.json"] = _wj("human_peer_review_checklist.json", checklist_json)
    paths["human_peer_review_checklist.md"] = _w("human_peer_review_checklist.md", _build_checklist_md(result))

    # missing_artifacts.json
    missing_doc = {
        "dataset_id": result.dataset_id,
        "missing_groups": result.missing_groups,
        "missing_count": len(result.missing_groups),
        "generated_at": result.generated_at,
    }
    paths["missing_artifacts.json"] = _wj("missing_artifacts.json", missing_doc)

    # report.md
    paths["report.md"] = _w("report.md", _build_report_md(result))

    return paths
