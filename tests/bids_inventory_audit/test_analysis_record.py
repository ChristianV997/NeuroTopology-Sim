"""Analyzed N and exclusions are reported only as declared and count-checked. File presence is not completion."""
from __future__ import annotations

import pytest

from shared.bids_inventory_audit import audit_inventory


def _codes(report, severity=None):
    return [f["code"] for f in report["findings"] if severity is None or f["severity"] == severity]


def test_without_a_record_analyzed_n_and_exclusions_are_not_established(synthetic_tsv, synthetic_listing):
    analysis = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)["analysis"]
    assert analysis["status"] == "NOT_ESTABLISHED"
    assert analysis["record_declared"] is False
    assert analysis["analyzed_n"] is None
    assert analysis["excluded_subjects"] is None
    assert analysis["count_check"] == "NOT_PERFORMED"
    assert analysis["authoritative"] is False


def test_absent_record_is_a_warning_not_an_inferred_count(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)
    assert "ANALYSIS_RECORD_NOT_DECLARED" in _codes(report, "warning")
    assert "ANALYSIS_RECORD_NOT_DECLARED" not in _codes(report, "error")


def test_consistent_declared_record_is_reported_as_declared_and_unverified(synthetic_tsv, synthetic_listing,
                                                                          synthetic_analysis_record):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             analysis_record=synthetic_analysis_record)
    analysis = report["analysis"]
    assert analysis["record_status"] == "DECLARED"
    assert analysis["status"] == "DECLARED_UNVERIFIED"
    assert analysis["count_check"] == "CONSISTENT"
    assert analysis["analyzed_n"] == 2
    assert analysis["excluded_subjects"] == ["sub-03"]
    assert analysis["authoritative"] is False
    assert report["analysis_authorized"] is False


def test_declared_count_that_disagrees_with_the_participants_is_flagged_and_quotes_no_number(
        synthetic_tsv, synthetic_listing):
    record = {"analyzed_n": 3, "excluded_subjects": ["sub-03"]}
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing, analysis_record=record)
    analysis = report["analysis"]
    assert "ANALYSIS_COUNT_MISMATCH" in _codes(report, "error")
    assert analysis["count_check"] == "FAILED"
    assert analysis["status"] == "DECLARED_INCONSISTENT"
    assert analysis["analyzed_n"] is None
    assert analysis["excluded_subjects"] is None


def test_exclusion_absent_from_the_participants_fails_the_count_check(synthetic_tsv, synthetic_listing):
    record = {"analyzed_n": 2, "excluded_subjects": ["sub-09"]}
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing, analysis_record=record)
    errors = [f for f in report["findings"] if f["code"] == "EXCLUSION_NOT_IN_PARTICIPANTS"]
    assert [f["subject"] for f in errors] == ["sub-09"]
    assert report["analysis"]["status"] == "DECLARED_INCONSISTENT"


@pytest.mark.parametrize("record", [
    "two",                                                   # not a mapping
    ["analyzed_n", 2],                                       # not a mapping
    {"analyzed_n": 2},                                       # exclusions missing
    {"excluded_subjects": []},                               # count missing
    {"analyzed_n": 2, "excluded_subjects": [], "note": 1},   # unknown key
    {"analyzed_n": True, "excluded_subjects": []},           # a boolean is not a count
    {"analyzed_n": -1, "excluded_subjects": []},
    {"analyzed_n": 2.0, "excluded_subjects": []},
    {"analyzed_n": 2, "excluded_subjects": "sub-03"},        # a string is not a list
    {"analyzed_n": 2, "excluded_subjects": ["03"]},          # not a subject label
    {"analyzed_n": 2, "excluded_subjects": ["sub-03", "sub-03"]},
])
def test_malformed_record_is_rejected_and_quotes_no_number(synthetic_tsv, synthetic_listing, record):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing, analysis_record=record)
    analysis = report["analysis"]
    assert "ANALYSIS_RECORD_MALFORMED" in _codes(report, "error")
    assert analysis["record_status"] == "MALFORMED"
    assert analysis["status"] == "NOT_ESTABLISHED"
    assert analysis["analyzed_n"] is None
    assert analysis["excluded_subjects"] is None


def test_declared_record_without_a_participants_table_is_unchecked_not_confirmed(synthetic_listing,
                                                                                 synthetic_analysis_record):
    report = audit_inventory(participants_tsv=None, file_paths=synthetic_listing,
                             analysis_record=synthetic_analysis_record)
    analysis = report["analysis"]
    assert analysis["status"] == "DECLARED_UNVERIFIED"
    assert analysis["count_check"] == "NOT_PERFORMED"
    assert "ANALYSIS_COUNT_UNCHECKED" in _codes(report, "warning")


def test_task_presence_is_stated_as_not_completion_evidence(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest", "stroop"])
    assert report["tasks"]["completion_evidence"] is False
    assert "not analysis or completion evidence" in report["tasks"]["presence_statement"]


def test_full_task_coverage_still_claims_no_completion(synthetic_tsv):
    listing = [f"sub-0{i}/eeg/sub-0{i}_task-rest_eeg.edf" for i in (1, 2, 3)]
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=listing, expected_tasks=["rest"])
    assert not {"MISSING_TASK_FOR_SUBJECT", "TASK_ABSENT_FOR_ALL_SUBJECTS", "TASK_ABSENT_IN_LISTING"} & set(_codes(report))
    assert report["tasks"]["completion_evidence"] is False
    assert report["analysis"]["status"] == "NOT_ESTABLISHED"
    assert report["scientific_pass"] is False
    assert report["cohort_identity"] == "NOT_ESTABLISHED"
