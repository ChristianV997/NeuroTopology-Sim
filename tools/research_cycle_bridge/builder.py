"""Builder synthesizing simulation artifacts and research-cycle components into bridge records.

Links:
- Source dataset & provenance
- Experiment plan
- Simulation run & metrics
- Artifact manifest
- Validation report
- Evidence graph
- Release-evidence decision
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from tools.research_cycle_bridge.adapters import (
    adapt_bridge_to_release_bundle,
    adapt_simulation_lineage,
)
from tools.research_cycle_bridge.models import (
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    ResearchCycleBridgeRecord,
    canonical_hash,
    finite_value,
)
from tools.research_cycle_release.evaluator import evaluate_research_cycle_release
from tools.simulation_artifacts.extractor import extract_run


def _load_json_or_dict(source: Any) -> Optional[dict[str, Any]]:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return dict(source)
    if hasattr(source, "to_dict"):
        return source.to_dict()
    path = Path(source)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def build_research_cycle_bridge(
    run_dir: str | Path | None = None,
    *,
    lineage_report: Mapping[str, Any] | None = None,
    experiment_plan: Any | None = None,
    source_dataset: Any | None = None,
    cycle_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    evaluate_release: bool = True,
) -> ResearchCycleBridgeRecord:
    """Build a deterministic ResearchCycleBridgeRecord linking artifacts to research-cycle entities.
    
    Args:
        run_dir: Local simulation run directory path.
        lineage_report: Pre-extracted simulation artifact lineage dictionary (if run_dir not provided).
        experiment_plan: Optional ExperimentPlan.v1 dictionary, object, or file path.
        source_dataset: Optional dataset metadata dictionary or path.
        cycle_id: Optional research cycle ID.
        dataset_id: Optional dataset ID override.
        evaluate_release: Whether to invoke the release-evidence evaluator.
        
    Returns:
        Fully populated, validated ResearchCycleBridgeRecord with deterministic checksums.
    """
    if run_dir is not None:
        raw_lineage = extract_run(run_dir)
    elif lineage_report is not None:
        raw_lineage = dict(lineage_report)
    else:
        raise ValueError("Either run_dir or lineage_report must be provided")

    adapted = adapt_simulation_lineage(raw_lineage)
    prov = adapted["provenance"]
    status = adapted["status"]
    data_mode = adapted["data_mode"]
    synthetic = adapted["synthetic"]
    proxy = adapted["proxy"]
    empirical = adapted["empirical"]
    evidence_class = adapted["evidence_class"]
    diagnostics = adapted["diagnostics"]
    artifacts_manifest = adapted["artifact_manifest"]

    run_id = prov.get("run_id") or "run_unspecified"
    eff_cycle_id = cycle_id or f"rc-cycle-{run_id}"
    eff_dataset_id = dataset_id or prov.get("dataset_id") or "dataset_unspecified"

    # 1. Source dataset stage
    ds_payload = _load_json_or_dict(source_dataset) or {
        "dataset_id": eff_dataset_id,
        "data_mode": data_mode,
        "source": prov.get("source"),
    }
    ds_checksum = canonical_hash(ds_payload)
    ds_node_id = f"ds_{eff_dataset_id}"

    # 2. Experiment plan stage
    plan_payload = _load_json_or_dict(experiment_plan) or {
        "plan_id": f"plan_{run_id}",
        "hypothesis_id": f"hyp_{run_id}",
        "dataset_id": eff_dataset_id,
        "data_mode": data_mode,
        "is_synthetic": synthetic,
    }
    plan_checksum = plan_payload.get("checksum") or canonical_hash(plan_payload)
    plan_node_id = str(plan_payload.get("plan_id", f"plan_{run_id}"))

    # 3. Simulation run stage
    sim_run_payload = {
        "run_id": run_id,
        "status": status,
        "data_mode": data_mode,
        "created_at": prov.get("created_at"),
        "git_commit": prov.get("git_commit"),
        "metrics": {},
    }
    # Read metrics artifact if present
    run_dir_path = Path(artifacts_manifest.get("run_directory", ""))
    if run_dir_path.is_dir():
        metrics_file = run_dir_path / "metrics.json"
        if metrics_file.is_file():
            try:
                metrics_data = json.loads(metrics_file.read_text(encoding="utf-8"))
                if isinstance(metrics_data, Mapping):
                    sim_run_payload["metrics"] = {k: finite_value(v) for k, v in metrics_data.items()}
            except Exception:
                pass
        summary_file = run_dir_path / "summary.json"
        if summary_file.is_file():
            try:
                summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
                if isinstance(summary_data, Mapping):
                    for k in ("loss", "accuracy", "peak_memory_mb", "runtime_s"):
                        if k in summary_data and k not in sim_run_payload["metrics"]:
                            sim_run_payload["metrics"][k] = finite_value(summary_data[k])
            except Exception:
                pass

    sim_checksum = canonical_hash(sim_run_payload)
    sim_node_id = f"run_{run_id}"

    # 4. Artifact manifest stage
    artifact_checksum = adapted["lineage_checksum"]
    artifact_node_id = f"artifact_{run_id}"

    # 5. Validation report stage
    val_report_payload = None
    val_node_id = f"val_{run_id}"
    val_checksum = ""
    if run_dir_path.is_dir():
        val_file = run_dir_path / "validation_report.json"
        if val_file.is_file():
            try:
                val_report_payload = json.loads(val_file.read_text(encoding="utf-8"))
            except Exception:
                val_report_payload = None
    if val_report_payload is None:
        val_report_payload = {
            "validation_id": val_node_id,
            "status": "complete" if status == "COMPLETE" else "inconclusive",
            "checks_passed": status == "COMPLETE",
        }
    val_checksum = canonical_hash(val_report_payload)

    # 6. Evidence graph stage
    nodes = [
        EvidenceGraphNode(id=ds_node_id, stage="source_dataset", data_mode=data_mode, checksum=ds_checksum),
        EvidenceGraphNode(id=plan_node_id, stage="experiment_plan", data_mode=data_mode, checksum=plan_checksum),
        EvidenceGraphNode(id=sim_node_id, stage="simulation_run", data_mode=data_mode, checksum=sim_checksum),
        EvidenceGraphNode(id=artifact_node_id, stage="artifact_manifest", data_mode=data_mode, checksum=artifact_checksum),
        EvidenceGraphNode(id=val_node_id, stage="validation_report", data_mode=data_mode, checksum=val_checksum),
    ]
    edges = [
        EvidenceGraphEdge(source=plan_node_id, target=ds_node_id, relationship="audits"),
        EvidenceGraphEdge(source=sim_node_id, target=plan_node_id, relationship="executes"),
        EvidenceGraphEdge(source=artifact_node_id, target=sim_node_id, relationship="indexes"),
        EvidenceGraphEdge(source=val_node_id, target=artifact_node_id, relationship="validates"),
    ]

    egraph = EvidenceGraph(
        graph_id=f"egraph_{run_id}",
        nodes=nodes,
        edges=edges,
        partial=(status == "PARTIAL"),
        scientific_status="not_evidence",
    )
    egraph_dict = egraph.to_dict()
    egraph_checksum = egraph_dict["checksum"]

    # 7. Release-evidence evaluation stage
    release_decision_dict = None
    if evaluate_release:
        draft_record = {
            "record_id": f"bridge_{eff_cycle_id}_{run_id}",
            "cycle_id": eff_cycle_id,
            "status": status,
            "evidence_class": evidence_class,
            "synthetic": synthetic,
            "proxy": proxy,
            "empirical": empirical,
            "provenance": prov,
            "artifact_manifest": artifacts_manifest,
            "simulation_run": sim_run_payload,
            "validation_report": val_report_payload,
            "diagnostics": diagnostics,
        }
        bundle = adapt_bridge_to_release_bundle(draft_record)
        release_report = evaluate_research_cycle_release(bundle, adapter_hint="generic")
        release_decision_dict = release_report.to_dict()

    parent_ids = [ds_node_id, plan_node_id, sim_node_id, artifact_node_id, val_node_id]
    parent_checksums = [ds_checksum, plan_checksum, sim_checksum, artifact_checksum, val_checksum]

    record = ResearchCycleBridgeRecord(
        record_id=f"bridge_{eff_cycle_id}_{run_id}",
        cycle_id=eff_cycle_id,
        dataset_id=eff_dataset_id,
        data_mode=data_mode,
        status=status,
        evidence_class=evidence_class,
        synthetic=synthetic,
        proxy=proxy,
        empirical=empirical,
        provenance=prov,
        source_dataset=ds_payload,
        experiment_plan=plan_payload,
        simulation_run=sim_run_payload,
        artifact_manifest=artifacts_manifest,
        validation_report=val_report_payload,
        evidence_graph=egraph_dict,
        release_evidence=release_decision_dict,
        parent_ids=parent_ids,
        parent_checksums=parent_checksums,
        diagnostics=diagnostics,
        scientific_verdict="NOT_APPLICABLE",
    )

    # Compute record checksum
    record.to_dict()
    return record
