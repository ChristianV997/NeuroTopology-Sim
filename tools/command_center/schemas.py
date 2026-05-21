from __future__ import annotations

from copy import deepcopy

BASE_RESPONSE = {
    "claim_scope": "engineering_runtime_or_research_hypothesis",
    "evidence_state": "artifact_retrieval_only",
    "guardrails_applied": [
        "no_ontology_promotion",
        "q_qabs_fdress_candidate_telemetry_only",
        "tol_quarantine_respected",
    ],
    "source_artifacts": [],
}


def with_base(payload: dict) -> dict:
    merged = deepcopy(BASE_RESPONSE)
    merged.update(payload)
    return merged
