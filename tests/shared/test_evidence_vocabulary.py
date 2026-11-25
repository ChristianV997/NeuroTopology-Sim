"""The shared evidence vocabulary must reproduce both gates' historical taxonomies exactly."""
import pytest

from shared.evidence_vocabulary import (
    EVIDENCE_CLASSES, LEGACY_ALIASES, PROMOTABLE_TO_DESCRIPTIVE_REVIEW, normalize_evidence_class,
)
from tools.evidence_promotion_gate.schema import ALLOWED_EVIDENCE_CLASSES
from tools.research_claim_gate.gate import CLAIM_CLASSES

HISTORICAL_CLAIM = ("engineering_fact", "benchmark_result", "synthetic_demonstration", "descriptive_empirical",
                    "proxy_inference", "formal_statistical_evidence", "hypothesis", "speculation", "unsupported_claim")


def test_gates_bind_the_shared_taxonomy_unchanged():
    assert CLAIM_CLASSES == EVIDENCE_CLASSES == HISTORICAL_CLAIM
    assert ALLOWED_EVIDENCE_CLASSES == PROMOTABLE_TO_DESCRIPTIVE_REVIEW
    assert ALLOWED_EVIDENCE_CLASSES == tuple(c for c in HISTORICAL_CLAIM if c != "formal_statistical_evidence")
    assert "empirical" not in ALLOWED_EVIDENCE_CLASSES


@pytest.mark.parametrize("alias,canonical", sorted(LEGACY_ALIASES.items()))
def test_aliases_map_to_canonical(alias, canonical):
    assert canonical in EVIDENCE_CLASSES
    assert normalize_evidence_class(alias) == canonical
    assert normalize_evidence_class(alias.upper() + " ") == canonical


@pytest.mark.parametrize("value", ["EMPIRICAL", "validated", "", None, 3, "confirmed"])
def test_unknown_input_fails_closed(value):
    assert normalize_evidence_class(value) == "unsupported_claim"


def test_aliases_never_upgrade_to_formal_evidence_except_the_explicit_formal_spelling():
    upgraded = [a for a, c in LEGACY_ALIASES.items() if c == "formal_statistical_evidence"]
    assert upgraded == ["formal"]
