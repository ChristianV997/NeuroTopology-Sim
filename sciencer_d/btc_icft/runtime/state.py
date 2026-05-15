"""
Science runtime state and snapshot (P18.2 / O4).
Loads P18.1 execution artifacts and builds a structured runtime state.
Includes ontology evaluation status when available.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sciencer_d.btc_icft.ontology.artifact_reader import summarize_ontology_for_packet


_NEXT_ACTION_CHAIN = [
    "run_mock_e2e",
    "build_artifact_manifest",
    "evaluate_ontology_claims",
    "export_evidence_packet",
    "generate_paper_skeleton",
    "ready_for_real_local_preflight_or_review",
]


@dataclass
class ScienceRuntimeState:
    dataset_id: str
    artifact_root: str
    execution_json_path: Optional[str]
    benchmark_completed: bool
    p12_succeeded: bool
    p13_succeeded: bool
    p11_succeeded: bool
    mock_e2e_run: bool
    artifact_manifest_exists: bool
    evidence_packet_exists: bool
    paper_skeleton_exists: bool
    next_action: str
    blockers: list[str]
    warnings: list[str]
    last_updated: str
    predictive_metrics_available: bool = False
    real_local_preflight_ready: bool = False
    ontology_available: bool = False
    ontology_max_claim_scope: str = "engineering_runtime"
    ontology_promotion_state: str = "engineering_validated"
    ontology_claim_status: str = "ontology_quarantined"
    ontology_next_action: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class ScienceRuntimeSnapshot:
    snapshot_id: str
    created_at: str
    state: dict
    source_artifacts: list[str]


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _determine_next_action(state_partial: dict) -> str:
    if not state_partial.get("mock_e2e_run"):
        return "run_mock_e2e"
    if not state_partial.get("artifact_manifest_exists"):
        return "build_artifact_manifest"
    if not state_partial.get("ontology_evaluation_exists"):
        return "evaluate_ontology_claims"
    if not state_partial.get("evidence_packet_exists"):
        return "export_evidence_packet"
    if not state_partial.get("paper_skeleton_exists"):
        return "generate_paper_skeleton"
    return "ready_for_real_local_preflight_or_review"


def load_latest_execution(artifact_root: str) -> Optional[dict]:
    """Load ds005620_real_benchmark_execution.json from artifact_root."""
    p = Path(artifact_root) / "ds005620_real_benchmark_execution.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_runtime_state(
    dataset_id: str,
    artifact_root: str,
    *,
    manifest_dir: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    skeleton_dir: Optional[str] = None,
    ontology_root: Optional[str] = None,
) -> ScienceRuntimeState:
    execution = load_latest_execution(artifact_root)

    if execution is None:
        return ScienceRuntimeState(
            dataset_id=dataset_id,
            artifact_root=artifact_root,
            execution_json_path=None,
            benchmark_completed=False,
            p12_succeeded=False,
            p13_succeeded=False,
            p11_succeeded=False,
            mock_e2e_run=False,
            artifact_manifest_exists=False,
            evidence_packet_exists=False,
            paper_skeleton_exists=False,
            next_action="run_mock_e2e",
            blockers=["no_execution_artifact_found"],
            warnings=[],
            last_updated=_ts_now(),
        )

    benchmark_completed = bool(execution.get("benchmark_completed"))
    p12_succeeded = bool(execution.get("p12_succeeded"))
    p13_succeeded = bool(execution.get("p13_succeeded"))
    p11_succeeded = bool(execution.get("p11_succeeded"))
    mode = execution.get("mode", "unknown")
    mock_e2e_run = benchmark_completed and mode in ("mock_e2e", "mock-e2e")

    manifest_dir = manifest_dir or artifact_root
    evidence_dir = evidence_dir or artifact_root
    skeleton_dir = skeleton_dir or artifact_root

    manifest_exists = (Path(manifest_dir) / "artifact_manifest.json").exists()
    evidence_exists = (Path(evidence_dir) / "evidence_packet.json").exists()
    skeleton_exists = (Path(skeleton_dir) / "paper_skeleton.md").exists()

    # Ontology evaluation status
    _ont_root = Path(ontology_root) if ontology_root else Path("outputs/btc_icft/ds005620_ontology_evaluation_mock")
    ontology_eval_exists = (_ont_root / "ontology_claim_evaluation.json").exists()
    ontology_summary = summarize_ontology_for_packet(_ont_root) if ontology_eval_exists else {}

    partial = {
        "mock_e2e_run": mock_e2e_run,
        "artifact_manifest_exists": manifest_exists,
        "ontology_evaluation_exists": ontology_eval_exists,
        "evidence_packet_exists": evidence_exists,
        "paper_skeleton_exists": skeleton_exists,
    }
    next_action = _determine_next_action(partial)

    blockers: list[str] = []
    if not benchmark_completed:
        blockers.append("benchmark_not_completed")

    execution_json_path = str(Path(artifact_root) / "ds005620_real_benchmark_execution.json")

    predictive_metrics_path = None
    for stage in execution.get("stages", []):
        if stage.get("stage_id") == "p11" and stage.get("succeeded"):
            for out in stage.get("actual_outputs", []):
                if "metrics_signal_mt.json" in str(out):
                    predictive_metrics_path = out

    return ScienceRuntimeState(
        dataset_id=dataset_id,
        artifact_root=artifact_root,
        execution_json_path=execution_json_path,
        benchmark_completed=benchmark_completed,
        p12_succeeded=p12_succeeded,
        p13_succeeded=p13_succeeded,
        p11_succeeded=p11_succeeded,
        mock_e2e_run=mock_e2e_run,
        artifact_manifest_exists=manifest_exists,
        evidence_packet_exists=evidence_exists,
        paper_skeleton_exists=skeleton_exists,
        next_action=next_action,
        blockers=blockers,
        warnings=[],
        last_updated=_ts_now(),
        predictive_metrics_available=predictive_metrics_path is not None,
        ontology_available=bool(ontology_summary.get("ontology_available", False)),
        ontology_max_claim_scope=str(ontology_summary.get("max_claim_scope", "engineering_runtime")),
        ontology_promotion_state=str(ontology_summary.get("promotion_state", "engineering_validated")),
        ontology_claim_status=str(ontology_summary.get("ontology_claim_status", "ontology_quarantined")),
        ontology_next_action="evaluate_ontology_claims" if not ontology_eval_exists else None,
    )


def build_runtime_snapshot(state: ScienceRuntimeState, snapshot_id: Optional[str] = None) -> ScienceRuntimeSnapshot:
    import hashlib

    if snapshot_id is None:
        raw = json.dumps(
            {"dataset_id": state.dataset_id, "artifact_root": state.artifact_root, "ts": state.last_updated},
            sort_keys=True,
        )
        snapshot_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

    state_dict = {
        "dataset_id": state.dataset_id,
        "artifact_root": state.artifact_root,
        "execution_json_path": state.execution_json_path,
        "benchmark_completed": state.benchmark_completed,
        "p12_succeeded": state.p12_succeeded,
        "p13_succeeded": state.p13_succeeded,
        "p11_succeeded": state.p11_succeeded,
        "mock_e2e_run": state.mock_e2e_run,
        "artifact_manifest_exists": state.artifact_manifest_exists,
        "evidence_packet_exists": state.evidence_packet_exists,
        "paper_skeleton_exists": state.paper_skeleton_exists,
        "next_action": state.next_action,
        "blockers": state.blockers,
        "warnings": state.warnings,
        "last_updated": state.last_updated,
        "predictive_metrics_available": state.predictive_metrics_available,
        "real_local_preflight_ready": state.real_local_preflight_ready,
        "ontology_available": state.ontology_available,
        "ontology_max_claim_scope": state.ontology_max_claim_scope,
        "ontology_promotion_state": state.ontology_promotion_state,
        "ontology_claim_status": state.ontology_claim_status,
        "ontology_next_action": state.ontology_next_action,
        "extra": state.extra,
    }

    source_artifacts = []
    if state.execution_json_path:
        source_artifacts.append(state.execution_json_path)

    return ScienceRuntimeSnapshot(
        snapshot_id=snapshot_id,
        created_at=state.last_updated,
        state=state_dict,
        source_artifacts=source_artifacts,
    )
