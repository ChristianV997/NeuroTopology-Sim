"""Privacy regressions using only generated, in-memory synthetic identifiers and text."""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from shared.bids_inventory_audit import (
    audit_inventory,
    metadata_evidence,
    parse_bids_relpath,
    parse_participants_tsv,
    reconcile_license,
)


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
        key.endswith("_count") for key in report["tasks"]["coverage"])
    assert all("subject" not in finding and "path" not in finding and "task" not in finding
               for finding in report["findings"])


def test_malformed_rows_and_missing_columns_do_not_echo_supplied_values():
    marker = "sub-InputMarker96"
    malformed = parse_participants_tsv(f"participant_id\tage\n{marker}\n")
    missing = parse_participants_tsv(f"{marker}\tage\n{marker}\t18\n")
    assert "MALFORMED_ROW" in [finding["code"] for finding in malformed.findings]
    assert "HEADER_MISSING_PARTICIPANT_ID" in [finding["code"] for finding in missing.findings]
    assert marker not in repr(malformed)
    assert marker not in repr(missing)


def test_identifier_like_filename_extension_is_rejected_without_echoing():
    marker = "sub-ExtensionPrivacyMarker99"
    path = f"sub-01/eeg/sub-01_task-rest_eeg.{marker}"
    parsed = parse_bids_relpath(path)
    assert not parsed.valid
    assert "EXTENSION_MALFORMED" in parsed.problems
    assert parsed.extension is None
    assert marker not in repr(parsed)

    report = audit_inventory(participants_tsv=None, file_paths=[path])
    assert marker not in json.dumps(report, sort_keys=True, allow_nan=False)


def test_caller_controlled_entity_values_are_not_returned_in_public_results(caplog):
    marker = "participantmarker123"
    duplicate_key_marker = "PrivacyMarkerABC"
    paths = [
        f"sub-01/eeg/sub-01_task-{marker}_eeg.edf",
        f"sub-01/eeg/sub-01_run-{marker}_eeg.edf",
        f"sub-01/eeg/sub-01_{marker}.edf",
        f"sub-01/eeg/sub-01_task-rest_eeg.{marker}",
    ]
    parsed = [parse_bids_relpath(path) for path in paths]
    duplicate_key_path = (
        f"sub-01/eeg/sub-01_{duplicate_key_marker}-one_"
        f"{duplicate_key_marker}-two_eeg.edf"
    )
    duplicate_key_parsed = parse_bids_relpath(duplicate_key_path)
    duplicate_key_report = audit_inventory(participants_tsv=None, file_paths=[duplicate_key_path])
    unexpected = audit_inventory(
        participants_tsv="participant_id\nsub-01\n",
        file_paths=paths,
        expected_tasks=["rest"],
    )
    expected_only = audit_inventory(
        participants_tsv="participant_id\nsub-01\n",
        file_paths=[],
        expected_tasks=[marker],
    )
    rendered = json.dumps(
        {"parsed": [item.__dict__ for item in parsed], "unexpected": unexpected,
         "expected_only": expected_only, "duplicate_key_parsed": duplicate_key_parsed.__dict__,
         "duplicate_key_report": duplicate_key_report},
        sort_keys=True,
        allow_nan=False,
    )

    assert parsed[0].has_task and parsed[0].task is None
    assert parsed[1].has_run and parsed[1].run is None
    assert parsed[2].has_suffix and parsed[2].suffix is None
    assert parsed[3].has_extension and parsed[3].extension is None
    assert not duplicate_key_parsed.valid
    assert "DUPLICATE_ENTITY" in duplicate_key_parsed.problems
    assert all(duplicate_key_marker not in problem for problem in duplicate_key_parsed.problems)
    assert "expected" not in unexpected["tasks"]
    assert "observed" not in unexpected["tasks"]
    assert unexpected["tasks"]["expected_count"] == 1
    assert unexpected["tasks"]["observed_count"] == 2
    assert unexpected["tasks"]["coverage"]["unexpected_observed_tasks_count"] == 1
    assert all(marker not in key for key in unexpected["tasks"]["coverage"])
    assert "UNEXPECTED_TASK" in [finding["code"] for finding in unexpected["findings"]]
    assert "TASK_ABSENT_FOR_ALL_SUBJECTS" in [finding["code"] for finding in expected_only["findings"]]
    assert all("task" not in finding for finding in expected_only["findings"])
    assert all(marker not in finding["detail"] for finding in unexpected["findings"])
    assert marker not in rendered
    assert duplicate_key_marker not in rendered
    assert marker not in caplog.text
    assert duplicate_key_marker not in caplog.text
    assert all("task" not in finding for finding in unexpected["findings"])


def test_public_license_helpers_do_not_echo_untrusted_source_or_evidence_text():
    marker = "sub-LicensePrivacyMarker72"
    metadata = metadata_evidence({"license": "CC-BY-4.0"}, source=marker)
    reconciled = reconcile_license([{
        "source": marker,
        "status": "RECOGNIZED",
        "tokens": ["CC-BY-4.0", marker],
        "note": marker,
    }])

    rendered = json.dumps([metadata, reconciled], sort_keys=True, allow_nan=False)
    assert marker not in rendered
    assert metadata["source"] == "unspecified"
    assert reconciled["state"] == "UNRESOLVED"
    assert reconciled["sources"] == [{
        "source": "unspecified", "status": "NOT_TEXT", "tokens": [],
    }]


def test_public_license_helpers_redact_caller_exception_text():
    marker = "sub-LicenseErrorMarker73"

    class BrokenMetadata(Mapping):
        def __getitem__(self, key):
            raise ValueError(marker)

        def __iter__(self):
            return iter(("license",))

        def __len__(self):
            return 1

    metadata = metadata_evidence(BrokenMetadata())
    assert metadata["status"] == "NOT_TEXT"
    assert marker not in repr(metadata)

    class BrokenEvidence:
        def __iter__(self):
            raise ValueError(marker)

    reconciled = reconcile_license(BrokenEvidence())
    rendered = json.dumps(reconciled, sort_keys=True, allow_nan=False)
    assert reconciled["state"] == "UNRESOLVED"
    assert marker not in rendered


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
