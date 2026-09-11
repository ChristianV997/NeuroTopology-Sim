"""Synthetic fixture builders for research-cycle smoke scenarios."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from tools.release_readiness.research_cycle_smoke.schema import (
    CHAIN_STAGES,
    ScenarioId,
    StageRecord,
    json_safe,
)

CLAIM_SCOPE = (
    "Synthetic smoke fixture for engineering acceptance only. "
    "Not empirical evidence and not a formal statistical certification."
)

SEED = 7
CODE_COMMIT = "smoke0c0ffee"


def _checksum(obj: Any) -> str:
    blob = json.dumps(json_safe(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _stage(
    stage: str,
    record_id: str,
    status: str,
    parent_ids: List[str],
    payload: Dict[str, Any],
    *,
    visible_issue: Optional[str] = None,
) -> StageRecord:
    body = {
        "stage": stage,
        "record_id": record_id,
        "status": status,
        "parent_ids": parent_ids,
        "payload": payload,
        "visible_issue": visible_issue,
        "claim_scope": CLAIM_SCOPE,
    }
    return StageRecord(
        stage=stage,
        record_id=record_id,
        status=status,
        parent_ids=list(parent_ids),
        checksum=_checksum(body),
        visible_issue=visible_issue,
        payload=payload,
    )


def _base_chain(
    *,
    scenario: ScenarioId,
    subjects: Optional[List[str]] = None,
    source_status: str = "complete",
    source_issue: Optional[str] = None,
    run_status: str = "completed",
    run_issue: Optional[str] = None,
    validation_status: str = "ok",
    validation_present: bool = True,
    validation_issue: Optional[str] = None,
    provenance_ok: bool = True,
    evidence_class: str = "engineering",
    metrics: Optional[Dict[str, Any]] = None,
) -> List[StageRecord]:
    subjects = subjects or [f"sub-{i:02d}" for i in range(1, 9)]
    source_id = f"src_{scenario.value}"
    plan_id = f"plan_{scenario.value}"
    hyp_id = f"hyp_{scenario.value}"
    exp_id = f"exp_{scenario.value}"
    run_id = f"run_{scenario.value}"
    art_id = f"art_{scenario.value}"
    val_id = f"val_{scenario.value}"
    graph_id = f"egraph_{scenario.value}"

    source_payload = {
        "subjects": subjects,
        "subject_count": len(subjects),
        "origin": "synthetic_local",
        "source_checksum": ("a" * 64) if provenance_ok else None,
        "full_dataset_download": False,
        "network_accessed": False,
    }
    stages = [
        _stage(
            "source",
            source_id,
            source_status,
            [],
            source_payload,
            visible_issue=source_issue,
        )
    ]
    stages.append(
        _stage(
            "plan",
            plan_id,
            "complete" if provenance_ok else "invalid",
            [source_id],
            {
                "plan_id": plan_id,
                "source_id": source_id,
                "configuration_locked": True,
                "seed": SEED,
                "code_commit": CODE_COMMIT,
                "is_synthetic": True,
            },
            visible_issue=None if provenance_ok else "invalid_provenance",
        )
    )
    stages.append(
        _stage(
            "hypothesis",
            hyp_id,
            "preregistered",
            [plan_id],
            {
                "hypothesis_id": hyp_id,
                "precise_claim": "Synthetic operational claim for smoke only.",
                "epistemic_label": "computational_model",
                "scientific_pass": False,
            },
        )
    )
    stages.append(
        _stage(
            "experiment",
            exp_id,
            "ready",
            [hyp_id],
            {
                "experiment_id": exp_id,
                "hypothesis_id": hyp_id,
                "domain": "null_and_surrogate",
                "held_out_split_locked": True,
            },
        )
    )
    run_metrics = metrics if metrics is not None else {"fixture_metric": 0.25}
    stages.append(
        _stage(
            "run",
            run_id,
            run_status,
            [exp_id],
            {
                "run_id": run_id,
                "status": run_status,
                "partial": run_status == "partial",
                "metrics": run_metrics,
                "synthetic": True,
                "seed": SEED,
            },
            visible_issue=run_issue,
        )
    )
    art_status = "complete"
    if run_status in {"failed", "error", "timeout", "timed_out"}:
        # Failure/timeout still leaves a terminal artifact envelope so the
        # validation decision remains visible (not collapsed into provenance).
        art_status = "complete"
    elif run_status == "partial":
        art_status = "partial"
    elif run_status not in {"completed", "complete", "success"}:
        art_status = run_status
    stages.append(
        _stage(
            "artifact",
            art_id,
            art_status,
            [run_id],
            {
                "artifact_id": art_id,
                "run_id": run_id,
                "output_checksums": ["out_" + run_id] if art_status in {"complete", "partial"} else [],
                "input_checksums": ["in_" + exp_id] if provenance_ok else [],
                "lineage_complete": art_status == "complete" and provenance_ok,
            },
            visible_issue=None
            if art_status == "complete" and provenance_ok
            else ("artifact_incomplete" if art_status != "complete" else "artifact_incomplete"),
        )
    )
    if validation_present:
        stages.append(
            _stage(
                "validation",
                val_id,
                validation_status,
                [art_id],
                {
                    "validation_id": val_id,
                    "status": validation_status,
                    "null_metadata": {"method": "phase_shuffle"},
                    "multiplicity_method": "holm",
                    "scientific_pass": False,
                    "bayes_factor": None,
                },
                visible_issue=validation_issue,
            )
        )
    else:
        stages.append(
            _stage(
                "validation",
                val_id,
                "missing",
                [art_id],
                {"validation_id": val_id, "present": False},
                visible_issue="missing_validation_report",
            )
        )

    node_ids = [s.record_id for s in stages]
    stages.append(
        _stage(
            "evidence_graph",
            graph_id,
            "projected",
            [val_id],
            {
                "graph_id": graph_id,
                "nodes": node_ids,
                "edges": [
                    {"from": stages[i].record_id, "to": stages[i + 1].record_id}
                    for i in range(len(stages) - 1)
                ],
                "evidence_class": evidence_class,
                "synthetic": True,
                "scientific_evidence": False,
            },
        )
    )
    return stages


def chain_to_release_bundle(
    stages: List[StageRecord],
    *,
    scenario: ScenarioId,
    expected_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Map a smoke chain onto the research_cycle_release generic bundle."""
    by_stage = {s.stage: s for s in stages}
    source = by_stage["source"]
    plan = by_stage["plan"]
    run = by_stage["run"]
    artifact = by_stage["artifact"]
    validation = by_stage["validation"]
    graph = by_stage["evidence_graph"]

    has_source_checksum = bool(source.payload.get("source_checksum"))
    source_present = has_source_checksum and source.status not in {"incomplete", "invalid", "missing"}
    provenance_complete = (
        source_present
        and plan.status != "invalid"
        and bool(plan.payload.get("code_commit"))
        and plan.payload.get("seed") is not None
        and bool(plan.payload.get("configuration_locked"))
    )
    lineage_complete = bool(artifact.payload.get("lineage_complete"))
    validation_present = validation.status not in {"missing"}
    run_status = str(run.payload.get("status") or run.status)
    partial = bool(run.payload.get("partial")) or run_status == "partial"
    terminal = run_status.lower() in {
        "completed",
        "complete",
        "failed",
        "error",
        "timeout",
        "timed_out",
        "cancelled",
        "canceled",
    } and not partial

    metrics = run.payload.get("metrics") if isinstance(run.payload.get("metrics"), dict) else {}
    non_finite_paths = []
    cleaned_metrics: Dict[str, Any] = {}
    for key, value in metrics.items():
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            cleaned_metrics[key] = None
            non_finite_paths.append(f"metrics.{key}")
        else:
            cleaned_metrics[key] = value

    evidence_class = str(graph.payload.get("evidence_class") or "engineering")
    synthetic_only = evidence_class in {"synthetic", "synthetic_only"}
    proxy_only = evidence_class in {"proxy", "proxy_only"}

    # Keep provenance fields independent of run outcome so downstream failures
    # remain visible as artifact/validation decisions (not provenance collapse).
    checksum_entries = (
        [{"id": source.record_id, "sha256": source.payload.get("source_checksum")}]
        if has_source_checksum
        else []
    )

    bundle: Dict[str, Any] = {
        "bundle_schema": "research_cycle_release_bundle.v1",
        "cycle_id": f"smoke-{scenario.value}",
        "source_manifest_present": source_present,
        "source_manifest_path": f"fixtures/{scenario.value}/source.json" if source_present else None,
        "checksums_present": bool(checksum_entries),
        "checksum_entries": checksum_entries,
        "configuration_locked": bool(plan.payload.get("configuration_locked")),
        "code_commit": plan.payload.get("code_commit"),
        "seed": plan.payload.get("seed"),
        "input_provenance_complete": provenance_complete,
        "input_provenance_missing": [] if provenance_complete else ["source_or_plan_provenance"],
        "outputs_finite": len(non_finite_paths) == 0,
        "non_finite_metric_paths": non_finite_paths,
        "metrics": cleaned_metrics,
        "work_units": [
            {
                "id": run.record_id,
                "status": run_status,
                "partial": partial,
                "output_checksums": artifact.payload.get("output_checksums") or [],
                "input_checksums": artifact.payload.get("input_checksums") or [],
            }
        ],
        "all_work_units_terminal": terminal,
        "partial_runs_explicitly_marked": True,
        "artifact_lineage_complete": lineage_complete,
        "artifact_lineage_missing": [] if lineage_complete else ["artifact_lineage"],
        "validation_report_present": validation_present,
        "validation_status": None if not validation_present else validation.status,
        "null_metadata_applicable": True,
        "null_metadata_present": bool((validation.payload or {}).get("null_metadata")),
        "multiplicity_metadata_applicable": True,
        "multiplicity_metadata_present": bool((validation.payload or {}).get("multiplicity_method")),
        "forecasting_applicable": False,
        "resource_budgets_respected": True,
        "full_dataset_download": False,
        "network_policy_recorded": True,
        "network_policy_violated": False,
        "evidence_classes": [evidence_class] if evidence_class else [],
        "evidence_classes_consistent": True,
        "synthetic_only": synthetic_only,
        "proxy_only": proxy_only,
        "empirical_present": False,
        "report_metadata_text": CLAIM_SCOPE,
        "infrastructure_blocked": False,
        "comparable": True,
        "comparability_notes": [],
        "hardware_metrics_advisory": True,
    }
    if expected_overrides:
        bundle.update(expected_overrides)
    return bundle


def build_scenario(scenario: ScenarioId) -> Tuple[List[StageRecord], Dict[str, Any], str]:
    """Return (stages, release_bundle, expected_decision)."""
    if scenario == ScenarioId.COMPLETE_VALID_ENGINEERING:
        stages = _base_chain(scenario=scenario, evidence_class="engineering")
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        # Empty evidence_classes with synthetic_only False → ready for review
        bundle["evidence_classes"] = []
        bundle["synthetic_only"] = False
        bundle["proxy_only"] = False
        return stages, bundle, "EVIDENCE_READY_FOR_REVIEW"

    if scenario == ScenarioId.INCOMPLETE_SOURCE:
        stages = _base_chain(
            scenario=scenario,
            source_status="incomplete",
            source_issue="source_manifest_incomplete",
            provenance_ok=False,
        )
        # Force missing source checksum
        stages[0].payload["source_checksum"] = None
        stages[0].visible_issue = "source_manifest_incomplete"
        stages[0] = _stage(
            "source",
            stages[0].record_id,
            "incomplete",
            [],
            stages[0].payload,
            visible_issue="source_manifest_incomplete",
        )
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        return stages, bundle, "PROVENANCE_FAILURE"

    if scenario == ScenarioId.PARTIAL_SUBJECT_SET:
        stages = _base_chain(
            scenario=scenario,
            subjects=["sub-01", "sub-02", "sub-03"],
            source_issue="partial_subject_set",
            run_status="partial",
            run_issue="partial_subject_set",
        )
        stages[0].payload["minimum_required_subjects"] = 8
        stages[0].payload["subject_count"] = 3
        stages[0] = _stage(
            "source",
            stages[0].record_id,
            "partial",
            [],
            stages[0].payload,
            visible_issue="partial_subject_set",
        )
        # Keep artifact lineage complete so the incomplete decision comes from
        # non-terminal partial work units (not artifact collapse).
        for idx, stage in enumerate(stages):
            if stage.stage == "artifact":
                payload = dict(stage.payload)
                payload["lineage_complete"] = True
                payload["output_checksums"] = ["out_partial"]
                payload["input_checksums"] = ["in_partial"]
                stages[idx] = _stage(
                    "artifact",
                    stage.record_id,
                    "partial",
                    stage.parent_ids,
                    payload,
                    visible_issue="partial_subject_set",
                )
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        return stages, bundle, "EVIDENCE_INCOMPLETE"

    if scenario == ScenarioId.FAILED_SIMULATION:
        stages = _base_chain(
            scenario=scenario,
            run_status="failed",
            run_issue="simulation_failed",
            validation_status="failed",
            validation_issue="simulation_failed",
        )
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        return stages, bundle, "VALIDATION_FAILURE"

    if scenario == ScenarioId.TIMEOUT:
        stages = _base_chain(
            scenario=scenario,
            run_status="timeout",
            run_issue="run_timeout",
            validation_status="failed",
            validation_issue="run_timeout",
        )
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        bundle["validation_status"] = "failed"
        return stages, bundle, "VALIDATION_FAILURE"

    if scenario == ScenarioId.MISSING_VALIDATION_REPORT:
        stages = _base_chain(
            scenario=scenario,
            validation_present=False,
        )
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        return stages, bundle, "VALIDATION_FAILURE"

    if scenario == ScenarioId.INVALID_PROVENANCE:
        stages = _base_chain(
            scenario=scenario,
            provenance_ok=False,
            source_issue="invalid_provenance",
        )
        stages[0].payload["source_checksum"] = None
        stages[0] = _stage(
            "source",
            stages[0].record_id,
            "invalid",
            [],
            stages[0].payload,
            visible_issue="invalid_provenance",
        )
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        bundle["code_commit"] = None
        bundle["seed"] = None
        bundle["configuration_locked"] = False
        bundle["input_provenance_complete"] = False
        return stages, bundle, "PROVENANCE_FAILURE"

    if scenario == ScenarioId.NETWORK_POLICY_VIOLATION:
        stages = _base_chain(scenario=scenario)
        stages[0].payload["network_accessed"] = True
        stages[0].payload["full_dataset_download"] = True
        stages[0] = _stage(
            "source",
            stages[0].record_id,
            "violated",
            [],
            stages[0].payload,
            visible_issue="network_policy_violation",
        )
        bundle = chain_to_release_bundle(
            stages,
            scenario=scenario,
            expected_overrides={
                "network_policy_violated": True,
                "full_dataset_download": True,
            },
        )
        return stages, bundle, "NETWORK_POLICY_FAILURE"

    if scenario == ScenarioId.SYNTHETIC_ONLY:
        stages = _base_chain(scenario=scenario, evidence_class="synthetic")
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        bundle["synthetic_only"] = True
        bundle["proxy_only"] = False
        bundle["evidence_classes"] = ["synthetic"]
        return stages, bundle, "SYNTHETIC_ONLY"

    if scenario == ScenarioId.PROXY_ONLY:
        stages = _base_chain(scenario=scenario, evidence_class="proxy")
        bundle = chain_to_release_bundle(stages, scenario=scenario)
        bundle["proxy_only"] = True
        bundle["synthetic_only"] = False
        bundle["evidence_classes"] = ["proxy"]
        return stages, bundle, "PROXY_ONLY"

    raise ValueError(f"unknown scenario: {scenario}")


def all_scenarios() -> List[ScenarioId]:
    return list(ScenarioId)


def fixture_checksum(stages: List[StageRecord], bundle: Dict[str, Any]) -> str:
    return _checksum({"stages": [s.to_dict() for s in stages], "bundle": bundle})
