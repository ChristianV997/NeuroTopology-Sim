"""Admission and ledger projection for explicitly registered local workloads."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from awareness_studio.research_cycle import ResearchCycleLedger, sha256_json
from awareness_studio.simulation_bridge import BridgeRequest, SimulationBridge, WorkloadRegistry


def execution_binding(request: BridgeRequest, registry: WorkloadRegistry) -> dict[str, Any]:
    """The exact request a reviewed plan authorizes, excluding resume preference."""
    workload = registry.get(request.workload_id)
    return {
        "run_id": request.run_id,
        "workload_id": request.workload_id,
        "argv": list(workload.argv) if workload else None,
        "expected_outputs": list(workload.expected_outputs) if workload else None,
        "code_commit": request.code_commit,
        "configuration": dict(request.configuration),
        "seed": request.seed,
        "input_identity": request.input_identity,
        "provenance": dict(request.provenance),
        "output_root": str(request.output_root.resolve()),
        "resource_budget": asdict(request.resource_budget),
        "network_enabled": request.network_enabled,
    }


def execute_registered(request: BridgeRequest, registry: WorkloadRegistry,
                       preflight_request: Mapping[str, Any], ledger_path: Path,
                       *, now: str | None = None) -> dict[str, Any]:
    """Run the canonical preflight and bridge, recording actual outcomes.

    Authorization is explicit in BridgeRequest. Planning invokes no workload.
    The caller must expose the repository's canonical tools package, as for
    the other cross-project integration APIs.
    """
    from awareness_studio.literature_bridge.repo_paths import ensure_repo_root_importable
    ensure_repo_root_importable()
    from tools.research_cycle_preflight.compose import run_preflight

    timestamp = now or datetime.now(timezone.utc).isoformat()
    binding = execution_binding(request, registry)
    # Validate serialization before writing any ledger event or starting a child.
    binding_hash = sha256_json(binding)
    preflight_hash = sha256_json(dict(preflight_request))
    cycle_id = "execution-" + sha256_json({"binding": binding_hash, "preflight": preflight_hash})[:32]
    diagnostics = []
    from .research_context import prepare_research_context
    try:
        research_records = prepare_research_context(preflight_request, cycle_id, binding)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        research_records = []
        diagnostics.append(f"literature context rejected: {exc}")
    if preflight_request.get("execution_binding") != binding:
        diagnostics.append("reviewed execution_binding does not match the requested computation")
    plan = preflight_request.get("plan", {})
    if not isinstance(plan, Mapping):
        plan = {}
    reproducibility = plan.get("reproducibility", {})
    if not isinstance(reproducibility, Mapping):
        reproducibility = {}
    if plan.get("dataset_id") != request.provenance.get("dataset_id"):
        diagnostics.append("plan dataset identity does not match execution provenance")
    if reproducibility.get("seed") != request.seed:
        diagnostics.append("plan seed does not match execution seed")
    if reproducibility.get("code_version") != request.code_commit:
        diagnostics.append("plan code version does not match execution revision")
    mode = str(request.provenance.get("data_mode", "")).lower()
    if mode in {"synthetic", "synthetic_demo"} and plan.get("evidence_class_declared") != "synthetic":
        diagnostics.append("synthetic execution requires a synthetic plan evidence class")
    if request.resource_budget.memory_budget_bytes is None or request.resource_budget.disk_budget_bytes is None:
        diagnostics.append("registered execution requires explicit memory and disk budgets")

    bridge = SimulationBridge(registry)
    planned = bridge.plan(request)
    if planned.state.value != "PLANNING":
        diagnostics.extend(planned.diagnostics)
    preflight = run_preflight(preflight_request, now=timestamp)
    admitted = preflight["cleared_for_execution"] is True and not diagnostics
    ledger = ResearchCycleLedger(ledger_path)
    ledger.create_cycle(cycle_id, metadata={"binding": binding, "preflight_request_sha256": preflight_hash},
                        producer="awareness_studio.orchestrator")
    if admitted:
        for record in research_records:
            ledger.append_record(cycle_id, record, producer="awareness_studio.orchestrator")
    ledger.append_event(cycle_id, "orchestrator_stage", producer="awareness_studio.orchestrator",
                        status="COMPLETED" if admitted else "BLOCKED",
                        payload={"stage": "preflight", "report": preflight, "diagnostics": diagnostics})
    result = None
    if admitted:
        ledger.append_event(cycle_id, "orchestrator_stage", producer="awareness_studio.orchestrator",
                            status="IN_PROGRESS", payload={"stage": "execute", "authorized": request.authorize_execution})
        try:
            result = bridge.run(request).to_dict()
        except Exception as exc:
            # The bridge normally converts runner failures into a typed result,
            # but keep the ledger recoverable if an adapter boundary itself
            # fails.  Never turn an unhandled exception into an absent outcome.
            failure = f"registered execution adapter failed: {type(exc).__name__}: {exc}"
            diagnostics.append(failure)
            result = {
                "schema_version": "AwarenessStudio.SimulationBridge.v1",
                "state": "EXECUTION_FAILED",
                "workload_id": request.workload_id,
                "run_id": request.run_id,
                "authorize_execution": request.authorize_execution,
                "network_enabled": request.network_enabled,
                "execution_state": None,
                "accepted_artifacts": [],
                "rejected_artifacts": [],
                "runner_manifest": None,
                "lineage_report": None,
                "diagnostics": [failure],
                "metrics": None,
                "scientific_pass": False,
                "formal_bayes_factor": None,
                "evidence_class": "engineering_execution",
                "claim_scope": "Engineering execution and artifact review only; not scientific evidence or causal validation.",
            }
    state = result["state"] if result else "BLOCKED"
    completed = state in {"ENGINEERING_EXECUTION_COMPLETE", "EVIDENCE_READY_FOR_REVIEW"}
    ledger.append_event(cycle_id, "execution_outcome", producer="awareness_studio.orchestrator",
                        status="COMPLETED" if completed else ("REVIEW_REQUIRED" if state == "PLANNING" else "BLOCKED" if state == "BLOCKED" else "FAILED"),
                        payload={"execution_state": state, "result": result, "scientific_evidence": False})
    if result and request.authorize_execution:
        ledger.append_event(cycle_id, "validation_outcome", producer="awareness_studio.orchestrator",
                            status="COMPLETED" if completed else "FAILED",
                            payload={"artifact_lineage": result["lineage_report"],
                                     "accepted_artifacts": result["accepted_artifacts"],
                                     "diagnostics": result["diagnostics"], "scientific_evidence": False})
    from .execution_review import review_execution
    review = review_execution(cycle_id, binding, preflight, result, research_records if admitted else ())
    ledger.append_event(cycle_id, "evidence_graph_update", producer="awareness_studio.orchestrator",
                        status="REVIEW_REQUIRED", payload=review["graph"])
    ledger.append_event(cycle_id, "release_review", producer="awareness_studio.orchestrator",
                        status="REVIEW_REQUIRED", payload={"release_authorized": False, "scientific_evidence": False,
                                                           "report": review["release_review"]})
    return {"schema_version": "AwarenessStudio.RegisteredExecution.v1", "cycle_id": cycle_id,
            "ledger_path": str(ledger_path), "state": state, "preflight": preflight,
            "diagnostics": diagnostics, "execution": result, **review, "scientific_pass": False,
            "formal_bayes_factor": None, "release_authorized": False}
