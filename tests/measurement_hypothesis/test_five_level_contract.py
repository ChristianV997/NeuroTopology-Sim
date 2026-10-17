"""Five-level separation: formal identity, implemented descriptor, sensor measure, empirical claim, interpretation.

Computability and construct validity are reported separately. Nothing here establishes that a
descriptor measures the intended construct.
"""
from __future__ import annotations

import copy

import pytest

from shared.measurement_hypothesis.schema import OPERATIONAL_CATEGORIES

CATEGORIES = sorted(OPERATIONAL_CATEGORIES)
TARGET_PHRASES = ["cortical wave", "consciousness", "biological validation", "source localization"]


def _codes(report):
    return {error["code"] for error in report["errors"]}


# ── operational category ─────────────────────────────────────────────────────

@pytest.mark.parametrize("category", CATEGORIES)
def test_every_closed_category_is_accepted(valid_mapping, check, category):
    valid_mapping["operational"]["category"] = category
    report = check(valid_mapping)
    assert report["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
    assert report["category"] == category


def test_missing_category_fails_closed_and_is_not_computable(valid_mapping, check):
    del valid_mapping["operational"]["category"]
    report = check(valid_mapping)
    assert "CATEGORY_MISSING" in _codes(report)
    assert report["computable"] is False


@pytest.mark.parametrize("value", ["cortical_wave_detector", "", ["sensor_space_winding"], 3])
def test_unknown_or_malformed_category_fails_closed(valid_mapping, check, value):
    valid_mapping["operational"]["category"] = value
    assert "CATEGORY_UNKNOWN" in _codes(check(valid_mapping))


# ── sensor-space observables ─────────────────────────────────────────────────

@pytest.mark.parametrize("observables", [None, [], [""], [3], "a single string"])
def test_missing_or_malformed_observables_are_rejected(valid_mapping, check, observables):
    valid_mapping["measurement"]["observables"] = observables
    assert "OBSERVABLES_MISSING" in _codes(check(valid_mapping))


def test_observable_named_as_a_target_construct_is_rejected(valid_mapping, check):
    valid_mapping["measurement"]["observables"] = ["a cortical wave amplitude"]
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(check(valid_mapping))


# ── level 1: formal or borrowed identity ─────────────────────────────────────

def test_missing_identity_status_is_rejected(valid_mapping, check):
    del valid_mapping["operator"]["identity_status"]
    assert "IDENTITY_STATUS_MISSING" in _codes(check(valid_mapping))


def test_unknown_identity_status_is_rejected(valid_mapping, check):
    valid_mapping["operator"]["identity_status"] = "exact_physical_identity"
    assert "IDENTITY_STATUS_UNKNOWN" in _codes(check(valid_mapping))


def test_borrowed_identity_must_state_its_conditions(valid_mapping, check):
    del valid_mapping["operator"]["identity_conditions"]
    assert "IDENTITY_CONDITIONS_MISSING" in _codes(check(valid_mapping))


def test_implementation_only_identity_needs_no_borrowed_conditions(valid_mapping, check):
    valid_mapping["operator"]["identity_status"] = "implementation_only"
    del valid_mapping["operator"]["identity_conditions"]
    assert check(valid_mapping)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"


# ── level 4: empirical claim, stated and designed but not run ────────────────

def test_missing_empirical_claim_block_is_rejected(valid_mapping, check):
    del valid_mapping["empirical_claim"]
    assert "EMPIRICAL_CLAIM_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("field", ["statement", "required_data", "analysis_design"])
def test_missing_empirical_field_is_rejected(valid_mapping, check, field):
    valid_mapping["empirical_claim"][field] = "  "
    assert "EMPIRICAL_CLAIM_FIELD_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("controls", [[], None, [""]])
def test_empirical_claim_without_controls_is_rejected(valid_mapping, check, controls):
    valid_mapping["empirical_claim"]["controls"] = controls
    assert "EMPIRICAL_CONTROLS_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("status", ["PASS", "VALIDATED", "SUPPORTED", "confirmed"])
def test_overstated_empirical_status_is_rejected(valid_mapping, check, status):
    valid_mapping["empirical_claim"]["status"] = status
    assert "EMPIRICAL_STATUS_OVERSTATED" in _codes(check(valid_mapping))


def test_any_other_empirical_status_is_not_permitted(valid_mapping, check):
    valid_mapping["empirical_claim"]["status"] = "RUNNING"
    assert "EMPIRICAL_STATUS_NOT_PERMITTED" in _codes(check(valid_mapping))


def test_data_access_other_than_not_authorized_is_rejected(valid_mapping, check):
    valid_mapping["empirical_claim"]["data_access"] = "AUTHORIZED"
    assert "DATA_ACCESS_NOT_PERMITTED" in _codes(check(valid_mapping))


def test_empirical_statement_may_pose_a_target_as_a_question(valid_mapping, check):
    valid_mapping["empirical_claim"]["statement"] = (
        "Does the channel-index gradient track a cortical wave under the locked controls?")
    assert check(valid_mapping)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"


def test_empirical_statement_may_not_assert_equivalence(valid_mapping, check):
    valid_mapping["empirical_claim"]["statement"] = "The gradient is identical to cortical propagation."
    assert "EQUIVALENCE_LANGUAGE" in _codes(check(valid_mapping))


# ── construct validity: never established here ───────────────────────────────

def test_missing_construct_validity_block_is_rejected(valid_mapping, check):
    del valid_mapping["construct_validity"]
    assert "CONSTRUCT_VALIDITY_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("status", ["VALIDATED", "ESTABLISHED", "PASS", "valid"])
def test_overstated_construct_validity_is_rejected(valid_mapping, check, status):
    valid_mapping["construct_validity"]["status"] = status
    assert "CONSTRUCT_VALIDITY_OVERSTATED" in _codes(check(valid_mapping))


def test_other_construct_validity_status_is_not_permitted(valid_mapping, check):
    valid_mapping["construct_validity"]["status"] = "PARTIAL"
    assert "CONSTRUCT_VALIDITY_STATUS_NOT_PERMITTED" in _codes(check(valid_mapping))


@pytest.mark.parametrize("field", ["intended_construct", "basis"])
def test_construct_validity_requires_its_fields(valid_mapping, check, field):
    del valid_mapping["construct_validity"][field]
    assert "CONSTRUCT_VALIDITY_FIELD_MISSING" in _codes(check(valid_mapping))


# ── computability is separate from construct validity ────────────────────────

def test_computable_descriptor_can_still_be_rejected_for_construct_overstatement(valid_mapping, check):
    valid_mapping["construct_validity"]["status"] = "VALIDATED"
    report = check(valid_mapping)
    assert report["contract_status"] == "REJECTED"
    assert report["computable"] is True
    assert report["measures_intended_construct"] is False
    assert report["construct_validity_status"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("mutate", [
    lambda m: m,
    lambda m: m["operational"]["implementation"].update(sha256="0" * 64),
    lambda m: m["construct_validity"].update(status="VALIDATED"),
])
def test_measures_intended_construct_is_false_in_every_report(valid_mapping, check, mutate):
    mutate(valid_mapping)
    assert check(valid_mapping)["measures_intended_construct"] is False


def test_checksum_drift_makes_the_descriptor_not_computable(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["sha256"] = "1" * 64
    report = check(valid_mapping)
    assert report["computable"] is False
    assert "IMPLEMENTATION_DRIFT" in _codes(report)


# ── target constructs are never equated with a descriptor ────────────────────

@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("phrase", TARGET_PHRASES)
def test_affirmative_equivalence_to_a_target_is_rejected_for_every_category(valid_mapping, check, category, phrase):
    valid_mapping["operational"]["category"] = category
    valid_mapping["interpretation"]["proposed_interpretation"] = f"The descriptor is a {phrase} measure."
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(check(valid_mapping))


@pytest.mark.parametrize("phrase", TARGET_PHRASES)
def test_negated_target_mention_is_not_an_equivalence(valid_mapping, check, phrase):
    valid_mapping["interpretation"]["proposed_interpretation"] = f"The descriptor is not a {phrase} measure."
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" not in _codes(check(valid_mapping))


def test_assumption_that_equates_a_target_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["assumptions"] = ["The winding is a cortical wave in the sensor array."]
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(check(valid_mapping))


def test_round6_origin_shift_claim_is_rejected(load_fixture, check):
    # Derived from Round 6 claim R6-007 (PR #412): "origin-invariant charge-separation
    # terminology identifies a cortical propagating wave."
    report = check(load_fixture("origin_shift_cortical_wave_equivalence"))
    assert report["contract_status"] == "REJECTED"
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(report)
    assert report["category"] == "origin_shift_identity"


def test_report_carries_separate_computability_and_construct_fields(valid_mapping, check):
    report = copy.deepcopy(check(valid_mapping))
    assert set(report) >= {"computable", "construct_validity_status", "measures_intended_construct", "category"}
    assert report["construct_validity_status"] == "NOT_ESTABLISHED"
