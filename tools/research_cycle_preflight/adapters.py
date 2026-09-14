"""Read-only adapters over the real, already-merged validators.

Every function here does exactly one thing: normalize this preflight's
input shape into the real validator's expected input, call the real
validator, and return its own ``to_dict()`` (or an equivalent plain
dict) unmodified. None of these adapters re-derive a decision the real
validator already makes, and none of them fabricates a value for a
field a caller left out -- an absent field stays absent.

Every failure mode fails closed: if a real validator cannot be run
because its input is malformed, the adapter reports that as a hard
blocker rather than silently skipping the check or defaulting to a
permissive result.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from tools.research_plan_quality.models import ResearchPlan
from tools.research_plan_quality.rubric import evaluate_plan
from tools.research_claim_gate.gate import evaluate_claim
from tools.simulation_artifacts.extractor import extract_run
from tools.data_access.policy_enforcement.policy import DEFAULT_POLICY, DataAccessPolicy

_PLAN_SHAPE_BLOCKER = (
    "plan_shape: the supplied plan could not be read by the research-plan rubric ({error}); "
    "an unreadable plan is treated as a hard blocker, never as an empty-but-passing plan"
)
_ARTIFACT_READ_BLOCKER = (
    "artifact_lineage: prior_run_dir could not be read by the simulation-artifact extractor ({error})"
)


def run_plan_rubric(plan_data: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Compose ``tools.research_plan_quality.rubric.evaluate_plan``.

    A missing or malformed plan is not silently treated as an empty,
    all-warnings plan: it is reported as its own hard blocker so a
    caller cannot bypass the rubric by sending an unparseable shape.
    """
    try:
        plan = ResearchPlan.from_dict(dict(plan_data or {}))
    except TypeError as exc:
        empty_result = evaluate_plan(ResearchPlan())
        payload = empty_result.to_dict()
        blocker = _PLAN_SHAPE_BLOCKER.format(error=str(exc))
        payload["overall_status"] = "BLOCKED"
        payload["hard_blockers"] = [blocker, *payload["hard_blockers"]]
        payload["recommended_revisions"] = [blocker, *payload["recommended_revisions"]]
        return payload
    result = evaluate_plan(plan)
    return result.to_dict()


def run_claim_gate(claim_data: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Compose ``tools.research_claim_gate.gate.evaluate_claim``.

    Returns ``None`` when no claim was supplied -- a preflight run
    before a claim has even been drafted has nothing to check here, and
    that absence must read as "not applicable", never as "admissible".
    """
    if claim_data is None:
        return None
    result = evaluate_claim(dict(claim_data))
    return result.to_dict()


def run_artifact_lineage(prior_run_dir: Optional[str]) -> Optional[dict[str, Any]]:
    """Compose ``tools.simulation_artifacts.extractor.extract_run``.

    Returns ``None`` when no prior run directory was supplied (a fresh
    cycle with nothing to trace lineage against). A directory that
    cannot be read is reported as a synthetic ``BLOCKED`` lineage
    record rather than silently omitted, so a caller cannot bypass the
    lineage check by pointing at a nonexistent path.
    """
    if prior_run_dir is None:
        return None
    try:
        return extract_run(prior_run_dir)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "schema_version": "NeuroTopologySim.SimulationArtifactLineage.v1",
            "status": "BLOCKED",
            "read_only": True,
            "solver_executed": False,
            "heavy_runtime_imported": False,
            "diagnostics": {
                "missing": [], "stale": [], "partial": [], "failed": [], "conflicting": [],
                "errors": [_ARTIFACT_READ_BLOCKER.format(error=str(exc))],
            },
            "artifact_manifest": {"run_directory": str(prior_run_dir), "artifacts": [], "duplicate_content": []},
            "provenance": {},
            "evidence": {"evidence_class": None, "claim_scope": None, "synthetic": None},
            "relationships": [],
            "ledger_reference": None,
            "incremental_scan": {"previous_manifest_used": False, "checksums_reused": 0},
        }


def classify_data_access(
    request: Optional[Mapping[str, Any]], *, policy: DataAccessPolicy = DEFAULT_POLICY
) -> dict[str, Any]:
    """Classify a declared acquisition request against the real, declared
    :class:`DataAccessPolicy` -- read as a reference contract, never
    mutated and never re-scanned here (the real static scanner audits
    source code, not a single cycle's declared request).

    An undeclared field is never assumed permissive: no network
    request, no bounded-transfer declaration, and no checksum
    declaration is the default, matching the policy's own
    ``network_enabled_by_default = False``.
    """
    request = dict(request or {})
    network_requested = bool(request.get("network_access_requested", False))
    full_dataset_download_requested = bool(request.get("full_dataset_download_requested", False))
    bounded_transfer_declared = bool(request.get("bounded_transfer_declared", False))
    checksum_declared = bool(request.get("checksum_declared", False))

    violations: list[str] = []
    if full_dataset_download_requested and policy.full_dataset_download_policy == "reject":
        violations.append("FULL_DATASET_DOWNLOAD_REJECTED")
    if network_requested and policy.bounded_transfer_required and not bounded_transfer_declared:
        violations.append("BOUNDED_TRANSFER_NOT_DECLARED")

    if not network_requested:
        checksum_classification = "not_applicable"
    elif checksum_declared:
        checksum_classification = "checksum_declared"
    else:
        # Matches the policy's own checksum_policy string verbatim:
        # "checksum_required_when_source_provides_one; missing_is_unknown".
        checksum_classification = "checksum_unknown"

    if violations:
        status = "BLOCKED"
    elif checksum_classification == "checksum_unknown":
        status = "REVIEW_REQUIRED"
    else:
        status = "CLEAR"

    return {
        "network_access_requested": network_requested,
        "full_dataset_download_requested": full_dataset_download_requested,
        "bounded_transfer_declared": bounded_transfer_declared,
        "checksum_declared": checksum_declared,
        "checksum_classification": checksum_classification,
        "policy_network_enabled_by_default": policy.network_enabled_by_default,
        "policy_full_dataset_download_policy": policy.full_dataset_download_policy,
        "policy_bounded_transfer_required": policy.bounded_transfer_required,
        "policy_checksum_policy": policy.checksum_policy,
        "violations": violations,
        "status": status,
    }

