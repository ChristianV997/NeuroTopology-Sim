"""Inventory audit: cross-checks, declared-only task expectations, duplicates, scope, and determinism."""
from __future__ import annotations

import json
import random

import pytest

from shared.bids_inventory_audit import audit_inventory


def _codes(report, severity=None):
    return [f["code"] for f in report["findings"] if severity is None or f["severity"] == severity]


def _find(report, code):
    return [f for f in report["findings"] if f["code"] == code]


# ── synthetic fixture: participant and file cross-checks ─────────────────────

def test_fixture_subject_cross_checks(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)
    assert report["participants"]["cross_check"] == "PERFORMED"
    assert report["participants"]["file_only_subject_count"] == 1
    assert report["participants"]["participants_without_files_count"] == 1
    assert _find(report, "FILE_SUBJECT_NOT_IN_PARTICIPANTS")[0]["affected_count"] == 1
    assert _find(report, "PARTICIPANT_WITHOUT_FILES")[0]["affected_count"] == 1


def test_fixture_path_classification_and_counts(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)
    assert report["entries"] == {"listed": 8, "subject_entries_valid": 4,
                                 "non_subject_entries": 2, "invalid_entries": 2}
    invalid = _find(report, "UNPARSEABLE_PATH")
    assert len(invalid) == 1 and invalid[0]["affected_count"] == 2
    assert "path" not in invalid[0]


def test_backup_copy_does_not_manufacture_task_coverage(synthetic_tsv):
    listing = ["sub-02/eeg/sub-02_task-stroop_eeg.edf.bak", "sub-02/eeg/sub-02_task-rest_eeg.edf"]
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=listing,
                             expected_tasks=["rest", "stroop"])
    assert report["tasks"]["coverage"] == {
        "rest": {"subjects_with_file_count": 1, "subject_count": 3},
    }
    assert "stroop" not in report["tasks"]["observed"]


def test_fixture_coverage_is_recorded_per_participant(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)
    assert report["tasks"]["coverage"] == {
        "rest": {"subjects_with_file_count": 3, "subject_count": 3},
        "stroop": {"subjects_with_file_count": 1, "subject_count": 3},
    }


# ── tasks: only against a declared set ───────────────────────────────────────

def test_undeclared_expectation_is_reported_and_nothing_is_inferred(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=None)
    assert "EXPECTED_TASKS_NOT_DECLARED" in _codes(report, "error")
    assert report["tasks"]["expected_declared"] is False
    assert report["tasks"]["expected"] is None
    assert report["tasks"]["observed"] == ["rest", "stroop"]  # observation is reported, not used
    for code in ("UNEXPECTED_TASK", "TASK_ABSENT_FOR_ALL_SUBJECTS", "MISSING_TASK_FOR_SUBJECT"):
        assert code not in _codes(report)


def test_declared_tasks_yield_per_participant_gaps(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest", "stroop"])
    gaps = {f["task"]: f["affected_count"] for f in _find(report, "MISSING_TASK_FOR_SUBJECT")}
    assert gaps == {"rest": 1, "stroop": 2}
    assert not _find(report, "TASK_ABSENT_FOR_ALL_SUBJECTS")


def test_task_absent_for_every_participant_is_an_error(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest", "nback"])
    absent = _find(report, "TASK_ABSENT_FOR_ALL_SUBJECTS")
    assert [f["task"] for f in absent] == ["nback"]
    assert absent[0]["severity"] == "error"
    assert absent[0]["affected_count"] == 3


def test_observed_task_outside_the_declared_set_is_flagged(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest"])
    unexpected = _find(report, "UNEXPECTED_TASK")
    assert [f["task"] for f in unexpected] == ["stroop"]
    assert unexpected[0]["severity"] == "warning"


@pytest.mark.parametrize("label", ["n-back", "rest stroop", "", "rest!"])
def test_invalid_declared_task_label_is_rejected_not_silently_kept(synthetic_tsv, synthetic_listing, label):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest", label])
    assert "EXPECTED_TASK_INVALID" in _codes(report, "error")
    assert report["tasks"]["expected"] == ["rest"]


def test_without_a_participants_table_only_whole_listing_absence_is_reported(synthetic_listing):
    report = audit_inventory(participants_tsv=None, file_paths=synthetic_listing,
                             expected_tasks=["rest", "nback"])
    assert "PARTICIPANTS_NOT_PROVIDED" in _codes(report, "error")
    assert report["participants"]["cross_check"] == "NOT_PERFORMED"
    assert report["participants"]["universe_source"] == "none"
    absent = _find(report, "TASK_ABSENT_IN_LISTING")
    assert [f["task"] for f in absent] == ["nback"]
    assert not _find(report, "MISSING_TASK_FOR_SUBJECT")
    assert not _find(report, "TASK_ABSENT_FOR_ALL_SUBJECTS")


def test_without_participants_file_subjects_are_not_treated_as_the_cohort(synthetic_listing):
    report = audit_inventory(participants_tsv=None, file_paths=synthetic_listing)
    assert report["participants"]["subject_count"] is None
    assert report["participants"]["participants_without_files_count"] is None


# ── duplicates ───────────────────────────────────────────────────────────────

def test_identical_path_listed_twice_is_a_duplicate_file(synthetic_tsv):
    listing = ["sub-01/eeg/sub-01_task-rest_eeg.edf", "sub-01/eeg/sub-01_task-rest_eeg.edf"]
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=listing)
    duplicate = _find(report, "DUPLICATE_FILE")
    assert len(duplicate) == 1 and duplicate[0]["affected_count"] == 1
    assert "path" not in duplicate[0]


def test_different_paths_claiming_the_same_entities_are_flagged_not_resolved(synthetic_tsv):
    listing = ["sub-01/eeg/sub-01_task-rest_eeg.edf", "sub-01/func/sub-01_task-rest_eeg.edf"]
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=listing)
    flagged = _find(report, "DUPLICATE_ENTITY_SIGNATURE")
    assert len(flagged) == 1 and flagged[0]["affected_count"] == 1 and flagged[0]["severity"] == "error"
    assert "subject" not in flagged[0] and "path" not in flagged[0]


def test_participant_table_problems_are_carried_into_the_audit():
    # sub-01 is duplicated and sub-02's row is malformed, so no participant survives the table.
    # The file for sub-02 must then be reported as absent from the table, not quietly accepted.
    tsv = "participant_id\tage\nsub-01\t20\nsub-01\t21\nsub-02\n"
    report = audit_inventory(participants_tsv=tsv, file_paths=["sub-02/eeg/sub-02_task-rest_eeg.edf"])
    assert "DUPLICATE_PARTICIPANT" in _codes(report, "error")
    assert "MALFORMED_ROW" in _codes(report, "error")
    assert report["participants"]["subject_count"] == 0
    assert report["participants"]["file_only_subject_count"] == 1
    assert _find(report, "FILE_SUBJECT_NOT_IN_PARTICIPANTS")[0]["affected_count"] == 1


# ── scope and claim boundaries ───────────────────────────────────────────────

def test_scope_and_status_fields_are_fixed(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)
    assert report["scope"] == "INVENTORY_LEVEL_ONLY_PENDING_AUTHORITATIVE_MANIFEST"
    assert report["status"] == "HOLD"
    assert report["evidence_class"] == "SYNTHETIC_ONLY"
    assert report["registration_status"] == "UNREGISTERED_DRAFT"
    assert report["authoritative_manifest"] is False
    assert report["download_authorized"] is False
    assert report["analysis_authorized"] is False
    assert report["scientific_pass"] is False


def test_cohort_identity_is_never_established(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest"])
    assert report["cohort_identity"] == "NOT_ESTABLISHED"
    assert "not a cohort identification" in report["cohort_statement"]


def test_license_conflict_stays_unresolved_in_the_audit(synthetic_tsv, synthetic_listing,
                                                        synthetic_readme, synthetic_nemar):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             readme_text=synthetic_readme, nemar_metadata=synthetic_nemar)
    assert report["license"]["state"] == "CONFLICT_UNRESOLVED"
    assert report["license"]["resolved"] is False
    assert report["license"]["selected_license"] is None
    assert "LICENSE_CONFLICT_UNRESOLVED" in _codes(report, "error")


# ── determinism and strict output ────────────────────────────────────────────

def test_output_is_strict_json_and_deterministic(synthetic_tsv, synthetic_listing):
    first = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                            expected_tasks=["rest", "stroop"])
    second = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             expected_tasks=["rest", "stroop"])
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)


def test_listing_order_does_not_change_findings_or_coverage(synthetic_tsv, synthetic_listing):
    shuffled = list(synthetic_listing)
    random.Random(7).shuffle(shuffled)
    base = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                           expected_tasks=["rest", "stroop"])
    permuted = audit_inventory(participants_tsv=synthetic_tsv, file_paths=shuffled,
                               expected_tasks=["rest", "stroop"])
    assert base["findings"] == permuted["findings"]
    assert base["tasks"] == permuted["tasks"]
    assert base["participants"] == permuted["participants"]


def test_empty_inputs_produce_a_hold_report_with_errors_not_a_pass():
    report = audit_inventory(participants_tsv=None, file_paths=[], expected_tasks=None)
    assert report["status"] == "HOLD"
    assert report["severity_counts"]["error"] >= 2
    assert report["scientific_pass"] is False
