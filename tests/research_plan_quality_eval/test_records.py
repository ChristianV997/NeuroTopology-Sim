from __future__ import annotations

import copy
import dataclasses

import pytest

from tools.research_plan_quality.models import ResearchPlan
from tools.research_plan_quality_eval.errors import MalformedRecordError
from tools.research_plan_quality_eval.records import (
    FORBIDDEN_LABEL_KEYS,
    exact_fingerprint,
    normalize_text,
    normalized_fingerprint,
    parse_json_bytes,
    plan_from_dict,
)


def test_plan_schema_contains_no_label_or_target_fields():
    field_names = {f.name for f in dataclasses.fields(ResearchPlan)}
    assert field_names.isdisjoint(FORBIDDEN_LABEL_KEYS)


@pytest.mark.parametrize("label_key", sorted(FORBIDDEN_LABEL_KEYS))
def test_label_like_key_in_a_plan_record_is_rejected(base_plan_dict, label_key):
    data = copy.deepcopy(base_plan_dict)
    data[label_key] = "leaked"
    with pytest.raises(MalformedRecordError, match="label-like keys"):
        plan_from_dict(data, "P01.json")


def test_unknown_key_is_rejected(base_plan_dict):
    data = copy.deepcopy(base_plan_dict)
    data["surprise_field"] = 1
    with pytest.raises(MalformedRecordError):
        plan_from_dict(data, "P01.json")


@pytest.mark.parametrize(
    "override",
    [
        {"sample_size": "forty"},
        {"sample_size": True},
        {"minimum_required_sample_size": 3.5},
        {"number_of_planned_tests": "three"},
        {"evidence_class_declared": "anecdotal"},
        {"secondary_endpoints": "not-a-list"},
        {"condition_labels": [1, 2]},
        {"sources": ["not-an-object"]},
        {"power_analysis": {"target_power": "0.8"}},
        {"reproducibility": {"seed": 1.5}},
        {"research_question": 42},
    ],
)
def test_wrong_types_are_rejected_before_the_rubric_sees_them(base_plan_dict, override):
    data = copy.deepcopy(base_plan_dict)
    data.update(override)
    with pytest.raises(MalformedRecordError):
        plan_from_dict(data, "P01.json")


def test_non_object_plan_record_is_rejected():
    with pytest.raises(MalformedRecordError, match="JSON object"):
        plan_from_dict(["not", "an", "object"], "P01.json")


def test_nan_and_infinity_constants_are_rejected_at_parse_time():
    with pytest.raises(MalformedRecordError, match="non-finite"):
        parse_json_bytes(b'{"sample_size": NaN}', "x.json")
    with pytest.raises(MalformedRecordError, match="non-finite"):
        parse_json_bytes(b'{"power_analysis": {"alpha": Infinity}}', "x.json")


def test_invalid_utf8_and_invalid_json_are_rejected():
    with pytest.raises(MalformedRecordError):
        parse_json_bytes(b"\xff\xfe", "x.json")
    with pytest.raises(MalformedRecordError):
        parse_json_bytes(b"{not json", "x.json")


def test_absent_optional_fields_stay_absent_and_are_never_filled_in():
    plan = plan_from_dict({"plan_id": "bare"}, "bare.json")
    assert plan.sample_size is None
    assert plan.null_model is None
    assert plan.sources == ()
    assert plan.evidence_class_declared is None


def test_exact_fingerprint_ignores_plan_id_but_not_content(base_plan_dict):
    original = plan_from_dict(base_plan_dict, "a")
    relabelled = plan_from_dict({**base_plan_dict, "plan_id": "other"}, "b")
    changed = plan_from_dict({**base_plan_dict, "sample_size": 41}, "c")
    assert exact_fingerprint(original) == exact_fingerprint(relabelled)
    assert exact_fingerprint(original) != exact_fingerprint(changed)


def test_normalization_folds_case_punctuation_and_compatibility_forms():
    assert normalize_text("ＦＯＲＴＹ,  Participants!") == normalize_text("forty participants")
    assert normalize_text("A-B_C") == "a b c"
    assert normalize_text("") == ""


def test_normalized_fingerprint_matches_surface_variants(base_plan_dict):
    variant = copy.deepcopy(base_plan_dict)
    variant["research_question"] = variant["research_question"].upper().replace(" ", "  ") + "."
    a = plan_from_dict(base_plan_dict, "a")
    b = plan_from_dict(variant, "b")
    assert normalized_fingerprint(a) == normalized_fingerprint(b)
    assert exact_fingerprint(a) != exact_fingerprint(b)
