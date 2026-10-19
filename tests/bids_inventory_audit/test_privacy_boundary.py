"""Privacy regressions using only generated, in-memory synthetic identifiers and text."""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from shared.bids_inventory_audit import audit_inventory, parse_participants_tsv


def test_default_audit_json_omits_ids_paths_and_file_to_subject_mappings(caplog, capsys):
    participant = "sub-PrivacyMarker91"
    file_only = "sub-FileOnlyMarker92"
    excluded_unknown = "sub-ExcludedMarker93"
    unsafe_marker = "sub-PathEscapeMarker94"
    duplicate_path = f"{participant}/eeg/{participant}_task-rest_eeg.edf"
    tsv = (
        "participant_id\tage\n"
        f"{participant}\t36\n"
        f"{participant}\t37\n"  # Duplicate is excluded, but its identifier must not escape.
        "sub-PrivacyMarker95\t40\n"
    )
    paths = [
        duplicate_path,
        duplicate_path,
        f"{file_only}/eeg/{file_only}_task-rest_eeg.edf",
        f"../{unsafe_marker}/eeg/{unsafe_marker}_task-rest_eeg.edf",
        "sub-PrivacyMarker95/eeg/sub-PrivacyMarker95_task-rest_eeg.edf.bak",
    ]
    record = {"analyzed_n": 2, "excluded_subjects": [participant, excluded_unknown]}

    with caplog.at_level(logging.DEBUG):
        report = audit_inventory(
            participants_tsv=tsv,
            file_paths=paths,
            expected_tasks=["rest", "bad-task"],
            analysis_record=record,
        )
    rendered = json.dumps(report, sort_keys=True, allow_nan=False)
    captured = capsys.readouterr()

    for marker in (participant, file_only, excluded_unknown, unsafe_marker, "36", "37", "40"):
        assert marker not in rendered
        assert marker not in caplog.text
        assert marker not in captured.out
        assert marker not in captured.err
    assert report["participants"]["subject_count"] == 1
    assert report["participants"]["file_subject_count"] == 2
    assert report["participants"]["file_only_subject_count"] == 2
    assert report["analysis"]["excluded_subjects_n"] is None  # inconsistent declaration is not quoted
    assert "subjects" not in report["participants"]
    assert "coverage" in report["tasks"] and all(
        isinstance(value, dict) for value in report["tasks"]["coverage"].values())
    assert all("subject" not in finding and "path" not in finding for finding in report["findings"])


def test_malformed_rows_and_missing_columns_do_not_echo_supplied_values():
    marker = "sub-InputMarker96"
    malformed = parse_participants_tsv(f"participant_id\tage\n{marker}\n")
    missing = parse_participants_tsv(f"{marker}\tage\n{marker}\t18\n")
    assert "MALFORMED_ROW" in [finding["code"] for finding in malformed.findings]
    assert "HEADER_MISSING_PARTICIPANT_ID" in [finding["code"] for finding in missing.findings]
    assert marker not in repr(malformed)
    assert marker not in repr(missing)


def test_unreadable_caller_iterable_returns_generic_error_without_echoing_exception(caplog):
    marker = "sub-IteratorErrorMarker97"

    class SyntheticBrokenListing:
        def __iter__(self):
            raise ValueError(marker)

    report = audit_inventory(participants_tsv=None, file_paths=SyntheticBrokenListing())
    rendered = json.dumps(report, sort_keys=True, allow_nan=False)
    assert "FILE_LISTING_UNREADABLE" in [finding["code"] for finding in report["findings"]]
    assert marker not in rendered and marker not in caplog.text
    assert report["entries"]["listed"] is None
    assert report["participants"]["cross_check"] == "NOT_PERFORMED"
    assert report["tasks"]["coverage"] is None


def test_unreadable_expected_tasks_return_generic_error_without_echoing_exception():
    marker = "sub-TaskIteratorErrorMarker97"

    class SyntheticBrokenTasks:
        def __iter__(self):
            raise ValueError(marker)

    report = audit_inventory(participants_tsv=None, file_paths=[], expected_tasks=SyntheticBrokenTasks())
    rendered = json.dumps(report, sort_keys=True, allow_nan=False)
    assert "EXPECTED_TASKS_UNREADABLE" in [finding["code"] for finding in report["findings"]]
    assert marker not in rendered


def test_unreadable_analysis_mapping_returns_generic_error_without_echoing_exception():
    marker = "sub-AnalysisMappingMarker97"

    class SyntheticBrokenRecord(Mapping):
        def __getitem__(self, key):
            raise ValueError(marker)

        def __iter__(self):
            return iter(("analyzed_n", "excluded_subjects"))

        def __len__(self):
            return 2

    report = audit_inventory(participants_tsv=None, file_paths=[], analysis_record=SyntheticBrokenRecord())
    rendered = json.dumps(report, sort_keys=True, allow_nan=False)
    assert "ANALYSIS_RECORD_MALFORMED" in [finding["code"] for finding in report["findings"]]
    assert marker not in rendered


def test_audit_output_is_deterministic_for_same_synthetic_inputs():
    marker = "sub-DeterministicMarker98"
    tsv = f"participant_id\tage\n{marker}\t42\n"
    paths = [f"{marker}/eeg/{marker}_task-rest_eeg.edf"]
    first = audit_inventory(participants_tsv=tsv, file_paths=paths, expected_tasks=["rest"])
    second = audit_inventory(participants_tsv=tsv, file_paths=list(paths), expected_tasks=["rest"])
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)
    assert marker not in json.dumps(first, sort_keys=True, allow_nan=False)
