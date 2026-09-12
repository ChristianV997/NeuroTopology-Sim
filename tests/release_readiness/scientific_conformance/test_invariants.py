"""Cross-cutting invariants required by this task, checked against every
fixture at once rather than one scenario at a time:

4. No fixture can produce scientific PASS or a formal Bayes factor.
5. Missing values remain null, never silently zero-filled.
6. Release-evidence decisions remain engineering review decisions, not
   scientific confirmation.
7. Fixtures (and the gate's own behavior on them) are deterministic,
   finite, local-only, and synthetic.
"""
from __future__ import annotations

import json

import pytest

from tools.research_claim_gate.gate import evaluate_claim, serialize_json

from .conftest import ADVERSARIAL_FIXTURE_NAMES

ALL_FIXTURE_NAMES = ADVERSARIAL_FIXTURE_NAMES + ("accepted_baseline",)


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_no_fixture_ever_produces_scientific_pass_or_a_formal_bayes_factor(load_fixture, fixture_name):
    result = evaluate_claim(load_fixture(fixture_name))
    assert result.scientific_pass is False
    assert result.formal_bayes_factor is None
    payload = result.to_dict()
    assert payload["scientific_pass"] is False
    assert payload["formal_bayes_factor"] is None


def test_injecting_a_fake_pass_or_bayes_factor_into_the_input_has_no_effect(load_fixture):
    """A caller cannot smuggle a fabricated result past the gate by
    simply adding the fields it would have produced itself -- the gate
    only ever reads its own declared input vocabulary."""
    raw = load_fixture("accepted_baseline")
    raw = dict(raw)
    raw["scientific_pass"] = True
    raw["formal_bayes_factor"] = 999.0
    raw["decision"] = "CLAIM_ADMISSIBLE"
    raw["scientific_eligibility"] = True

    result = evaluate_claim(raw)

    assert result.scientific_pass is False
    assert result.formal_bayes_factor is None


def test_unknown_number_of_tests_stays_null_not_defaulted_to_one(load_fixture):
    raw = dict(load_fixture("accepted_baseline"))
    raw["n_tests"] = None
    result = evaluate_claim(raw)
    # The gate's own reason message documents this invariant explicitly;
    # this test holds it to that documented behavior.
    assert "UNKNOWN_N_TESTS" in result.reason_codes
    reason = next(r for r in result.reasons if r.code == "UNKNOWN_N_TESTS")
    assert "not treated as one test" in reason.message


def test_malformed_input_leaves_identity_fields_null_not_zero_or_empty_string():
    result = evaluate_claim({"not": "a valid claim shape"})
    assert result.decision == "CLAIM_INCOMPLETE"
    payload = result.to_dict()
    assert payload["claim_class"] is None
    assert payload["evidence_class"] is None
    assert payload["data_mode"] is None
    # None of the "missing" identity fields were silently coerced to a
    # falsy-but-present value like "" or 0 -- each is exactly None.
    for key in ("claim_class", "evidence_class", "data_mode"):
        assert payload[key] is None


def test_missing_provenance_fields_stay_null_in_the_serialized_provenance_record(load_fixture):
    from tools.research_claim_gate.gate import ProvenanceRecord

    record = ProvenanceRecord.from_value(None)
    as_dict = record.to_dict()
    assert as_dict["checksum"] is None
    assert as_dict["source_id"] is None
    assert as_dict["subject_ids"] == []  # an empty *list* is correct here, not None -- the field is a collection


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_decision_is_never_reported_as_a_scientific_confirmation(load_fixture, fixture_name):
    """Requirement 6: release-evidence decisions remain engineering
    review decisions. The gate's own docstring states it "never emits...
    a scientific PASS inferred from metadata" -- this asserts that
    holds at the output level, not just in comments."""
    result = evaluate_claim(load_fixture(fixture_name))
    text = serialize_json(result)
    assert '"scientific_pass": false' in text
    assert '"formal_bayes_factor": null' in text
    payload = json.loads(text)
    assert payload["decision"] != "CLAIM_ADMISSIBLE" or fixture_name == "accepted_baseline"


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_fixtures_are_deterministic_across_repeated_evaluation(load_fixture, fixture_name):
    raw = load_fixture(fixture_name)
    result1 = evaluate_claim(raw)
    result2 = evaluate_claim(raw)
    assert serialize_json(result1) == serialize_json(result2)


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_fixtures_are_locally_loadable_and_are_pure_json_with_no_network_markers(load_fixture, fixture_name):
    raw = load_fixture(fixture_name)
    text = json.dumps(raw)
    assert "http://" not in text
    assert "https://" not in text
    assert "ftp://" not in text


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_serialized_gate_output_is_finite_json(load_fixture, fixture_name):
    result = evaluate_claim(load_fixture(fixture_name))
    text = serialize_json(result)
    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text) == result.to_dict()
