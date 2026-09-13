"""Fixture-only command-center payload for promotion-gate status."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA_VERSION = "command-center-evidence-promotion/v1"


def build_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    results = list(report.get("results") or [])
    counts: dict[str, int] = {}
    fingerprints = []
    for item in results:
        decision = str(item.get("promotion_decision") or "unknown")
        counts[decision] = counts.get(decision, 0) + 1
        combined = (item.get("input_fingerprints") or {}).get("combined")
        if combined:
            fingerprints.append(combined)
    return {
        "schema_version": SCHEMA_VERSION,
        "input_fingerprint": fingerprints[0] if len(fingerprints) == 1 else sorted(fingerprints),
        "claim_scope": "engineering_promotion_gate",
        "evidence_state": "not_validated_in_repo",
        "scientific_pass": False,
        "scientific_status": "INCONCLUSIVE",
        "synthetic_status": "NOT_SUPPORTED",
        "live_api_calls_enabled": False,
        "network_required": False,
        "api_keys_required": False,
        "diagnosis_claims_allowed": False,
        "treatment_claims_allowed": False,
        "ontology_promotion_allowed": False,
        "proof_claims_allowed": False,
        "case_count": report.get("case_count", len(results)),
        "decision_counts": counts,
        "cases": [
            {
                "case_id": item.get("case_id"),
                "promotion_decision": item.get("promotion_decision"),
                "declared_evidence_class": item.get("declared_evidence_class"),
                "allowed_evidence_class": item.get("allowed_evidence_class"),
                "synthetic_demo": item.get("synthetic_demo"),
                "scientific_pass": False,
            }
            for item in results
        ],
        "limitations": [
            "Fixture-only status board.",
            "Does not confirm biology, consciousness, or a theory of everything.",
            "Does not promote synthetic, proxy, or literature-hypothesis records.",
        ],
        "next_actions": ["manual review of BLOCK_PROMOTION and HOLD_* cases"],
    }
