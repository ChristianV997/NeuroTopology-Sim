"""Status-labeling guardrails shared by every report section.

Enum vocabularies below are deliberately aligned with the ones already
established in ``configs/release/evidence_schema.yaml`` (the Release
compiler's own evidence-bundle contract) so this mobile-focused compiler
speaks the same language as the rest of the repo's evidence tooling,
without importing or depending on it. Where this tool needs a distinction
``evidence_schema.yaml`` does not define (CI timeouts, the graph-beta-1
vs. spatial-charge topology split, checksum provenance), a clearly
documented tool-specific vocabulary is added instead of overloading an
existing one.

Every normalizer here is defensive: an unrecognized or absent input
degrades to an explicit "unknown"-shaped value rather than a guessed one.
"""
from __future__ import annotations

import math
from typing import Any

# --- Vocabularies shared with configs/release/evidence_schema.yaml --------

MERGE_STATUS = {"merged", "open", "draft", "branch_only", "blocked", "unverified", "closed", "unknown"}
STATUS_CATEGORY = {
    "VERIFIED_MERGED", "OPEN_REVIEW", "DRAFT_REVIEW", "BRANCH_ONLY", "CI_BLOCKED",
    "BILLING_BLOCKED", "SUPERSEDED", "DUPLICATE", "SCIENTIFIC_REVIEW_REQUIRED", "UNVERIFIED",
}
CLAIM_CLASS = {"none", "synthetic", "proxy", "unsupported", "empirical", "unavailable"}
DATA_MODE = {"none", "synthetic", "proxy", "empirical", "local-unknown", "unknown"}
VALUE_CLASS = {"scientific", "engineering", "governance", "tooling", "performance", "interoperability"}
VERIFICATION_EXISTENCE = {"verified", "missing", "unverified", "unknown"}
VERIFICATION_MERGE_STATUS = {"verified", "unverified", "not_applicable", "unknown"}
SCIENTIFIC_PASS = {"not_claimed", "claimed", "pass", "fail", "unsupported", "inconclusive"}
AUTHOR_TEST_RESULTS = {"unverified", "verified", "verified_pass", "missing", "not_applicable", "claimed_unverified"}
IMPLEMENTATION_REPORT = {"not_located", "missing", "present", "unverified"}
MEMORY_KIND = {"rss", "RSS", "tracemalloc", "unavailable"}
#: Distinguishes why something is blocked -- an infrastructure/billing block
#: is not a scientific failure, and must never be reported as one (or vice
#: versa). Not in evidence_schema.yaml as its own enum, but directly
#: implements its "status_category is not merge_status" / billing-not-pass
#: spirit for CI jobs and merge-gate decisions.
BLOCK_REASON = {"infrastructure", "billing", "scientific"}
RELEASE_RECOMMENDATION = {
    "READY_FOR_REVIEW", "BLOCKED_BY_CI", "BLOCKED_BY_MISSING_BRANCHES",
    "BLOCKED_BY_SCIENTIFIC_VALIDATION", "READY_FOR_MERGE_REVIEW",
}
#: Not in evidence_schema.yaml -- an explicit extension for this tool's
#: "support partial reports" requirement, since none of the five canonical
#: recommendations mean "we don't have enough evidence to recommend
#: anything." Kept visually distinct (no ready/blocked framing).
INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"

# --- Vocabularies specific to this tool ------------------------------------

#: Distinguishes a job that failed from one CI never started for it, and
#: from one that started but exceeded its time budget (a third, distinct
#: outcome -- neither "failed" in the sense of an assertion, nor simply
#: "not_started").
CI_STATUS = {"passed", "failed", "pending", "not_started", "timed_out", "skipped"}

#: NeuroTopology-Sim's two topology metric families are not interchangeable
#: evidence for the same claim: graph_beta_1 (first Betti number / cycle
#: rank from the fMRI-TDA graph pipeline, contracts/fmri_tda/**) measures
#: connectivity-graph topology, while spatial_charge (Qz/Qabs/plaquette
#: charge, core/topology.py) measures the sim engine's field topology. A
#: PASS on one is never evidence for the other.
METRIC_FAMILY = {"graph_beta_1", "spatial_charge", "other"}
_UNCLASSIFIED_METRIC_FAMILY = "unclassified"

#: A checksum this compiler (or an evidence producer) computed from local
#: bytes proves reproducible integrity of what was read -- it does not
#: prove the content was independently verified against a second source
#: (e.g. the GitHub API). Only "independent" may be described that way.
CHECKSUM_SOURCE = {"local", "independent"}

_NON_FINITE_STRINGS = {"nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"}


def _normalize_enum(value: Any, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def safe_number(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None``.

    Accepts numeric-looking strings (CSV rows are all strings) as well as
    native int/float. Rejects NaN/Infinity regardless of how they were
    spelled, including values that overflow to +/-inf (e.g. ``1e400``) and
    string literals like ``"nan"``/``"Infinity"``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in _NON_FINITE_STRINGS:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def safe_int(value: Any) -> int | None:
    number = safe_number(value)
    return int(number) if number is not None else None


def safe_bool(value: Any) -> bool | None:
    """Coerce a bool, or a CSV-style ``"true"``/``"false"`` string, to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def normalize_merge_status(value: Any) -> str:
    """Pass through only an explicitly-declared merge_status literal.

    A branch existing, a PR being present, or any other side information
    must never upgrade a PR's status to "merged" -- only a literal
    ``merge_status: "merged"`` in the source record does that. Note in
    particular that "branch_only" (present in an integration branch but
    not merged to the default branch) and "merged" are different values;
    an integration-only PR must never be reported as merged.
    """
    return _normalize_enum(value, MERGE_STATUS, "unknown")


def normalize_status_category(value: Any) -> str:
    """Pass through only an explicitly-declared status_category literal.

    Per evidence_schema.yaml's own hard rule, a status_category is not a
    merge_status: ``OPEN_REVIEW``/``DRAFT_REVIEW`` must never be read as
    "merged", and this function never invents one from other fields.
    """
    if isinstance(value, str) and value in STATUS_CATEGORY:
        return value
    return "NOT_CLASSIFIED"


def normalize_claim_class(value: Any) -> str:
    """Pass through only an explicitly-declared claim_class literal.

    This is the "proxy evidence versus formal evidence" (and
    synthetic-versus-empirical) axis: only ``"empirical"`` may ever be
    described as formal/empirical evidence; ``"proxy"``, ``"synthetic"``,
    ``"unsupported"``, and ``"unavailable"`` are all explicitly weaker.
    """
    return _normalize_enum(value, CLAIM_CLASS, "unknown")


def normalize_data_mode(value: Any) -> str:
    """Pass through only an explicitly-declared data_mode literal (never guessed)."""
    return _normalize_enum(value, DATA_MODE, "unknown")


def normalize_ci_status(value: Any) -> str:
    """Pass through only an explicitly-declared CI status; never infer passing
    from a job that has not started or timed out."""
    return _normalize_enum(value, CI_STATUS, "unknown")


def normalize_metric_family(value: Any) -> str:
    """Pass through only graph_beta_1/spatial_charge/other; anything else is
    "unclassified" so it is never silently folded into either family's tally."""
    if isinstance(value, str) and value in METRIC_FAMILY:
        return value
    return _UNCLASSIFIED_METRIC_FAMILY


def normalize_checksum_source(value: Any) -> str:
    return _normalize_enum(value, CHECKSUM_SOURCE, "unknown")


def normalize_value_class(value: Any) -> str:
    return _normalize_enum(value, VALUE_CLASS, "unknown")


def normalize_verification_existence(value: Any) -> str:
    return _normalize_enum(value, VERIFICATION_EXISTENCE, "unknown")


def normalize_verification_merge_status(value: Any) -> str:
    return _normalize_enum(value, VERIFICATION_MERGE_STATUS, "unknown")


def normalize_scientific_pass(value: Any) -> str:
    return _normalize_enum(value, SCIENTIFIC_PASS, "not_claimed")


def normalize_author_test_results(value: Any) -> str:
    return _normalize_enum(value, AUTHOR_TEST_RESULTS, "unverified")


def normalize_implementation_report(value: Any) -> str:
    return _normalize_enum(value, IMPLEMENTATION_REPORT, "not_located")


def normalize_block_reason(value: Any) -> str | None:
    return value if isinstance(value, str) and value in BLOCK_REASON else None


def normalize_memory_kind(value: Any) -> str:
    if isinstance(value, str) and value in MEMORY_KIND:
        return "rss" if value == "RSS" else value
    return "unavailable"


def metric_label(metric_type: Any) -> dict[str, Any]:
    """Only ``metric_type == "bayes_factor"`` is ever displayed as a Bayes factor."""
    declared = metric_type if isinstance(metric_type, str) and metric_type.strip() else "unspecified_metric"
    is_formal_bayes_factor = declared == "bayes_factor"
    display = "Bayes factor" if is_formal_bayes_factor else f"{declared} (not a formal Bayes factor)"
    return {"metric_type": declared, "is_formal_bayes_factor": is_formal_bayes_factor, "metric_display_label": display}


def evidence_strength_label(claim_class: str) -> str:
    """Human label for the proxy-vs-formal-evidence axis, keyed on claim_class."""
    return {
        "empirical": "formal empirical evidence",
        "proxy": "proxy evidence (not formal)",
        "synthetic": "synthetic evidence (not formal, not empirical)",
        "unsupported": "unsupported claim",
        "unavailable": "no evidence available",
        "none": "no claim made",
        "unknown": "evidence class unknown",
    }[claim_class if claim_class in CLAIM_CLASS else "unknown"]


def checksum_source_label(checksum_source: str) -> str:
    return {
        "local": "local checksum only (not independently verified)",
        "independent": "independently verified",
        "unknown": "verification status unknown",
    }[checksum_source if checksum_source in CHECKSUM_SOURCE else "unknown"]
