"""Stage executors for the fixed allowlist (in-process only)."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from tools.batch3_offline_integration.allowlist import StageSpec, resolve_callable
from tools.batch3_offline_integration.fixture_producers import (
    load_workflow_request,
    substitute_artifact_lineage,
    synthetic_registry_payload,
)
from tools.batch3_offline_integration.schema import ExecutionMode, StageOutcome
from tools.batch3_offline_integration.serialization import contains_nonfinite, json_safe, load_json, sha256_hex


def _base_record(spec: StageSpec) -> Dict[str, Any]:
    return {
        "stage_id": spec.stage_id,
        "order": spec.order,
        "title": spec.title,
        "module": spec.module,
        "qualname": spec.qualname,
        "required": spec.required,
        "depends_on": list(spec.depends_on),
        "source_version": f"{spec.module}:{spec.qualname}",
        "configuration": {},
        "inputs": {},
        "outputs": {},
        "outcome": StageOutcome.FAILED.value,
        "execution_mode": ExecutionMode.NOT_EXECUTED.value,
        "actual_upstream_producer_ran": False,
        "missing_dependency": None,
        "error": None,
    }


def execute_stage(
    spec: StageSpec,
    *,
    context: Mapping[str, Any],
    fixture_name: str,
    force_fail_stage: Optional[str] = None,
    prior_run_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute one allowlisted stage or return a marked substitute/skip."""
    record = _base_record(spec)
    record["configuration"] = {
        "fixture_name": fixture_name,
        "prior_run_dir": prior_run_dir,
        "force_fail_stage": force_fail_stage,
    }

    if force_fail_stage == spec.stage_id:
        record["outcome"] = StageOutcome.FAILED.value
        record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
        record["error"] = "forced_stage_failure"
        record["actual_upstream_producer_ran"] = False
        return record

    if spec.stage_id == "load_synthetic_fixture":
        record["execution_mode"] = ExecutionMode.FIXTURE_PRODUCER.value
        record["inputs"] = {"fixture_name": fixture_name}
        try:
            output = load_workflow_request(fixture_name=fixture_name)
            if contains_nonfinite(output):
                record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
                record["error"] = "nonfinite_in_fixture"
                return record
            if output.get("request", {}).get("inject_nonfinite"):
                # Explicit probe path used by tests: reject before propagating.
                record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
                record["error"] = "inject_nonfinite_flag"
                record["outputs"] = {"flag": "inject_nonfinite"}
                return record
            record["outputs"] = json_safe(output)
            record["outcome"] = StageOutcome.SUCCEEDED.value
            record["actual_upstream_producer_ran"] = False
            return record
        except Exception as exc:
            record["outcome"] = StageOutcome.REJECTED_INVALID_INPUT.value
            record["error"] = f"{type(exc).__name__}"
            return record

    # Dependency gate for required upstream outcomes.
    failed_deps = []
    for dep in spec.depends_on:
        dep_rec = context.get("stages", {}).get(dep) or {}
        if dep_rec.get("outcome") not in {
            StageOutcome.SUCCEEDED.value,
            StageOutcome.FIXTURE_SUBSTITUTED.value,
        }:
            failed_deps.append(dep)
    if failed_deps:
        record["outcome"] = StageOutcome.SKIPPED_UPSTREAM_FAILED.value
        record["error"] = "upstream_failed:" + ",".join(failed_deps)
        record["inputs"] = {"failed_dependencies": failed_deps}
        return record

    request = ((context.get("stages", {}).get("load_synthetic_fixture") or {}).get("outputs") or {}).get(
        "request"
    ) or {}

    if spec.stage_id == "plan_quality":
        return _run_plan_quality(spec, record, request)
    if spec.stage_id == "claim_gate":
        return _run_claim_gate(spec, record, request)
    if spec.stage_id == "preflight":
        return _run_preflight(spec, record, request)
    if spec.stage_id == "registry_probe":
        return _run_registry(spec, record)
    if spec.stage_id == "release_evaluate":
        return _run_release(spec, record)
    if spec.stage_id == "optional_artifact_lineage":
        return _run_optional_lineage(spec, record, prior_run_dir=prior_run_dir)

    record["outcome"] = StageOutcome.FAILED.value
    record["error"] = "unhandled_stage"
    return record


def _run_plan_quality(spec: StageSpec, record: Dict[str, Any], request: Mapping[str, Any]) -> Dict[str, Any]:
    fn, missing = resolve_callable(spec)
    if fn is None:
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["missing_dependency"] = missing
        record["outputs"] = {
            "overall_status": "BLOCKED",
            "producer": "fixture_substitute",
            "actual_upstream_producer_ran": False,
            "missing_dependency": missing,
        }
        return record
    from tools.research_plan_quality.models import ResearchPlan

    plan_data = request.get("plan")
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {"plan_keys": sorted((plan_data or {}).keys()) if isinstance(plan_data, dict) else []}
    try:
        plan = ResearchPlan.from_dict(dict(plan_data or {}))
        result = fn(plan)
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if contains_nonfinite(payload):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_plan_output"
            return record
        record["outputs"] = json_safe(payload)
        record["actual_upstream_producer_ran"] = True
        status = payload.get("overall_status")
        if status == "BLOCKED":
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "plan_blocked"
        elif status == "NEEDS_REVISION":
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "plan_needs_revision"
        else:
            record["outcome"] = StageOutcome.SUCCEEDED.value
        return record
    except TypeError:
        record["outcome"] = StageOutcome.REJECTED_SCHEMA.value
        record["error"] = "plan_schema_incompatible"
        return record
    except Exception as exc:
        record["outcome"] = StageOutcome.FAILED.value
        record["error"] = type(exc).__name__
        return record


def _run_claim_gate(spec: StageSpec, record: Dict[str, Any], request: Mapping[str, Any]) -> Dict[str, Any]:
    fn, missing = resolve_callable(spec)
    if fn is None:
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["missing_dependency"] = missing
        record["outputs"] = {
            "decision": "CLAIM_INCOMPLETE",
            "producer": "fixture_substitute",
            "actual_upstream_producer_ran": False,
            "missing_dependency": missing,
        }
        return record
    claim = request.get("claim")
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {"claim_present": claim is not None}
    if claim is None:
        record["outcome"] = StageOutcome.REJECTED_INVALID_INPUT.value
        record["error"] = "claim_absent"
        return record
    try:
        result = fn(dict(claim))
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if contains_nonfinite(payload):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_claim_output"
            return record
        record["outputs"] = json_safe(payload)
        record["actual_upstream_producer_ran"] = True
        decision = payload.get("decision")
        if decision in {"CLAIM_REJECTED", "CLAIM_INCOMPLETE", "CLAIM_PROVENANCE_INVALID"}:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = str(decision)
        else:
            # CLAIM_SYNTHETIC_ONLY / engineering admissible paths succeed as engineering stages.
            record["outcome"] = StageOutcome.SUCCEEDED.value
        return record
    except Exception as exc:
        record["outcome"] = StageOutcome.FAILED.value
        record["error"] = type(exc).__name__
        return record


def _run_preflight(spec: StageSpec, record: Dict[str, Any], request: Mapping[str, Any]) -> Dict[str, Any]:
    fn, missing = resolve_callable(spec)
    if fn is None:
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["missing_dependency"] = missing
        record["outputs"] = {
            "cleared_for_execution": False,
            "producer": "fixture_substitute",
            "actual_upstream_producer_ran": False,
            "missing_dependency": missing,
        }
        return record
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {
        "has_plan": "plan" in request,
        "has_claim": "claim" in request,
        "data_access_request": request.get("data_access_request") or {},
    }
    try:
        payload = fn(
            {
                "plan": request.get("plan"),
                "claim": request.get("claim"),
                "data_access_request": request.get("data_access_request"),
            },
            now="2026-10-16T00:00:00Z",
        )
        if contains_nonfinite(payload):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_preflight_output"
            return record
        record["outputs"] = json_safe(payload)
        record["actual_upstream_producer_ran"] = True
        if payload.get("cleared_for_execution") is True:
            record["outcome"] = StageOutcome.SUCCEEDED.value
        else:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "preflight_not_cleared"
        return record
    except Exception as exc:
        record["outcome"] = StageOutcome.FAILED.value
        record["error"] = type(exc).__name__
        return record


def _run_registry(spec: StageSpec, record: Dict[str, Any]) -> Dict[str, Any]:
    cls, missing = resolve_callable(spec)
    if cls is None:
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["missing_dependency"] = missing
        record["outputs"] = {
            "producer": "fixture_substitute",
            "actual_upstream_producer_ran": False,
            "missing_dependency": missing,
        }
        return record
    from tools.research_cycle import ExperimentPlan, HypothesisRecord

    fixture = synthetic_registry_payload()
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {"fixture_producer": True, "hypothesis_id": fixture["hypothesis"]["hypothesis_id"]}
    try:
        registry = cls(registry_id="batch3-offline-integration")
        hyp = HypothesisRecord(**fixture["hypothesis"])
        plan = ExperimentPlan(**fixture["plan"])
        registry.register_hypothesis(hyp)
        registry.register_experiment_plan(plan)
        exported = registry.to_dict()
        if contains_nonfinite(exported):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_registry_output"
            return record
        record["outputs"] = {
            "registry_id": exported.get("registry_id"),
            "schema_version": exported.get("schema_version"),
            "hypothesis_ids": sorted(exported.get("hypotheses") or {}),
            "plan_ids": sorted(exported.get("plans") or {}),
            "fixture_producer_used_for_inputs": True,
            "checksum": sha256_hex(
                {
                    "hypotheses": exported.get("hypotheses"),
                    "plans": exported.get("plans"),
                }
            ),
        }
        record["actual_upstream_producer_ran"] = True
        record["outcome"] = StageOutcome.SUCCEEDED.value
        return record
    except TypeError:
        record["outcome"] = StageOutcome.REJECTED_SCHEMA.value
        record["error"] = "registry_schema_incompatible"
        return record
    except Exception as exc:
        record["outcome"] = StageOutcome.FAILED.value
        record["error"] = type(exc).__name__
        return record


def _run_release(spec: StageSpec, record: Dict[str, Any]) -> Dict[str, Any]:
    fn, missing = resolve_callable(spec)
    if fn is None:
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["missing_dependency"] = missing
        record["outputs"] = {
            "decision": "SYNTHETIC_ONLY",
            "producer": "fixture_substitute",
            "actual_upstream_producer_ran": False,
            "missing_dependency": missing,
        }
        return record
    from pathlib import Path

    from tools.batch3_offline_integration.fixture_producers import FIXTURE_DIR

    bundle_path = FIXTURE_DIR / "release_bundle_synthetic.json"
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {"bundle_fixture": str(bundle_path.name)}
    try:
        bundle = load_json(str(bundle_path))
        report = fn(bundle, adapter_hint="generic")
        payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        if contains_nonfinite(payload):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_release_output"
            return record
        # Keep report compact for determinism (drop bulky nested bundle if present).
        compact = {
            "decision": payload.get("decision"),
            "evidence_class": payload.get("evidence_class"),
            "synthetic_flag": payload.get("synthetic_flag"),
            "scientific_pass_emitted": payload.get("scientific_pass_emitted"),
            "bayes_factor_emitted": payload.get("bayes_factor_emitted"),
            "reason_codes": payload.get("reason_codes"),
            "result_label": "SYNTHETIC_ONLY",
        }
        record["outputs"] = json_safe(compact)
        record["actual_upstream_producer_ran"] = True
        if compact.get("scientific_pass_emitted") is True:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "scientific_pass_emitted_forbidden"
        else:
            record["outcome"] = StageOutcome.SUCCEEDED.value
        return record
    except Exception as exc:
        record["outcome"] = StageOutcome.FAILED.value
        record["error"] = type(exc).__name__
        return record


def _run_optional_lineage(
    spec: StageSpec, record: Dict[str, Any], *, prior_run_dir: Optional[str]
) -> Dict[str, Any]:
    if not prior_run_dir:
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["outcome"] = StageOutcome.SKIPPED_OPTIONAL_ABSENT.value
        record["missing_dependency"] = "prior_run_dir"
        record["outputs"] = substitute_artifact_lineage(
            missing_dependency="prior_run_dir",
            reason="optional prior_run_dir not supplied; fixture substitute recorded",
        )
        record["actual_upstream_producer_ran"] = False
        return record
    fn, missing = resolve_callable(spec)
    if fn is None:
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["missing_dependency"] = missing
        record["outputs"] = substitute_artifact_lineage(
            missing_dependency=str(missing),
            reason="optional extract_run unavailable",
        )
        return record
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {"prior_run_dir": prior_run_dir}
    try:
        payload = fn(prior_run_dir)
        record["outputs"] = json_safe(payload)
        record["actual_upstream_producer_ran"] = True
        record["outcome"] = StageOutcome.SUCCEEDED.value
        return record
    except Exception as exc:
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["outcome"] = StageOutcome.FIXTURE_SUBSTITUTED.value
        record["missing_dependency"] = f"extract_run_error:{type(exc).__name__}"
        record["outputs"] = substitute_artifact_lineage(
            missing_dependency=f"extract_run_error:{type(exc).__name__}",
            reason="optional lineage call failed; fixture substitute recorded",
        )
        record["actual_upstream_producer_ran"] = False
        return record
