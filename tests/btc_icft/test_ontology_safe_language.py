"""Tests for ontology safe-language firewall (O1)."""
from __future__ import annotations

from sciencer_d.btc_icft.ontology.safe_language import (
    ALLOWED_SAFE_PHRASES,
    FORBIDDEN_ONTOLOGY_PHRASES,
    find_forbidden_phrases,
    normalize_text,
    validate_json_safe_text,
    validate_safe_text,
)


def test_banned_phrases_detected_case_insensitively():
    text = "This DOC says 'EEG Proves Consciousness' which is forbidden."
    hits = validate_safe_text(text)
    assert any("eeg proves consciousness" in h for h in hits)


def test_all_forbidden_phrases_in_table():
    for phrase in FORBIDDEN_ONTOLOGY_PHRASES:
        hits = find_forbidden_phrases(f"... {phrase} ...")
        assert phrase in hits


def test_safe_phrases_allowed():
    safe_text = " ".join(ALLOWED_SAFE_PHRASES)
    hits = validate_safe_text(safe_text)
    assert hits == []


def test_safe_generated_claim_passes():
    safe = (
        "Ontology evaluation constrains DS005620 benchmark outputs to "
        "explicit claim scopes and keeps substrate, theory, and ontology "
        "claims quarantined unless required independent evidence exists."
    )
    assert validate_safe_text(safe) == []


def test_nested_json_scan_finds_banned_phrase():
    obj = {
        "title": "fine",
        "nested": {
            "deeper": [
                "ok",
                {"problematic": "the device proves consciousness ultimately"},
            ]
        },
    }
    hits = validate_json_safe_text(obj)
    assert any("proves consciousness" in h for h in hits)


def test_normalize_collapses_whitespace_and_lowercases():
    assert normalize_text("  Hello\nWorld  ") == "hello world"
