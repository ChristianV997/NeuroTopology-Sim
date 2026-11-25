"""End-to-end fixture tests against the real, canonical
``tools/research_claim_gate/gate.py`` (read-only, not modified or
duplicated here). Every adversarial fixture must be rejected in some
form; the accepted-baseline fixture must not be, proving this suite
does not just reject everything indiscriminately.
"""
from __future__ import annotations

import pytest

from tools.research_claim_gate.gate import evaluate_claim

from .conftest import ADVERSARIAL_CASES, bucket_for_decision


@pytest.mark.parametrize("fixture_name,expected_decision,expected_reason_code", ADVERSARIAL_CASES, ids=[c[0] for c in ADVERSARIAL_CASES])
def test_adversarial_fixture_is_never_admissible(load_fixture, fixture_name, expected_decision, expected_reason_code):
    raw = load_fixture(fixture_name)
    result = evaluate_claim(raw)

    assert result.decision == expected_decision, f"{fixture_name}: expected {expected_decision}, got {result.decision} (codes={result.reason_codes})"
    assert result.decision != "CLAIM_ADMISSIBLE"
    assert expected_reason_code in result.reason_codes
    assert bucket_for_decision(result.decision) in {"BLOCKED", "INCOMPLETE", "DOWNGRADED", "REVIEW_REQUIRED"}


def test_accepted_baseline_is_admissible_proving_the_suite_is_not_indiscriminate(load_fixture):
    """A control case: a well-formed claim with complete provenance,
    verified labels, declared null controls, uncertainty, and effect
    size must be admitted -- if this fixture were also rejected, the
    conformance suite would be meaningless (rejecting everything is not
    the same as rejecting bad science)."""
    raw = load_fixture("accepted_baseline")
    result = evaluate_claim(raw)

    assert result.decision == "CLAIM_ADMISSIBLE"
    assert result.reason_codes == ()
    assert result.scientific_pass is False  # admissible is never a scientific PASS either


def test_every_adversarial_fixture_is_covered_by_a_case():
    """Guards against silently losing coverage if a fixture file is
    added without a corresponding case, or vice versa."""
    from pathlib import Path

    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    fixture_files = {p.stem for p in fixtures_dir.glob("*.json")}
    cased = {name for name, _, _ in ADVERSARIAL_CASES} | {"accepted_baseline"}
    assert fixture_files == cased
