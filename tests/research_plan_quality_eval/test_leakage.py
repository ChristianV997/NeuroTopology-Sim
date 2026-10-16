from __future__ import annotations

import random

from tools.research_plan_quality_eval.leakage import (
    NEAR_DUPLICATE_THRESHOLD,
    REASON_EXACT,
    REASON_NEAR,
    REASON_NORMALIZED,
    detect_cross_split_leaks,
)
from tools.research_plan_quality_eval.records import PlanRecord
from tools.research_plan_quality_eval.splits import DEVELOPMENT, LOCKED_INTERNAL_VALIDATION

from .conftest import record_with


def _dev_record(shipped_records) -> PlanRecord:
    return next(r for r in shipped_records if r.fixture_id == "fx-v1-P01")


def _held_record(shipped_records) -> PlanRecord:
    return next(r for r in shipped_records if r.fixture_id == "fx-v1-P10")


def _as_held_copy(record: PlanRecord, fixture_id: str, **overrides) -> PlanRecord:
    relabelled = record_with(record, plan_id=fixture_id, **overrides)
    return PlanRecord(fixture_id=fixture_id, group_id="held-group-x", split=LOCKED_INTERNAL_VALIDATION,
                      plan=relabelled.plan)


def test_shipped_fixtures_have_no_cross_split_duplicates(shipped_records):
    report = detect_cross_split_leaks(shipped_records)
    assert report.cross_split_findings == ()
    assert report.held_out_plans_with_cross_split_match == 0


def test_exact_copy_across_splits_is_detected_with_all_matching_reasons(shipped_records):
    dev = _dev_record(shipped_records)
    leaked = _as_held_copy(dev, "fx-x-copy")
    report = detect_cross_split_leaks([*shipped_records, leaked])
    finding = next(f for f in report.cross_split_findings if "fx-x-copy" in (f.left, f.right))
    assert {REASON_EXACT, REASON_NORMALIZED, REASON_NEAR} <= set(finding.reasons)
    assert finding.jaccard == 1.0
    assert report.held_out_plans_with_cross_split_match == 1


def test_normalized_variant_is_flagged_even_when_exact_content_differs(shipped_records):
    dev = _dev_record(shipped_records)
    question = dev.plan.research_question
    variant = question.upper().replace(" ", "   ").replace("FORTY", "ＦＯＲＴＹ") + "!!"
    assert "ＦＯＲＴＹ" in variant
    leaked = _as_held_copy(dev, "fx-x-norm", research_question=variant)
    report = detect_cross_split_leaks([*shipped_records, leaked])
    finding = next(f for f in report.cross_split_findings if "fx-x-norm" in (f.left, f.right))
    assert REASON_NORMALIZED in finding.reasons
    assert REASON_EXACT not in finding.reasons


def test_near_duplicate_above_threshold_is_flagged_across_splits(plan_from):
    words = [f"term{i}" for i in range(60)]
    base = " ".join(words)
    edited_words = list(words)
    edited_words[30] = "changed"
    dev = PlanRecord("d1", "g-dev", DEVELOPMENT, plan_from(plan_id="d1", research_question=base))
    held = PlanRecord("h1", "g-held", LOCKED_INTERNAL_VALIDATION,
                      plan_from(plan_id="h1", research_question=" ".join(edited_words)))
    report = detect_cross_split_leaks([dev, held])
    assert len(report.cross_split_findings) == 1
    finding = report.cross_split_findings[0]
    assert finding.jaccard >= NEAR_DUPLICATE_THRESHOLD
    assert finding.reasons == (REASON_NEAR,)


def test_near_duplicate_below_threshold_is_not_flagged(plan_from):
    words = [f"term{i}" for i in range(60)]
    base = " ".join(words)
    edited = list(words)
    for index in (5, 20, 35, 50):
        edited[index] = f"other{index}"
    dev = PlanRecord("d1", "g-dev", DEVELOPMENT, plan_from(plan_id="d1", research_question=base))
    held = PlanRecord("h1", "g-held", LOCKED_INTERNAL_VALIDATION,
                      plan_from(plan_id="h1", research_question=" ".join(edited)))
    report = detect_cross_split_leaks([dev, held])
    assert report.cross_split_findings == ()


def test_unrelated_plans_are_not_flagged(shipped_records):
    dev = _dev_record(shipped_records)
    held = _held_record(shipped_records)
    report = detect_cross_split_leaks([dev, held])
    assert report.cross_split_findings == ()


def test_duplicates_within_one_split_are_counted_separately_not_as_leakage(shipped_records):
    report = detect_cross_split_leaks(shipped_records)
    assert report.within_split_finding_count == 1
    assert report.cross_split_findings == ()


def test_held_out_match_fraction_counts_only_held_out_plans(shipped_records):
    dev = _dev_record(shipped_records)
    leaked = _as_held_copy(dev, "fx-x-copy")
    report = detect_cross_split_leaks([*shipped_records, leaked])
    payload = report.to_dict()
    assert payload["held_out_plan_count"] == 6
    assert payload["held_out_cross_split_match_fraction"] == round(1 / 6, 4)
    assert "not a criterion-leakage rate" in payload["fraction_label"]


def test_empty_and_single_record_sets_have_no_findings(shipped_records):
    empty = detect_cross_split_leaks([])
    assert empty.plan_count == 0
    assert empty.to_dict()["held_out_cross_split_match_fraction"] is None
    single = detect_cross_split_leaks([shipped_records[0]])
    assert single.cross_split_findings == ()


def test_result_is_independent_of_input_order(shipped_records):
    dev = _dev_record(shipped_records)
    leaked = _as_held_copy(dev, "fx-x-copy")
    combined = [*shipped_records, leaked]
    shuffled = list(combined)
    random.Random(7).shuffle(shuffled)
    assert detect_cross_split_leaks(combined).to_dict() == detect_cross_split_leaks(shuffled).to_dict()
