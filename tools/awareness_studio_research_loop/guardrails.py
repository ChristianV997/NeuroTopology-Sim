"""Vocabularies, normalizers, and language guardrails shared by every
stage of the research-cycle orchestrator.

Enum vocabularies for literature-evidence fields (``claim_status``,
``evidence_tier``, ``verification_status``, ``source_status``) are
deliberately identical to the real ones defined in
``tools/awareness_studio_research/models.py`` (owned by Claude A, not
imported here) so this orchestrator speaks the same language as the
system it consumes without depending on it.

Every normalizer degrades to an explicit "unknown"/null value on anything
unrecognized -- nothing is ever inferred from context.
"""
from __future__ import annotations

import math
import re
from typing import Any

# --- Vocabularies matching tools/awareness_studio_research/models.py ------

CLAIM_STATUSES = {"empirical", "theoretical", "proxy", "speculative", "unsupported"}
EVIDENCE_TIERS = {"T1_verified_primary", "T2_verified_secondary", "T3_unverified_claimed", "T4_disputed"}
VERIFICATION_STATUSES = {"verified", "unverified", "disputed"}
SOURCE_STATUSES = {"active", "superseded", "disputed", "retracted"}
CLAIM_CLASSES = {"correlational", "causal", "theoretical", "methodological", "descriptive"}
LINK_RELATIONSHIPS = {"supports", "contradicts", "refines", "extends", "unrelated"}
EVIDENCE_UPDATE_TYPES = {"created", "downgraded", "superseded", "disputed", "amended"}

# --- Vocabularies specific to this orchestrator ----------------------------

DATA_MODE = {"synthetic", "proxy", "empirical", "unknown"}

#: The unified evidence-strength classification used in the artifact
#: ledger and the paper draft. Only "formal" may ever be described as a
#: rigorous statistical result; everything else is explicitly weaker.
EVIDENCE_CLASS = {"synthetic", "proxy", "empirical", "formal", "theoretical", "speculative", "unsupported", "unknown"}

NULL_VERDICTS = {"PASS", "FAIL", "INCONCLUSIVE", "TIMEOUT", "unknown"}

EXECUTION_STATUSES = {"completed", "failed", "running", "not_started", "unknown"}

DEPENDENCY_STATES = {"satisfied", "missing", "blocked", "unknown"}

REVIEW_DECISIONS = {"approved", "rejected", "pending", "not_required"}

#: The 14 cycle states this orchestrator computes deterministically per
#: hypothesis. Never stored/asserted by an upstream input -- always
#: derived here from the gate results below.
CYCLE_STATES = (
    "LITERATURE_READY",
    "HYPOTHESIS_READY",
    "EXPERIMENT_READY",
    "EXECUTION_PENDING",
    "EXECUTED",
    "VALIDATION_PENDING",
    "EVIDENCE_UPDATE_READY",
    "THEORY_REVISION_REQUIRED",
    "PAPER_DRAFT_READY",
    "BLOCKED_BY_PROVENANCE",
    "BLOCKED_BY_DATA",
    "BLOCKED_BY_DEPENDENCY",
    "HUMAN_REVIEW_REQUIRED",
    "INCONCLUSIVE",
)

_NON_FINITE_STRINGS = {"nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"}


def _normalize_enum(value: Any, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def safe_number(value: Any) -> float | None:
    """Finite float, or None. Rejects NaN/Infinity in any spelling,
    including numeric strings and silent-overflow literals like 1e400."""
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
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def normalize_claim_status(value: Any) -> str:
    return _normalize_enum(value, CLAIM_STATUSES, "unsupported")


def normalize_evidence_tier(value: Any) -> str:
    return _normalize_enum(value, EVIDENCE_TIERS, "T3_unverified_claimed")


def normalize_verification_status(value: Any) -> str:
    return _normalize_enum(value, VERIFICATION_STATUSES, "unverified")


def normalize_source_status(value: Any) -> str:
    return _normalize_enum(value, SOURCE_STATUSES, "active")


def normalize_claim_class(value: Any) -> str:
    return _normalize_enum(value, CLAIM_CLASSES, "descriptive")


def normalize_relationship(value: Any) -> str:
    return _normalize_enum(value, LINK_RELATIONSHIPS, "unrelated")


def normalize_evidence_update_type(value: Any) -> str:
    return _normalize_enum(value, EVIDENCE_UPDATE_TYPES, "created")


def normalize_data_mode(value: Any) -> str:
    return _normalize_enum(value, DATA_MODE, "unknown")


def normalize_null_verdict(value: Any) -> str:
    return _normalize_enum(value, NULL_VERDICTS, "unknown")


def normalize_execution_status(value: Any) -> str:
    return _normalize_enum(value, EXECUTION_STATUSES, "unknown")


def normalize_dependency_state(value: Any) -> str:
    return _normalize_enum(value, DEPENDENCY_STATES, "unknown")


def normalize_review_decision(value: Any) -> str:
    return _normalize_enum(value, REVIEW_DECISIONS, "pending")


def evidence_class_for_claim(claim_status: str) -> str:
    """A literature claim's own claim_status IS its evidence class -- both
    vocabularies were designed to line up 1:1."""
    return claim_status if claim_status in EVIDENCE_CLASS else "unknown"


def evidence_class_for_execution(*, data_mode: str, is_formal: bool) -> str:
    """Rule: a synthetic result remains synthetic, and only a formal
    statistical test (a completed null/surrogate test on a preregistered,
    held-out-locked, empirical experiment) is ever called "formal"."""
    if data_mode == "synthetic":
        return "synthetic"
    if data_mode == "proxy":
        return "proxy"
    if data_mode == "empirical":
        return "formal" if is_formal else "empirical"
    return "unknown"


# --- Forbidden-language policy (requirement 7) -----------------------------

#: Exact phrases (case-insensitive) that must never appear describing a
#: result unless the specific claim/hypothesis carries both formal
#: evidence (evidence_class == "formal") and an "approved" human-review
#: decision. Includes both the example phrasings given and their
#: present-tense variants.
FORBIDDEN_STRONG_CLAIM_PHRASES: tuple[str, ...] = (
    "proved consciousness",
    "proves consciousness",
    "confirmed liberation",
    "confirms liberation",
    "demonstrated quantum coherence",
    "demonstrates quantum coherence",
)

_CAUSAL_WORD_PATTERN = re.compile(r"\bcaus(?:e|ed|es|ing|ation|al)\b", re.IGNORECASE)


def find_forbidden_phrases(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    return sorted({phrase for phrase in FORBIDDEN_STRONG_CLAIM_PHRASES if phrase in lowered})


def contains_causal_language(text: str) -> bool:
    return bool(text) and _CAUSAL_WORD_PATTERN.search(text) is not None
