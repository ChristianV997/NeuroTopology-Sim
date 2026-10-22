"""Stage executors for the fixed allowlist (in-process only)."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from tools.batch3_offline_integration.allowlist import STAGE_BY_ID, StageSpec, resolve_callable
from tools.batch3_offline_integration.fixture_producers import (
    _read_fixture,
    display_fixture_name,
    load_workflow_request,
    substitute_artifact_lineage,
    synthetic_registry_payload,
)
from tools.batch3_offline_integration.schema import ExecutionMode, StageOutcome
from tools.batch3_offline_integration.serialization import contains_nonfinite, json_safe, sha256_hex

_ADMISSIBLE_CLAIM_STAGE_DECISIONS = frozenset(
    {
        "CLAIM_ADMISSIBLE",
        "CLAIM_SYNTHETIC_ONLY",
        "CLAIM_REQUIRES_REVIEW",
        "CLAIM_DOWNGRADED",
    }
)
_ADMISSIBLE_RELEASE_STAGE_DECISIONS = frozenset({"SYNTHETIC_ONLY"})


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
        "fixture_name": display_fixture_name(fixture_name),
        "prior_run_dir_supplied": prior_run_dir is not None,
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
        record["inputs"] = {"fixture_name": display_fixture_name(fixture_name)}
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

    # Dependency gate for required upstream outcomes: required stages must have
    # explicitly succeeded (never substituted); optional stages may be substituted.
    failed_deps = []
    for dep in spec.depends_on:
        dep_rec = context.get("stages", {}).get(dep) or {}
        dep_spec = STAGE_BY_ID.get(dep)
        allowed_outcomes = (
            {StageOutcome.SUCCEEDED.value}
            if (dep_spec is None or dep_spec.required)
            else {StageOutcome.SUCCEEDED.value, StageOutcome.FIXTURE_SUBSTITUTED.value}
        )
        if dep_rec.get("outcome") not in allowed_outcomes:
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
    record["inputs"] = {"plan_keys": sorted(plan_data.keys()) if isinstance(plan_data, Mapping) else []}
    if not isinstance(plan_data, Mapping):
        record["outcome"] = StageOutcome.REJECTED_INVALID_INPUT.value
        record["error"] = "plan_absent"
        return record
    try:
        plan = ResearchPlan.from_dict(dict(plan_data))
        result = fn(plan)
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if contains_nonfinite(payload):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_plan_output"
            return record
        record["outputs"] = json_safe(payload)
        record["actual_upstream_producer_ran"] = True
        status = payload.get("overall_status")
        if status == "READY_FOR_EXECUTION":
            record["outcome"] = StageOutcome.SUCCEEDED.value
        elif status == "BLOCKED":
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "plan_blocked"
        elif status == "NEEDS_REVISION":
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "plan_needs_revision"
        else:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = f"plan_unrecognized_status:{status}"
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
    record["inputs"] = {"claim_present": isinstance(claim, Mapping)}
    if not isinstance(claim, Mapping):
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
        if payload.get("scientific_pass") is True:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "scientific_pass_emitted_forbidden"
        elif decision in _ADMISSIBLE_CLAIM_STAGE_DECISIONS:
            # Explicit allowlist of admissible engineering / synthetic decisions only.
            record["outcome"] = StageOutcome.SUCCEEDED.value
        else:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = str(decision or "claim_unrecognized_decision")
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
        "has_plan": isinstance(request.get("plan"), Mapping),
        "has_claim": isinstance(request.get("claim"), Mapping),
        "data_access_request": request.get("data_access_request") or {},
    }
    if not isinstance(request.get("plan"), Mapping) or not isinstance(request.get("claim"), Mapping):
        record["outcome"] = StageOutcome.REJECTED_INVALID_INPUT.value
        record["error"] = "preflight_missing_plan_or_claim"
        return record
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
        if (
            payload.get("cleared_for_execution") is True
            and payload.get("operational_readiness") == "READY"
        ):
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
        hyp_ids = sorted(exported.get("hypotheses") or {})
        plan_ids = sorted(exported.get("plans") or {})
        record["outputs"] = {
            "registry_id": exported.get("registry_id"),
            "schema_version": exported.get("schema_version"),
            "hypothesis_ids": hyp_ids,
            "plan_ids": plan_ids,
            "fixture_producer_used_for_inputs": True,
            "checksum": sha256_hex(
                {
                    "hypotheses": exported.get("hypotheses"),
                    "plans": exported.get("plans"),
                }
            ),
        }
        record["actual_upstream_producer_ran"] = True
        if hyp_ids and plan_ids:
            record["outcome"] = StageOutcome.SUCCEEDED.value
        else:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "registry_incomplete"
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

    bundle_name = "release_bundle_synthetic.json"
    record["execution_mode"] = ExecutionMode.ALLOWLISTED_CALLABLE.value
    record["inputs"] = {"bundle_fixture": bundle_name}
    try:
        bundle = _read_fixture(bundle_name)
    except Exception as exc:
        record["outcome"] = StageOutcome.REJECTED_INVALID_INPUT.value
        record["error"] = type(exc).__name__
        return record
    if contains_nonfinite(bundle):
        record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
        record["error"] = "nonfinite_in_release_bundle"
        return record
    try:
        report = fn(bundle, adapter_hint="generic")
        payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        if contains_nonfinite(payload):
            record["outcome"] = StageOutcome.REJECTED_NONFINITE.value
            record["error"] = "nonfinite_release_output"
            return record
        decision = payload.get("decision")
        # Keep report compact for determinism (drop bulky nested bundle if present).
        compact = {
            "decision": decision,
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
        elif compact.get("bayes_factor_emitted") is True:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = "bayes_factor_emitted_forbidden"
        elif (
            decision in _ADMISSIBLE_RELEASE_STAGE_DECISIONS
            and compact.get("synthetic_flag") is True
        ):
            record["outcome"] = StageOutcome.SUCCEEDED.value
        else:
            record["outcome"] = StageOutcome.FAILED.value
            record["error"] = f"release_decision_not_admissible:{decision}"
        return record
    except Exception as exc:
        record["outcome"] = StageOutcome.FAILED.value
        record["error"] = type(exc).__name__
        return record


def _run_optional_lineage(
    spec: StageSpec, record: Dict[str, Any], *, prior_run_dir: Optional[str]
) -> Dict[str, Any]:
    if prior_run_dir is not None:
        # This harness is fixture-only. Never scan caller-controlled run trees:
        # they may contain participant or dataset payloads.
        record["execution_mode"] = ExecutionMode.NOT_EXECUTED.value
        record["outcome"] = StageOutcome.REJECTED_INVALID_INPUT.value
        record["inputs"] = {"prior_run_dir_supplied": True}
        record["error"] = "caller_run_directory_not_scanned"
        record["actual_upstream_producer_ran"] = False
        return record

    if prior_run_dir is None:
        record["execution_mode"] = ExecutionMode.FIXTURE_SUBSTITUTE.value
        record["outcome"] = StageOutcome.SKIPPED_OPTIONAL_ABSENT.value
        record["missing_dependency"] = "prior_run_dir"
        record["outputs"] = substitute_artifact_lineage(
            missing_dependency="prior_run_dir",
            reason="optional prior_run_dir not supplied; fixture substitute recorded",
        )
        record["actual_upstream_producer_ran"] = False
        return record
    raise AssertionError("unreachable optional lineage state")
