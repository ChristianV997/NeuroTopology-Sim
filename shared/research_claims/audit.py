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
    "R5_EP_NOT_BIO_TRANSITION": "A fitted exceptional point cannot be called a biological phase transition without empirical validation.",
    "R6_SIM_NOT_BIO_QUANTUM": "A decoherence simulation cannot be called evidence of biological quantum coherence without independently validated inputs.",
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
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def normalize_claim(raw: Mapping[str, Any]) -> dict[str, Any]:
    incoming = {normalize_field_name(str(key)): value for key, value in raw.items()}
    claim = {field: incoming.get(field, None) for field in CLAIM_RECORD_FIELDS}
    claim["allowed_language"] = _as_list(claim["allowed_language"])
    claim["prohibited_language"] = _as_list(claim["prohibited_language"])
    claim["required_controls"] = _as_list(claim["required_controls"])
    return claim


def _v(code: str, detail: str, *, phrases: list[str] | None = None) -> dict[str, Any]:
    item = {"code": code, "rule": _RULE_CODES.get(code, code), "detail": detail}
    if phrases:
        item["phrases"] = list(phrases)
    return item


def _schema_violations(claim: Mapping[str, Any]) -> list[dict[str, Any]]:
    violations = []
    if is_missing_text(claim.get("claim_id")):
        violations.append(_v("SCHEMA_INVALID", "claim_id is required"))
    if not isinstance(claim.get("text"), str) or claim.get("text") == "":
        violations.append(_v("SCHEMA_INVALID", "text must be a non-empty string"))
    if claim.get("claim_category") not in CLAIM_CATEGORIES:
        violations.append(_v("SCHEMA_INVALID", f"claim_category must be one of {list(CLAIM_CATEGORIES)}"))
    if claim.get("evidence_class") not in CLAIM_CATEGORIES:
        violations.append(_v("SCHEMA_INVALID", f"evidence_class must be one of {list(CLAIM_CATEGORIES)}"))
    if claim.get("empirical_synthetic_status") not in EMPIRICAL_SYNTHETIC_STATUSES:
        violations.append(_v("SCHEMA_INVALID", f"empirical_synthetic_status must be one of {list(EMPIRICAL_SYNTHETIC_STATUSES)}"))
    if claim.get("proxy_formal_status") not in PROXY_FORMAL_STATUSES:
        violations.append(_v("SCHEMA_INVALID", f"proxy_formal_status must be one of {list(PROXY_FORMAL_STATUSES)}"))
    if claim.get("reviewer_state") not in REVIEWER_STATES:
        violations.append(_v("SCHEMA_INVALID", f"reviewer_state must be one of {list(REVIEWER_STATES)}"))
    return violations


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
        return "synthetic_demonstration" if claim.get("empirical_synthetic_status") == "synthetic" else "speculation"
    if "R8_NO_FALSIFIER" in codeset:
        return "speculation"
    if "LANGUAGE_PROHIBITED" in codeset or "R9_UNCERTAINTY_ERASED" in codeset:
        return "unsupported_claim"
    return None


def audit_one(raw: Mapping[str, Any]) -> dict[str, Any]:
    claim = normalize_claim(raw)
    violations = _schema_violations(claim)
    scans = rules.scan_text(claim.get("text") if isinstance(claim.get("text"), str) else "")
    text = claim.get("text") if isinstance(claim.get("text"), str) else ""
    category = claim.get("claim_category")
    evidence = claim.get("evidence_class")
    emp = claim.get("empirical_synthetic_status")
    proxy = claim.get("proxy_formal_status")

    if emp == "synthetic" and category in {"empirical_observation", "formal_statistical_evidence"}:
        violations.append(_v("R1_SYNTHETIC_NOT_BIOLOGY", "synthetic data cannot be classified as empirical or formal biological evidence"))
    if emp == "synthetic" and scans["synthetic_biology"]:
        violations.append(_v("R1_SYNTHETIC_NOT_BIOLOGY", "synthetic output used to assert biological confirmation", phrases=scans["synthetic_biology"]))

    proxy_language = scans["proxy_as_formal"]
    if proxy == "proxy" and (category == "formal_statistical_evidence" or evidence == "formal_statistical_evidence" or proxy_language):
        violations.append(_v("R2_PROXY_K_NOT_FORMAL", "proxy K / information-criterion ratio declared or worded as formal evidence", phrases=proxy_language))
    if rules.mentions_proxy_k(text) and (category == "formal_statistical_evidence" or rules._contains_any(text.lower(), ("formal bayes", "formal k"))):
        violations.append(_v("R2_PROXY_K_NOT_FORMAL", "proxy-K language combined with a formal-evidence classification"))

    if rules.mentions_beta1(text) and scans["beta1_consciousness"]:
        violations.append(_v("R3_BETA1_NOT_CONSCIOUSNESS", "numerical beta-1 used as proof of consciousness", phrases=scans["beta1_consciousness"]))
    if scans["beta1_consciousness"] and category in PROMOTABLE_CATEGORIES:
        violations.append(_v("R3_BETA1_NOT_CONSCIOUSNESS", "consciousness-proof language under a promoted evidence class", phrases=scans["beta1_consciousness"]))

    if rules.mentions_graph_beta1(text) and scans["graph_as_spatial"]:
        violations.append(_v("R4_GRAPH_BETA1_NOT_SPATIAL", "graph beta-1 conflated with spatial topological charge", phrases=scans["graph_as_spatial"]))

    if rules.mentions_exceptional_point(text) and scans["ep_as_biological_transition"]:
        if emp != "empirical" or is_missing_text(claim.get("provenance_reference")):
            violations.append(_v("R5_EP_NOT_BIO_TRANSITION", "fitted EP described as a biological phase transition without empirical validation", phrases=scans["ep_as_biological_transition"]))

    if rules.mentions_decoherence_simulation(text) and scans["decoherence_as_bio_quantum"]:
        violations.append(_v("R6_SIM_NOT_BIO_QUANTUM", "decoherence simulation described as biological quantum coherence", phrases=scans["decoherence_as_bio_quantum"]))
    if emp == "synthetic" and scans["decoherence_as_bio_quantum"]:
        violations.append(_v("R6_SIM_NOT_BIO_QUANTUM", "synthetic input used to assert biological quantum coherence", phrases=scans["decoherence_as_bio_quantum"]))

    missing_prov = is_missing_text(claim.get("provenance_reference"))
    missing_origin = is_missing_text(claim.get("data_origin"))
    if (missing_prov or missing_origin) and category in CATEGORIES_REQUIRING_PROVENANCE:
        violations.append(_v("R7_MISSING_PROVENANCE", "promoted claim is missing provenance_reference or data_origin"))

    if category not in CATEGORIES_EXEMPT_FROM_FALSIFIABILITY and is_missing_text(claim.get("falsifiability_condition")):
        violations.append(_v("R8_NO_FALSIFIER", "no falsifiability condition declared; label speculation or add a falsifier"))

    if scans["certainty_erasure"]:
        violations.append(_v("R9_UNCERTAINTY_ERASED", "language erases uncertainty or limitations", phrases=scans["certainty_erasure"]))
    if category in PROMOTABLE_CATEGORIES and scans["global_prohibited"]:
        violations.append(_v("R9_UNCERTAINTY_ERASED", "promoted claim uses globally prohibited certainty language", phrases=scans["global_prohibited"]))

    declared_hits = rules._contains_any(text.lower(), [phrase.lower() for phrase in (claim.get("prohibited_language") or [])])
    if declared_hits:
        violations.append(_v("LANGUAGE_PROHIBITED", "claim text contains a phrase listed in its own prohibited_language", phrases=declared_hits))
    if scans["global_prohibited"] and category not in {"historical_context", "unsupported_claim", "speculation"}:
        violations.append(_v("LANGUAGE_PROHIBITED", "claim text contains globally prohibited promotional language", phrases=scans["global_prohibited"]))

    if category == "formal_statistical_evidence" and proxy != "formal":
        violations.append(_v("CATEGORY_EVIDENCE_MISMATCH", "formal_statistical_evidence requires proxy_formal_status=formal"))
    if category == "empirical_observation" and emp == "synthetic":
        violations.append(_v("CATEGORY_EVIDENCE_MISMATCH", "empirical_observation cannot have empirical_synthetic_status=synthetic"))
    if category == "synthetic_demonstration" and emp == "empirical":
        violations.append(_v("CATEGORY_EVIDENCE_MISMATCH", "synthetic_demonstration cannot have empirical_synthetic_status=empirical"))

    codes = [item["code"] for item in violations]
    recommended = _recommend_category(claim, codes)
    scientific_codes = {
        "R1_SYNTHETIC_NOT_BIOLOGY", "R2_PROXY_K_NOT_FORMAL", "R3_BETA1_NOT_CONSCIOUSNESS",
        "R4_GRAPH_BETA1_NOT_SPATIAL", "R5_EP_NOT_BIO_TRANSITION", "R6_SIM_NOT_BIO_QUANTUM",
        "R7_MISSING_PROVENANCE", "R8_NO_FALSIFIER", "R9_UNCERTAINTY_ERASED",
        "LANGUAGE_PROHIBITED", "CATEGORY_EVIDENCE_MISMATCH", "SCHEMA_INVALID",
    }
    has_fail = any(code in scientific_codes for code in codes)
    if not has_fail:
        verdict, recommended_action = VERDICT_PASS, "accept"
    elif recommended and recommended != category:
        verdict, recommended_action = VERDICT_DOWNGRADED, f"downgrade_to:{recommended}"
    else:
        verdict, recommended_action = VERDICT_FAIL, "reject"

    return {
        "claim_id": claim.get("claim_id"),
        "verdict": verdict,
        "recommended_action": recommended_action,
        "recommended_category": recommended,
        "original_claim": {field: claim.get(field) for field in CLAIM_RECORD_FIELDS},
        "original_text": text if isinstance(claim.get("text"), str) else None,
        "text_rewritten": False,
        "results_rewritten": False,
        "violations": violations,
        "language_scan": {key: value for key, value in scans.items() if value},
    }


def _extract_claims(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        if "claims" in payload and isinstance(payload["claims"], list):
            return payload["claims"]
        if "records" in payload and isinstance(payload["records"], list):
            return payload["records"]
        raise ValueError("input object must contain a 'claims' or 'records' array")
    raise ValueError("input must be a JSON array or an object with a claims array")


def audit_claims(claims: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    audits = []
    for index, raw in enumerate(claims):
        if not isinstance(raw, Mapping):
            audits.append({
                "claim_id": None, "verdict": VERDICT_FAIL, "recommended_action": "reject",
                "recommended_category": None, "original_claim": None, "original_text": None,
                "text_rewritten": False, "results_rewritten": False,
                "violations": [_v("SCHEMA_INVALID", f"claims[{index}] is not an object")],
                "language_scan": {},
            })
            continue
        audits.append(audit_one(raw))
    counts = {
        "pass": sum(1 for item in audits if item["verdict"] == VERDICT_PASS),
        "fail": sum(1 for item in audits if item["verdict"] == VERDICT_FAIL),
        "downgraded": sum(1 for item in audits if item["verdict"] == VERDICT_DOWNGRADED),
        "total": len(audits),
    }
    return {
        "ok": counts["fail"] == 0 and counts["downgraded"] == 0,
        "schema": SCHEMA_ID,
        "auditor": AUDITOR_ID,
        "version": AUDITOR_VERSION,
        "counts": counts,
        "claims_rejected": [item["claim_id"] for item in audits if item["verdict"] == VERDICT_FAIL],
        "claims_downgraded": [item["claim_id"] for item in audits if item["verdict"] == VERDICT_DOWNGRADED],
        "audits": audits,
        "limitations": [
            "This auditor classifies language and metadata only.",
            "It does not compute Bayes factors, topology, or empirical statistics.",
            "A PASS means the claim record is internally consistent, not that biology is confirmed.",
            "Synthetic, proxy, and historical claims cannot be promoted to formal evidence here.",
            "The auditor never rewrites claim text or scientific numeric results.",
        ],
        "text_rewritten": False,
        "results_rewritten": False,
    }


def audit_claims_payload(payload: Any) -> dict[str, Any]:
    assert_finite_or_null(payload, path="$.input")
    report = audit_claims(_extract_claims(payload))
    assert_finite_or_null(report, path="$.audit")
    return report


def load_and_audit(raw_text: str) -> dict[str, Any]:
    import json
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    try:
        return audit_claims_payload(payload)
    except NonFiniteJsonError as exc:
        raise ValueError(str(exc)) from exc
