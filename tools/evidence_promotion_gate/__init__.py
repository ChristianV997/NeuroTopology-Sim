"""Fail-closed, offline evidence promotion gate.

This package consumes local RunRecords, claim-gate results, RAG Markdown,
command-center JSON, Airtable-shaped cards, and literature records. It
decides whether a record may be *reported* under a non-empirical class.
It does not compute statistics, contact a network, or confirm science.

Call ``evaluate_claim`` from ``tools.research_claim_gate`` rather than
reimplementing claim-language rules.
"""

from __future__ import annotations

from tools.evidence_promotion_gate.evaluator import evaluate_case, evaluate_path
from tools.evidence_promotion_gate.reporting import serialize_json
from tools.evidence_promotion_gate.schema import (
    ALLOWED_EVIDENCE_CLASSES,
    PROMOTION_DECISIONS,
    REASON_CODES,
    SCHEMA_VERSION,
    PromotionResult,
)

__all__ = [
    "ALLOWED_EVIDENCE_CLASSES",
    "PROMOTION_DECISIONS",
    "REASON_CODES",
    "SCHEMA_VERSION",
    "PromotionResult",
    "evaluate_case",
    "evaluate_path",
    "serialize_json",
]
