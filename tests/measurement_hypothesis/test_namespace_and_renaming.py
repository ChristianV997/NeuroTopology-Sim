"""Interpretation terms stay on the interpretation side, and existing features keep their code-derived names."""
from __future__ import annotations

import pytest


def _codes(report):
    return {error["code"] for error in report["errors"]}


def test_theory_term_leak_fixture_is_rejected(load_fixture, check):
    report = check(load_fixture("theory_term_leak"))
    assert report["contract_status"] == "REJECTED"
    assert {"THEORY_TERM_IN_OPERATIONAL_IDENTIFIER", "FEATURE_ID_NOT_DERIVED"} <= _codes(report)
    leaks = [error for error in report["errors"] if error["code"] == "THEORY_TERM_IN_OPERATIONAL_IDENTIFIER"]
    assert leaks[0]["path"] == "$.operational.feature_id"
    assert "['uttl']" in leaks[0]["message"]


@pytest.mark.parametrize(
    "term", ["ttfcd", "uttl", "consciousness", "gauge", "quantum", "nibbana", "equanimity"],
)
@pytest.mark.parametrize("position", ["feature_id", "symbol", "definition", "preprocessing"])
def test_theory_term_in_any_operational_position_is_rejected(valid_mapping, check, term, position):
    if position == "feature_id":
        valid_mapping["operational"]["feature_id"] = f"{term}_channel_phase_gradient_metrics.phase_grad"
    elif position == "symbol":
        valid_mapping["operational"]["implementation"]["symbol"] = f"{term}_channel_phase_gradient_metrics"
    elif position == "definition":
        valid_mapping["measurement"]["definition"] = f"A {term} reading of the channel phase gradient."
    else:
        valid_mapping["measurement"]["preprocessing"] = [f"bandpass_hilbert_phase_{term}"]
    assert "THEORY_TERM_IN_OPERATIONAL_IDENTIFIER" in _codes(check(valid_mapping))


def test_renaming_an_existing_feature_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["display_name"] = "phase_circulation_feature"
    valid_mapping["operational"]["feature_name"] = "phase_circulation_feature"
    report = check(valid_mapping)
    assert "OPERATIONAL_RENAME_NOT_PERMITTED" in _codes(report)


def test_feature_id_that_does_not_match_the_code_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["feature_id"] = "phase_circulation_feature.phase_grad"
    assert "FEATURE_ID_NOT_DERIVED" in _codes(check(valid_mapping))


def test_unimplemented_neutral_feature_is_refused_not_invented(valid_mapping, check):
    # A neutral name that no code defines must fail to resolve. The validator never creates the feature.
    impl = valid_mapping["operational"]["implementation"]
    impl["symbol"] = "coexact_phase_gradient_feature"
    impl["output_key"] = "coexact_phase_gradient"
    impl["metric_kind_literal"] = "coexact_phase_gradient"
    valid_mapping["operational"]["feature_id"] = "coexact_phase_gradient_feature.coexact_phase_gradient"
    report = check(valid_mapping)
    assert report["contract_status"] == "REJECTED"
    assert "SYMBOL_UNRESOLVED" in _codes(report)
    assert report["implementation"]["symbol_found"] is False


def test_theory_term_with_proposal_wording_is_admissible_in_the_interpretation(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = (
        "Hypothesis only: the channel-index phase gradient could serve as a proxy for the UTTL "
        "phase circulation term. This is a proposed reading and is not a finding."
    )
    valid_mapping["interpretation"]["theory_term"] = "UTTL.phase_circulation"
    assert check(valid_mapping)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
