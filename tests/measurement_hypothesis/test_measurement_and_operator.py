"""Measurements declare units and steps; operators are signal-processing generators, never physical objects."""
from __future__ import annotations

import json
import math

import pytest


def _codes(report):
    return {error["code"] for error in report["errors"]}


@pytest.mark.parametrize("units", [None, ""])
def test_missing_units_are_rejected(valid_mapping, check, units):
    valid_mapping["measurement"]["units"] = units
    assert "UNITS_MISSING" in _codes(check(valid_mapping))


def test_units_absent_from_the_key_are_rejected(valid_mapping, check):
    del valid_mapping["measurement"]["units"]
    assert "UNITS_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("units", ["furlongs", ["rad"], 1.5])
def test_unregistered_or_malformed_units_are_rejected(valid_mapping, check, units):
    valid_mapping["measurement"]["units"] = units
    assert "UNITS_UNREGISTERED" in _codes(check(valid_mapping))


@pytest.mark.parametrize("data_type", ["complex128", None, ["float64"]])
def test_invalid_data_type_is_rejected(valid_mapping, check, data_type):
    valid_mapping["measurement"]["data_type"] = data_type
    assert "DATA_TYPE_INVALID" in _codes(check(valid_mapping))


def test_missing_definition_is_rejected(valid_mapping, check):
    valid_mapping["measurement"]["definition"] = "   "
    assert "DEFINITION_MISSING" in _codes(check(valid_mapping))


@pytest.mark.parametrize("steps", [[], None])
def test_missing_preprocessing_is_rejected(valid_mapping, check, steps):
    valid_mapping["measurement"]["preprocessing"] = steps
    assert "PREPROCESSING_MISSING" in _codes(check(valid_mapping))


def test_unregistered_feature_family_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["feature_family"] = "phase_gradient"
    assert "FEATURE_FAMILY_UNREGISTERED" in _codes(check(valid_mapping))


def test_registered_feature_family_needs_no_family_note(valid_mapping, check):
    valid_mapping["operational"]["feature_family"] = "spatial_phase_charge"
    del valid_mapping["operational"]["family_note"]
    assert check(valid_mapping)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"


def test_absent_family_must_be_explained(valid_mapping, check):
    del valid_mapping["operational"]["family_note"]
    assert "FAMILY_NOTE_MISSING" in _codes(check(valid_mapping))


def test_operator_treated_as_a_physical_role_is_rejected(valid_mapping, check):
    valid_mapping["operator"]["role"] = "physical_gauge_field"
    assert "OPERATOR_ROLE_NOT_PERMITTED" in _codes(check(valid_mapping))


def test_literal_physical_identity_true_is_rejected(valid_mapping, check):
    valid_mapping["operator"]["literal_physical_identity"] = True
    assert "LITERAL_PHYSICAL_IDENTITY_NOT_PERMITTED" in _codes(check(valid_mapping))


def test_missing_literal_physical_identity_flag_is_rejected(valid_mapping, check):
    del valid_mapping["operator"]["literal_physical_identity"]
    assert "LITERAL_PHYSICAL_IDENTITY_NOT_PERMITTED" in _codes(check(valid_mapping))


def test_operator_citing_an_undeclared_source_is_rejected(valid_mapping, check):
    valid_mapping["operator"]["source_ids"] = ["not_declared"]
    assert "SOURCE_UNRESOLVED" in _codes(check(valid_mapping))


def test_unknown_top_level_field_is_rejected(valid_mapping, check):
    valid_mapping["notes"] = "free text"
    assert "UNKNOWN_FIELD" in _codes(check(valid_mapping))


def test_wrong_schema_and_malformed_identifier_are_rejected(valid_mapping, check):
    valid_mapping["schema"] = "NeuroTopologySim.Other.v1"
    valid_mapping["mapping_id"] = "mapping-1"
    codes = _codes(check(valid_mapping))
    assert {"SCHEMA_MISMATCH", "MAPPING_ID_INVALID"} <= codes


def test_malformed_checksum_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["sha256"] = "not-a-digest"
    assert "SHA256_INVALID" in _codes(check(valid_mapping))


def test_non_object_mapping_is_rejected(check):
    assert _codes(check(["not", "a", "mapping"])) == {"MALFORMED_MAPPING"}


def test_non_finite_number_is_rejected_as_non_json(valid_mapping, check):
    valid_mapping["measurement"]["sample_rate"] = math.nan
    assert "NON_FINITE_OR_NON_JSON" in _codes(check(valid_mapping))


def test_serialized_mapping_round_trips_through_strict_json_and_still_validates(valid_mapping, check):
    text = json.dumps(valid_mapping, allow_nan=False)
    assert check(json.loads(text))["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
