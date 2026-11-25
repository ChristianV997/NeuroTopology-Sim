"""Claim-record schema and closed classification vocabularies.

Field names are stable. The auditor never mutates a claim record's ``text``.
"""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA_ID = "NeuroTopology.ResearchClaim.v1"
AUDITOR_ID = "research_claim_auditor"
AUDITOR_VERSION = "1.0.0"

CLAIM_CATEGORIES: tuple[str, ...] = (
    "engineering_fact",
    "benchmark_result",
    "synthetic_demonstration",
    "empirical_observation",
    "proxy_inference",
    "formal_statistical_evidence",
    "hypothesis",
    "speculation",
    "unsupported_claim",
    "historical_context",
)

EVIDENCE_CLASSES: tuple[str, ...] = CLAIM_CATEGORIES

EMPIRICAL_SYNTHETIC_STATUSES: tuple[str, ...] = (
    "empirical",
    "synthetic",
    "mixed",
    "unknown",
    "not_applicable",
)

PROXY_FORMAL_STATUSES: tuple[str, ...] = (
    "proxy",
    "formal",
    "not_applicable",
    "unknown",
)

REVIEWER_STATES: tuple[str, ...] = (
    "pending",
    "accepted",
    "rejected",
    "needs_revision",
    "historical",
    "downgraded",
)

CLAIM_RECORD_FIELDS: tuple[str, ...] = (
    "claim_id",
    "text",
    "claim_category",
    "evidence_class",
    "provenance_reference",
    "data_origin",
    "empirical_synthetic_status",
    "proxy_formal_status",
    "test_reference",
    "required_controls",
    "falsifiability_condition",
    "allowed_language",
    "prohibited_language",
    "reviewer_state",
    "last_reviewed",
)

FIELD_ALIASES: Mapping[str, str] = {
    "claim ID": "claim_id",
    "claim_id": "claim_id",
    "id": "claim_id",
    "text": "text",
    "claim": "text",
    "claim category": "claim_category",
    "claim_category": "claim_category",
    "category": "claim_category",
    "evidence class": "evidence_class",
    "evidence_class": "evidence_class",
    "provenance reference": "provenance_reference",
    "provenance_reference": "provenance_reference",
    "provenance": "provenance_reference",
    "data origin": "data_origin",
    "data_origin": "data_origin",
    "empirical/synthetic status": "empirical_synthetic_status",
    "empirical_synthetic_status": "empirical_synthetic_status",
    "empirical_or_synthetic": "empirical_synthetic_status",
    "proxy/formal status": "proxy_formal_status",
    "proxy_formal_status": "proxy_formal_status",
    "proxy_or_formal": "proxy_formal_status",
    "test reference": "test_reference",
    "test_reference": "test_reference",
    "required controls": "required_controls",
    "required_controls": "required_controls",
    "falsifiability condition": "falsifiability_condition",
    "falsifiability_condition": "falsifiability_condition",
    "falsification_condition": "falsifiability_condition",
    "allowed language": "allowed_language",
    "allowed_language": "allowed_language",
    "prohibited language": "prohibited_language",
    "prohibited_language": "prohibited_language",
    "reviewer state": "reviewer_state",
    "reviewer_state": "reviewer_state",
    "last-reviewed marker": "last_reviewed",
    "last_reviewed": "last_reviewed",
    "last-reviewed": "last_reviewed",
}

MISSING_PROVENANCE_TOKENS = frozenset(
    {
        "",
        "none",
        "null",
        "nil",
        "n/a",
        "na",
        "unknown",
        "missing",
        "unspecified",
        "not_provided",
        "not provided",
    }
)

CATEGORIES_REQUIRING_PROVENANCE = frozenset(
    {
        "benchmark_result",
        "empirical_observation",
        "proxy_inference",
        "formal_statistical_evidence",
    }
)

CATEGORIES_EXEMPT_FROM_FALSIFIABILITY = frozenset(
    {
        "speculation",
        "historical_context",
        "unsupported_claim",
    }
)

PROMOTABLE_CATEGORIES = frozenset(
    {
        "empirical_observation",
        "formal_statistical_evidence",
        "benchmark_result",
    }
)


def normalize_field_name(name: str) -> str:
    key = str(name).strip()
    if key in FIELD_ALIASES:
        return FIELD_ALIASES[key]
    lowered = key.lower().replace("-", "_").replace(" ", "_")
    return FIELD_ALIASES.get(lowered, lowered)


def empty_optional() -> None:
    """Canonical missing-value representation in audit JSON: JSON null."""
    return None


def is_missing_text(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in MISSING_PROVENANCE_TOKENS:
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False
