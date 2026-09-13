"""Project verified execution artifacts without filling missing evidence."""
from typing import Any, Mapping

from awareness_studio.research_graph.builder import EvidenceGraphBuilder
from awareness_studio.research_graph.models import GraphNode
from awareness_studio.research_graph.types import EdgeType, NodeType


def review_execution(cycle_id: str, binding: Mapping[str, Any], preflight: Mapping[str, Any],
                     result: Mapping[str, Any] | None) -> dict[str, Any]:
    from tools.research_cycle_release.adapters import empty_bundle
    from tools.research_cycle_release.evaluator import evaluate_research_cycle_release

    graph = EvidenceGraphBuilder(metadata={"cycle_id": cycle_id, "scientific_pass": False})
    experiment_id = cycle_id + ":experiment"
    graph.add_node(GraphNode(experiment_id, NodeType.EXPERIMENT, "Declared execution plan",
                             status="proposed", evidence_class="unknown", properties=dict(binding)))
    bundle = empty_bundle(cycle_id=cycle_id)
    bundle.update(configuration_locked=preflight.get("cleared_for_execution") is True,
                  code_commit=binding["code_commit"], seed=binding["seed"],
                  report_metadata_text="Registered local engineering execution; scientific review pending.")
    manifest = (result or {}).get("runner_manifest") or {}
    units = manifest.get("units", [])
    if units:
        run_id = cycle_id + ":run"
        success = result.get("state") in {"ENGINEERING_EXECUTION_COMPLETE", "EVIDENCE_READY_FOR_REVIEW"}
        synthetic = result.get("evidence_class") == "synthetic_demo_only"
        evidence_class = "synthetic" if synthetic else "unknown"
        graph.add_node(GraphNode(run_id, NodeType.RUN, "Canonical executor outcome",
                                 status="review_required" if success else "blocked",
                                 evidence_class=evidence_class,
                                 properties={"execution_state": result.get("execution_state"), "units": units}))
        graph.link(EdgeType.GENERATED_BY, run_id, experiment_id)
        accepted = result.get("accepted_artifacts", [])
        for artifact in accepted:
            artifact_id = run_id + ":" + artifact["relative_path"]
            graph.add_node(GraphNode(artifact_id, NodeType.ARTIFACT, artifact["relative_path"],
                                     status="review_required", evidence_class=evidence_class,
                                     properties=dict(artifact)))
            graph.link(EdgeType.GENERATED_BY, artifact_id, run_id)
        validation_id = cycle_id + ":validation"
        graph.add_node(GraphNode(validation_id, NodeType.VALIDATION, "Artifact verification",
                                 status="review_required" if success else "blocked",
                                 evidence_class="unknown",
                                 properties={"lineage": result.get("lineage_report"),
                                             "diagnostics": result.get("diagnostics", [])}))
        # This relation records what was checked, not support for a theory.
        graph.link(EdgeType.REFERENCES, validation_id, run_id)
        lineage = result.get("lineage_report") or {}
        bundle.update(
            checksums_present=bool(accepted), checksum_entries=accepted,
            outputs_finite=True if success else None,
            work_units=[{"id": u["unit_id"], "status": u["state"]} for u in units],
            all_work_units_terminal=all(u["state"] in {"PASS", "FAILED", "TIMEOUT", "BLOCKED", "PARTIAL", "INFRASTRUCTURE_FAILURE"} for u in units),
            partial_runs_explicitly_marked=True,
            artifact_lineage_complete=lineage.get("status") == "COMPLETE" if lineage else None,
            validation_report_present=bool(lineage), validation_status="ok" if success else "failed",
            network_policy_recorded="network_disabled" in manifest.get("runner", {}),
            synthetic_only=synthetic, evidence_classes=[evidence_class],
            infrastructure_blocked=any(u["state"] == "INFRASTRUCTURE_FAILURE" for u in units),
            resource_budget_details={u["unit_id"]: u.get("resource_telemetry", {}) for u in units},
        )
        # Source manifests, empirical provenance, null-model applicability,
        # comparability, and sandbox enforcement are not established by a
        # successful process. Leave these canonical fields unknown.
    release = evaluate_research_cycle_release(bundle, adapter_hint="generic").to_dict()
    return {"graph": graph.build().to_dict(), "release_review": release}
