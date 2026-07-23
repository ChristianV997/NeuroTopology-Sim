from __future__ import annotations

import pytest

from sciencer_d.ontology.firewall import (
    assert_allowed,
    load_forbidden_claims,
    normalize_claim_text,
    scan_text,
)


@pytest.mark.parametrize("phrase", load_forbidden_claims())
def test_firewall_rejects_every_seeded_forbidden_claim(phrase):
    result = scan_text(phrase)
    assert result.allowed is False
    assert result.violations


def test_firewall_normalizes_diacritics_and_punctuation():
    assert normalize_claim_text("Nibbāna") == "nibbana"
    assert scan_text("RG fixed-point is NIBBANA!").allowed is False


def test_firewall_allows_bounded_bridge_language():
    text = "Field dynamics are a falsifiable bridge hypothesis with no ontology promotion."
    assert scan_text(text).allowed is True
    assert_allowed(text)


def test_firewall_matches_token_boundaries_instead_of_substrings():
    assert scan_text("The SQ is self-correcting.").allowed is True


def test_assert_allowed_raises_for_overclaim():
    with pytest.raises(ValueError, match="Forbidden ontology claim"):
        assert_allowed("consciousness ontology solved")
