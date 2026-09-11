"""Optional black-box probes of production consumers that exist on origin/main.

Missing Batch 1 modules are reported as PENDING. This file never invents them.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

PENDING_MODULES = (
    "awareness_studio.research_cycle",
)

ON_MAIN_MODULES = (
    "configs.empirical_sources.manifest",
    "tools.research_cycle",
    "runs.run_record",
    "tools.integration_bridge.artifact_manifest",
    "tools.performance.release_evidence_gate",
)


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def pending_producers() -> list[str]:
    return [name for name in PENDING_MODULES if not module_available(name)]


def available_main_producers() -> list[str]:
    return [name for name in ON_MAIN_MODULES if module_available(name)]


def probe_empirical_source(payload: dict[str, Any]) -> dict[str, Any]:
    from configs.empirical_sources.manifest import validate_manifest

    report = validate_manifest(payload)
    return report.to_dict()


def probe_research_cycle(payload: dict[str, Any]) -> dict[str, Any]:
    from tools.research_cycle import (
        ExperimentPlan,
        HypothesisRecord,
        PromotionBlockedError,
        ResearchCycleRegistry,
        check_promotion_gates,
    )
    from tools.research_cycle.schema import EvidenceUpdate, HypothesisStatus

    registry = ResearchCycleRegistry(registry_id=str(payload.get("registry_id") or "fixture"))
    hyp_data = next(iter(payload["hypotheses"].values()))
    plan_data = next(iter(payload["plans"].values()))
    hypothesis = HypothesisRecord(
        hypothesis_id=hyp_data["hypothesis_id"],
        precise_claim=hyp_data["precise_claim"],
        construct_definitions=hyp_data["construct_definitions"],
        operational_variables=hyp_data["operational_variables"],
        predicted_direction=hyp_data["predicted_direction"],
        null_prediction=hyp_data["null_prediction"],
        alternative_explanations=list(hyp_data["alternative_explanations"]),
        falsification_criterion=hyp_data["falsification_criterion"],
        min_sample_size_or_power=hyp_data["min_sample_size_or_power"],
        preregistration_reference=hyp_data["preregistration_reference"],
        data_requirements=list(hyp_data["data_requirements"]),
        analysis_plan=hyp_data["analysis_plan"],
        provenance=dict(hyp_data["provenance"]),
        epistemic_label=hyp_data["epistemic_label"],
        status=hyp_data["status"],
    )
    registry.register_hypothesis(hypothesis)
    plan = ExperimentPlan(
        plan_id=plan_data["plan_id"],
        hypothesis_id=plan_data["hypothesis_id"],
        domain=plan_data["domain"],
        design_type=plan_data["design_type"],
        variables=plan_data["variables"],
        target_sample_size=plan_data["target_sample_size"],
        power_analysis=plan_data["power_analysis"],
        analysis_protocol=plan_data["analysis_protocol"],
        surrogate_method=plan_data.get("surrogate_method"),
        data_source=plan_data.get("data_source", ""),
        is_synthetic=bool(plan_data.get("is_synthetic")),
        provenance=dict(plan_data.get("provenance") or {}),
    )
    registry.register_experiment_plan(plan)

    blocked = None
    try:
        check_promotion_gates(
            registry.get_hypothesis(hypothesis.hypothesis_id),
            HypothesisStatus.SUPPORTED_AS_SPECIFIED.value,
        )
    except PromotionBlockedError as exc:
        blocked = str(exc)

    exported = registry.to_dict()
    exported["promotion_blocked"] = blocked
    return exported


def probe_run_record(payload: dict[str, Any]) -> dict[str, Any]:
    from runs.run_record import RunRecordV1

    record = RunRecordV1.from_dict(payload)
    encoded = record.to_dict()
    round_trip = RunRecordV1.from_dict(json.loads(json.dumps(encoded))).to_dict()
    if round_trip["run_id"] != record.run_id:
        raise AssertionError("run_id changed across serialization")
    return round_trip


def probe_artifact_manifest(output_dir: Path, relative_paths: list[str], run_id: str) -> dict[str, Any]:
    from tools.integration_bridge.artifact_manifest import build_manifest

    manifest = build_manifest(
        run_id=run_id,
        output_dir=output_dir,
        artifact_relative_paths=relative_paths,
        metadata={"data_mode": "synthetic"},
    )
    return manifest.to_dict()


def probe_release_evidence(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    from tools.performance.release_evidence_gate import evaluate_release_evidence

    report = evaluate_release_evidence(baseline, candidate)
    return report.to_dict()
