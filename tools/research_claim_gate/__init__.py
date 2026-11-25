"""Deterministic scientific-claim admissibility gate.

This package evaluates claim metadata and language supplied by callers.  It
does not fetch data, run an LLM, compute statistics, or promote a claim to
scientific confirmation.
"""

from .gate import (
    CLAIM_CLASSES,
    DECISION_STATES,
    REASON_CODES,
    ClaimRecord,
    ClaimGateResult,
    ProvenanceRecord,
    evaluate_claim,
    evaluate_claim_batch,
    serialize_json,
    validate_provenance,
)

__all__ = [
    "CLAIM_CLASSES",
    "DECISION_STATES",
    "REASON_CODES",
    "ClaimRecord",
    "ClaimGateResult",
    "ProvenanceRecord",
    "evaluate_claim",
    "evaluate_claim_batch",
    "serialize_json",
    "validate_provenance",
]
