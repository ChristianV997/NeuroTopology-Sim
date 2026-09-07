"""Deterministic claim auditor.

The auditor records violations and recommended downgrades. It copies the
original claim fields into the report and never rewrites ``text`` or any
numeric scientific result.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import language_rules as rules
from .json_util import NonFiniteJsonError, assert_finite_or_null
from .schema import (
    AUDITOR_ID,
    AUDITOR_VERSION,
    CATEGORIES_EXEMPT_FROM_FALSIFIABILITY,
    CATEGORIES_REQUIRING_PROVENANCE,
    CLAIM_CATEGORIES,
    CLAIM_RECORD_FIELDS,
    EMPIRICAL_SYNTHETIC_STATUSES,
    PROMOTABLE_CATEGORIES,
    PROXY_FORMAL_STATUSES,
    REVIEWER_STATES,
    SCHEMA_ID,
    is_missing_text,
    normalize_field_name,
)

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_DOWNGRADED = "DOWNGRADED"

_RULE_CODES = {
    "R1_SYNTHETIC_NOT_BIOLOGY": "Synthetic output cannot support biological confirmation.",
    "R2_PROXY_K_NOT_FORMAL": "Proxy K cannot be called a formal Bayes factor.",
    "R3_BETA1_NOT_CONSCIOUSNESS": "A numerical beta-1 proxy cannot be called proof of consciousness.",
    "R4_GRAPH_BETA1_NOT_SPATIAL": "Graph beta-1 cannot be called spatial topological charge.",
    "R5_EP_NOT_BIO_TRANSITION": (
        "A fitted exceptional point cannot be called a biological phase "
        "transition without empirical validation."
    ),
    "R6_SIM_NOT_BIO_QUANTUM": (
        "A decoherence simulation cannot be called evidence of biological "
        "quantum coherence without independently validated inputs."
    ),
    "R7_MISSING_PROVENANCE": "Missing provenance must downgrade claims.",
    "R8_NO_FALSIFIER": "Claims must contain a falsification condition or be labeled speculation.",
    "R9_UNCERTAINTY_ERASED": "Reports must preserve uncertainty and limitations.",
    "R10_NO_REWRITE": "The validator must never rewrite scientific results.",
    "SCHEMA_INVALID": "Claim record failed schema validation.",
    "LANGUAGE_PROHIBITED": "Claim text contains prohibited promotional language.",
    "CATEGORY_EVIDENCE_MISMATCH": "Declared category is inconsistent with declared evidence status.",
}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def normalize_claim(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map aliases onto canonical fields. Does not edit ``text`` content."""
    incoming: dict[str, Any] = {}
    for key, value in raw.items():
        incoming[normalize_field_name(str(key))] = value
    claim: dict[str, Any] = {}
    for field in CLAIM_RECORD_FIELDS:
        claim[field] = incoming.get(field, None)
    if claim["allowed_language"] is None:
        claim["allowed_language"] = []
    else:
        claim["allowed_language"] = _as_list(claim["allowed_language"])
    if claim["prohibited_language"] is None:
        claim["prohibited_language"] = []
    else:
        claim["prohibited_language"] = _as_list(claim["prohibited_language"])
    if claim["required_controls"] is None:
        claim["required_controls"] = []
    else:
        claim["required_controls"] = _as_list(claim["required_controls"])
    return claim


def _schema_violations(claim: Mapping[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if is_missing_text(claim.get("claim_id")):
        violations.append(_v("SCHEMA_INVALID", "claim_id is required"))
    if not isinstance(claim.get("text"), str) or claim.get("text") == "":
        violations.append(_v("SCHEMA_INVALID", "text must be a non-empty string"))
    category = claim.get("claim_category")
    if category not in CLAIM_CATEGORIES:
        violations.append(_v("SCHEMA_INVALID", f"claim_category must be one of {list(CLAIM_CATEGORIES)}"))
    evidence = claim.get("evidence_class")
    if evidence not in CLAIM_CATEGORIES:
        violations.append(_v("SCHEMA_INVALID", f"evidence_class must be one of {list(CLAIM_CATEGORIES)}"))
    status = claim.get("empirical_synthetic_status")
    if status not in EMPIRICAL_SYNTHETIC_STATUSES:
        violations.append(_v("SCHEMA_INVALID", f"empirical_synthetic_status must be one of {list(EMPIRICAL_SYNTHETIC_STATUSES)}"))
    proxy = claim.get("proxy_formal_status")
    if proxy not in PROXY_FORMAL_STATUSES:
        violations.append(_v("SCHEMA_INVALID", f"proxy_formal_status must be one of {list(PROXY_FORMAL_STATUSES)}"))
    reviewer = claim.get("reviewer_state")
    if reviewer not in REVIEWER_STATES:
        violations.append(_v("SCHEMA_INVALID", f"reviewer_state must be one of {list(REVIEWER_STATES)}"))
    return violations


def _v(code: str, detail: str, *, phrases: list[str] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "rule": _RULE_CODES.get(code, code), "detail": detail}
    if phrases:
        item["phrases"] = list(phrases)
    return item


def _recommend_category(claim: Mapping[str, Any], codes: Iterable[str]) -> str | None:
    codeset = set(codes)
    current = claim.get("claim_category")
    if "R1_SYNTHETIC_NOT_BIOLOGY" in codeset:
        return "synthetic_demonstration"
    if "R2_PROXY_K_NOT_FORMAL" in codeset:
        return "proxy_inference"
    if "R3_BETA1_NOT_CONSCIOUSNESS" in codeset:
        return "unsupported_claim"
    if "R4_GRAPH_BETA1_NOT_SPATIAL" in codeset:
        return "proxy_inference" if current in PROMOTABLE_CATEGORIES else "unsupported_claim"
    if "R5_EP_NOT_BIO_TRANSITION" in codeset:
        return "hypothesis"
    if "R6_SIM_NOT_BIO_QUANTUM" in codeset:
        return "synthetic_demonstration"
    if "R7_MISSING_PROVENANCE" in codeset:
        if claim.get("empirical_synthetic_status") == "synthetic":
            return "synthetic_demonstration"
        return "speculation"
    if "R8_NO_FALSIFIER" in codeset:
        return "speculation"
    if "LANGUAGE_PROHIBITED" in codeset or "R9_UNCERTAINTY_ERASED" in codeset:
        return "unsupported_claim"
    return None
