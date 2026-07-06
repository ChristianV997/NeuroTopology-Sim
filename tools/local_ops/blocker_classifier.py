"""
Blocker classifier for the local ops action queue (P26).

Reads collected state (loaded JSONs) and source status, then classifies what is
blocking progress and emits LocalOpsBlocker dataclasses.

Deterministic. No empirical claims. stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BLOCKER_TYPES = [
    "missing_local_root",
    "missing_metadata",
    "missing_raw_eeg",
    "missing_reviewed_label_contract",
    "missing_dataset_specific_executor",
    "real_execution_manual_boundary",
    "human_peer_review_required",
    "controls_missing",
    "ontology_quarantined",
    "language_violation",
    "generated_language_violation",
    "local_agent_health_failure",
    "local_ops_health_failure",
    "stale_open_pr",
    "obsidian_sync_missing",
    "oss_harvest_not_started",
    "optional_dependency_missing",
    "test_failure",
]


@dataclass
class LocalOpsBlocker:
    blocker_type: str
    description: str
    source: str
    owner: str = "human"
    priority: str = "P2"
    manual_required: bool = False
    detail: dict = field(default_factory=dict)


def classify_blockers(data: dict, sources: dict) -> list[LocalOpsBlocker]:
    blockers: list[LocalOpsBlocker] = []
    _classify_local_data_blockers(data, sources, blockers)
    _classify_dataset_executor_blockers(data, sources, blockers)
    _classify_label_contract_blockers(data, sources, blockers)
    _classify_real_execution_blockers(data, sources, blockers)
    _classify_controls_blockers(data, sources, blockers)
    _classify_language_blockers(data, sources, blockers)
    _classify_ontology_blockers(data, sources, blockers)
    _classify_health_blockers(data, sources, blockers)
    _classify_obsidian_blocker(data, sources, blockers)
    _classify_stale_pr_blocker(data, sources, blockers)
    _classify_oss_harvest_blocker(data, sources, blockers)
    return blockers


def _classify_local_data_blockers(data, sources, blockers):
    next_actions = data.get("multi_dataset_next_actions", {}) or {}
    per_ds = next_actions.get("per_dataset_next_actions", {}) or {}

    aggregated = set()
    for _, action in per_ds.items():
        if isinstance(action, str):
            aggregated.add(action)

    top = next_actions.get("global_next_action", "")
    if isinstance(top, str):
        aggregated.add(top)

    la_status = data.get("local_agent_status", {}) or {}
    la_next = la_status.get("next_action", "")
    if isinstance(la_next, str):
        aggregated.add(la_next)

    if any("provide_local_root" in a for a in aggregated):
        blockers.append(LocalOpsBlocker(
            blocker_type="missing_local_root",
            description="One or more datasets need a local root directory.",
            source="multi_dataset_next_actions",
            owner="human",
            priority="P0",
            manual_required=True,
        ))
    if any("provide_metadata" in a for a in aggregated):
        blockers.append(LocalOpsBlocker(
            blocker_type="missing_metadata",
            description="One or more datasets need metadata (events.tsv).",
            source="multi_dataset_next_actions",
            owner="human",
            priority="P0",
            manual_required=True,
        ))
    if any("provide_raw_eeg" in a for a in aggregated):
        blockers.append(LocalOpsBlocker(
            blocker_type="missing_raw_eeg",
            description="One or more datasets need raw EEG files.",
            source="multi_dataset_next_actions",
            owner="human",
            priority="P0",
            manual_required=True,
        ))


_KNOWN_DATASETS_WITHOUT_EXECUTOR = ["DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]


def _classify_dataset_executor_blockers(data, sources, blockers):
    iteration_next = data.get("multi_dataset_iteration_next", {}) or {}
    per_ds = iteration_next.get("per_dataset_next_actions", {}) or {}

    detected: set[str] = set()
    for ds_id, action in per_ds.items():
        if not isinstance(action, str):
            continue
        if "implement_dataset_specific_executor" in action or "dataset_specific_executor_required" in action:
            detected.add(ds_id)

    mds_next = data.get("multi_dataset_next_actions", {}) or {}
    mds_per_ds = mds_next.get("per_dataset_next_actions", {}) or {}
    for ds_id, action in mds_per_ds.items():
        if isinstance(action, str) and "dataset_specific_executor" in action:
            detected.add(ds_id)

    if not detected:
        # Default: propose DS002094 as first candidate
        detected.add("DS002094")

    for ds_id in sorted(detected):
        blockers.append(LocalOpsBlocker(
            blocker_type="missing_dataset_specific_executor",
            description=f"{ds_id} lacks a dataset-specific executor mirroring DS005620.",
            source="multi_dataset_iteration_next" if sources.get("multi_dataset_iteration_next") == "available" else "default_plan",
            owner="claude",
            priority="P1",
            detail={"dataset_id": ds_id},
        ))


def _classify_label_contract_blockers(data, sources, blockers):
    gate = data.get("ds005620_real_execution_gate", {}) or {}
    if gate and not gate.get("ready_for_real_execution", False):
        next_action = str(gate.get("next_action", ""))
        if "label_contract" in next_action or "reviewed_contract" in next_action:
            blockers.append(LocalOpsBlocker(
                blocker_type="missing_reviewed_label_contract",
                description="Reviewed label contract declaration required before real execution.",
                source="ds005620_real_execution_gate",
                owner="claude",
                priority="P1",
                manual_required=True,
            ))


def _classify_real_execution_blockers(data, sources, blockers):
    gate = data.get("ds005620_real_execution_gate", {}) or {}
    la_status = data.get("local_agent_status", {}) or {}

    if gate and not gate.get("ready_for_real_execution", False):
        action = str(gate.get("next_action", ""))
        if "peer_review" in action:
            blockers.append(LocalOpsBlocker(
                blocker_type="human_peer_review_required",
                description="Human peer review required before real execution.",
                source="ds005620_real_execution_gate",
                owner="human",
                priority="P0",
                manual_required=True,
            ))

    if la_status.get("human_review_required"):
        blockers.append(LocalOpsBlocker(
            blocker_type="human_peer_review_required",
            description="Local agent status indicates human review required.",
            source="local_agent_status",
            owner="human",
            priority="P0",
            manual_required=True,
        ))


def _classify_controls_blockers(data, sources, blockers):
    if sources.get("multi_dataset_next_actions") == "available":
        blockers.append(LocalOpsBlocker(
            blocker_type="controls_missing",
            description="Post-real-execution controls validator is not yet implemented.",
            source="multi_dataset_next_actions",
            owner="codex",
            priority="P1",
        ))


def _classify_language_blockers(data, sources, blockers):
    lang = data.get("ontology_language_validation", {}) or {}
    if lang.get("violations_found"):
        blockers.append(LocalOpsBlocker(
            blocker_type="language_violation",
            description="Ontology claim-language violations detected.",
            source="ontology_language_validation",
            owner="codex",
            priority="P0",
        ))

    gen_lang = data.get("ds005620_language_validation", {}) or {}
    if gen_lang.get("violations_found"):
        blockers.append(LocalOpsBlocker(
            blocker_type="generated_language_violation",
            description="DS005620 generated artifacts contain language violations.",
            source="ds005620_language_validation",
            owner="codex",
            priority="P0",
        ))


def _classify_ontology_blockers(data, sources, blockers):
    la_status = data.get("local_agent_status", {}) or {}
    ont = la_status.get("ontology_status", {}) or {}
    if ont.get("ontology_quarantined", True):
        blockers.append(LocalOpsBlocker(
            blocker_type="ontology_quarantined",
            description="Ontology is quarantined to engineering_runtime scope (expected).",
            source="local_agent_status",
            owner="ontology_guard",
            priority="P3",
        ))


def _classify_health_blockers(data, sources, blockers):
    la_hc = data.get("local_agent_healthcheck", {}) or {}
    if la_hc and not la_hc.get("ok", True):
        blockers.append(LocalOpsBlocker(
            blocker_type="local_agent_health_failure",
            description=f"Local agent healthcheck blockers: {la_hc.get('blockers', [])}",
            source="local_agent_healthcheck",
            owner="codex",
            priority="P1",
        ))
    lo_hc = data.get("local_ops_healthcheck", {}) or {}
    if lo_hc and not lo_hc.get("ok", True):
        blockers.append(LocalOpsBlocker(
            blocker_type="local_ops_health_failure",
            description=f"Local ops healthcheck blockers: {lo_hc.get('blockers', [])}",
            source="local_ops_healthcheck",
            owner="codex",
            priority="P1",
        ))


def _classify_obsidian_blocker(data, sources, blockers):
    if sources.get("obsidian_sync_result") == "not_available":
        blockers.append(LocalOpsBlocker(
            blocker_type="obsidian_sync_missing",
            description="Obsidian sync output not yet generated.",
            source="obsidian_sync_result",
            owner="local_agent",
            priority="P2",
        ))


_STALE_PR_DEFAULT = 114


def _classify_stale_pr_blocker(data, sources, blockers):
    open_prs = data.get("open_prs")
    if isinstance(open_prs, dict) and "prs" in open_prs:
        for pr in open_prs.get("prs", []) or []:
            if isinstance(pr, dict) and pr.get("stale", False):
                blockers.append(LocalOpsBlocker(
                    blocker_type="stale_open_pr",
                    description=f"Stale open PR #{pr.get('number', '?')}: {pr.get('title', '')}",
                    source="open_prs",
                    owner="copilot",
                    priority="P3",
                    detail={"pr_number": pr.get("number")},
                ))
        return

    blockers.append(LocalOpsBlocker(
        blocker_type="stale_open_pr",
        description=f"PR #{_STALE_PR_DEFAULT} is presumed stale and likely superseded by merged P22-P25 work.",
        source="default_known_stale",
        owner="copilot",
        priority="P3",
        detail={"pr_number": _STALE_PR_DEFAULT},
    ))


def _classify_oss_harvest_blocker(data, sources, blockers):
    doc = Path("docs/oss_harvest_bids_mne_moabb.md")
    if not doc.exists():
        blockers.append(LocalOpsBlocker(
            blocker_type="oss_harvest_not_started",
            description="OSS harvest of BIDS/MNE/MOABB adapter patterns has not started.",
            source="docs/oss_harvest_bids_mne_moabb.md",
            owner="claude",
            priority="P2",
        ))
