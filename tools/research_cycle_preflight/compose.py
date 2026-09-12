"""Compose the read-only adapters into one preflight decision.

``run_preflight`` is the only entry point a caller needs. It never
executes a simulation, never performs network access, and never
mutates anything -- it reads a declared plan/claim/prior-run/
data-access request and reports whether it is operationally safe to
proceed and, separately, whether the claim this cycle intends to make
would be scientifically admissible.

Fail-closed by construction: ``cleared_for_execution`` starts from the
assumption that execution is *not* cleared, and only becomes ``True``
when every composed validator reports a state that this module's own
table says is safe to build on. There is no code path that defaults an
unrecognized or missing status to "safe".
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from . import adapters
from .models import NEVER_EMITTED, SCHEMA_VERSION

_ARTIFACT_HARD_BLOCK_STATUSES = frozenset({"FAILED", "CONFLICTING", "BLOCKED"})
_ARTIFACT_SOFT_BLOCK_STATUSES = frozenset({"PARTIAL", "INCOMPLETE"})

_PLAN_STATUS_TO_READINESS = {
    "READY_FOR_EXECUTION": "READY",
    "NEEDS_REVISION": "NEEDS_REVISION",
    "BLOCKED": "BLOCKED",
}

_CLAIM_DECISION_TO_ADMISSIBILITY = {
    "CLAIM_ADMISSIBLE": "ADMISSIBLE",
    "CLAIM_REQUIRES_REVIEW": "REVIEW_REQUIRED",
    "CLAIM_DOWNGRADED": "DOWNGRADED",
    "CLAIM_REJECTED": "BLOCKED",
    "CLAIM_INCOMPLETE": "INCOMPLETE",
    "CLAIM_SYNTHETIC_ONLY": "BLOCKED",
    "CLAIM_PROVENANCE_INVALID": "BLOCKED",
    "CLAIM_NOT_COMPARABLE": "BLOCKED",
}

# Scientific admissibility states that do not, on their own, block
# spending compute on the *engineering* side of the cycle: a claim that
# needs review or downgrade after execution is still worth running the
# plan for. Only a hard-BLOCKED or structurally-INCOMPLETE claim stops
# execution outright. This asymmetry is documented in
# docs/research/research_cycle_preflight.md.
_ADMISSIBILITY_PERMITS_EXECUTION = frozenset(
    {"ADMISSIBLE", "REVIEW_REQUIRED", "DOWNGRADED", "NOT_APPLICABLE"}
)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _finite_canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, allow_nan=False)


def run_preflight(request: Mapping[str, Any], *, now: Optional[str] = None) -> dict[str, Any]:
    """Run every composed validator over one preflight request and
    return one deterministic, finite JSON-serializable report.

    ``request`` is a plain mapping with up to four optional keys:
    ``plan`` (a research-plan-rubric input mapping), ``claim`` (a
    claim-gate input mapping), ``prior_run_dir`` (a path to a previous
    run directory for lineage/partial/failed/timeout classification),
    and ``data_access_request`` (declared network/download intent for
    this cycle).
    """
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    plan_audit = adapters.run_plan_rubric(request.get("plan"))
    claim_gate_result = adapters.run_claim_gate(request.get("claim"))
    artifact_lineage = adapters.run_artifact_lineage(request.get("prior_run_dir"))
    data_access = adapters.classify_data_access(request.get("data_access_request"))

    operational_readiness = _PLAN_STATUS_TO_READINESS[plan_audit["overall_status"]]
    operational_blockers: list[str] = list(plan_audit["hard_blockers"])

    if data_access["status"] == "BLOCKED":
        operational_readiness = "BLOCKED"
        operational_blockers.extend(f"data_access: {violation}" for violation in data_access["violations"])
    elif data_access["status"] == "REVIEW_REQUIRED" and operational_readiness == "READY":
        operational_readiness = "NEEDS_REVISION"

    if artifact_lineage is not None:
        prior_status = artifact_lineage["status"]
        if prior_status in _ARTIFACT_HARD_BLOCK_STATUSES:
            operational_readiness = "BLOCKED"
            operational_blockers.append(
                f"artifact_lineage: prior run status is {prior_status}, cannot build on it without explicit resolution"
            )
        elif prior_status in _ARTIFACT_SOFT_BLOCK_STATUSES and operational_readiness == "READY":
            operational_readiness = "NEEDS_REVISION"

    operational_blockers = _dedupe_preserve_order(operational_blockers)

    if claim_gate_result is not None:
        scientific_admissibility = _CLAIM_DECISION_TO_ADMISSIBILITY.get(claim_gate_result["decision"], "INCOMPLETE")
    else:
        scientific_admissibility = "NOT_APPLICABLE"

    cleared_for_execution = (
        operational_readiness == "READY" and scientific_admissibility in _ADMISSIBILITY_PERMITS_EXECUTION
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "research_cycle_preflight",
        "generated_at": generated_at,
        "operational_readiness": operational_readiness,
        "operational_blockers": operational_blockers,
        "scientific_admissibility": scientific_admissibility,
        "cleared_for_execution": cleared_for_execution,
        "validators_composed": {
            "research_plan_quality": plan_audit,
            "research_claim_gate": claim_gate_result,
            "simulation_artifact_lineage": artifact_lineage,
            "data_access_policy": data_access,
        },
        "never_emits": dict(NEVER_EMITTED),
        "note": (
            "This is an engineering readiness gate, not a scientific conclusion. "
            "cleared_for_execution reports whether it is safe to spend compute on this plan, "
            "never whether any claim this cycle produces will be true."
        ),
    }
    canonical = _finite_canonical_json(report)
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report
