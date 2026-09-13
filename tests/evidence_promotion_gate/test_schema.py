"""Closed vocabulary and serialization contracts."""

from __future__ import annotations

from tools.evidence_promotion_gate.schema import (
    ALLOWED_EVIDENCE_CLASSES,
    PROMOTION_DECISIONS,
    REASON_CODES,
    SCHEMA_VERSION,
)


def test_schema_version_and_closed_decisions():
    assert SCHEMA_VERSION == "EvidencePromotionGate.v1"
    assert PROMOTION_DECISIONS == (
        "HOLD_SYNTHETIC_ONLY",
        "HOLD_PROXY_ONLY",
        "HOLD_LITERATURE_HYPOTHESIS",
        "HOLD_INCOMPLETE_PROVENANCE",
        "HOLD_INCONCLUSIVE",
        "BLOCK_PROMOTION",
        "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW",
        "ADMISSIBLE_FOR_ENGINEERING_REPORT",
    )


def test_allowed_classes_never_include_empirical():
    lowered = {item.lower() for item in ALLOWED_EVIDENCE_CLASSES}
    assert "empirical" not in lowered
    assert "confirmed" not in lowered


def test_reason_codes_cover_fail_closed_rules():
    required = {
        "SYNTHETIC_NOT_EMPIRICAL",
        "PROXY_K_NOT_EMPIRICAL",
        "LITERATURE_HYPOTHESIS_NOT_EMPIRICAL",
        "UNKNOWN_N_TESTS",
        "DOWNSTREAM_UNSAFE_PASS",
        "DOWNSTREAM_UNSAFE_EMPIRICAL",
        "SCIENTIFIC_PASS_NOT_EMITTED",
        "K_EQUALS_100_NOT_PASS",
    }
    assert required <= set(REASON_CODES)
