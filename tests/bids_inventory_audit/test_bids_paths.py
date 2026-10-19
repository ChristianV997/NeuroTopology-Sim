"""BIDS path structure checks whose public summaries omit raw paths and subject labels."""
from __future__ import annotations

import pytest

from shared.bids_inventory_audit import parse_bids_relpath, unsafe_reason


def test_task_and_run_entities_are_parsed_without_returning_subject_label():
    marker = "sub-PathMarker11"
    parsed = parse_bids_relpath(f"{marker}/eeg/{marker}_task-rest_run-01_eeg.edf")
    assert parsed.valid and parsed.is_subject_file and parsed.has_subject
    assert (parsed.task, parsed.run, parsed.suffix, parsed.extension) == ("rest", "01", "eeg", ".edf")
    assert not hasattr(parsed, "subject") and not hasattr(parsed, "relpath")
    assert marker not in repr(parsed)


def test_session_presence_is_reported_without_returning_session_label():
    marker = "sub-PathMarker12"
    parsed = parse_bids_relpath(f"{marker}/ses-pre/eeg/{marker}_ses-pre_task-rest_eeg.edf")
    assert parsed.valid and parsed.has_session
    assert "pre" not in repr(parsed)


def test_compound_extension_is_kept_intact():
    parsed = parse_bids_relpath("sub-01/func/sub-01_task-rest_bold.nii.gz")
    assert parsed.valid and parsed.extension == ".nii.gz" and parsed.suffix == "bold"


def test_root_level_file_is_valid_but_not_a_subject_file():
    parsed = parse_bids_relpath("participants.tsv")
    assert parsed.valid and not parsed.is_subject_file and not parsed.has_subject


def test_non_subject_tree_is_valid_but_not_a_subject_file():
    parsed = parse_bids_relpath("derivatives/pipeline/dataset_description.json")
    assert parsed.valid and not parsed.is_subject_file


@pytest.mark.parametrize("path, code", [
    ("/etc/passwd", "PATH_UNSAFE"),
    ("C:/data/sub-01_task-rest_eeg.edf", "PATH_UNSAFE"),
    ("sub-01\\eeg\\sub-01_task-rest_eeg.edf", "PATH_UNSAFE"),
    ("sub-01/../sub-02/eeg/sub-02_task-rest_eeg.edf", "PATH_UNSAFE"),
    ("sub-01//eeg/sub-01_task-rest_eeg.edf", "PATH_UNSAFE"),
    ("./sub-01/eeg/sub-01_task-rest_eeg.edf", "PATH_UNSAFE"),
    ("sub-01/eeg/sub-01_task-rest_eeg.edf\t", "PATH_EMPTY_OR_PADDED"),
    (" sub-01/eeg/sub-01_task-rest_eeg.edf", "PATH_EMPTY_OR_PADDED"),
    ("", "PATH_EMPTY_OR_PADDED"),
    ("sub-01/eeg/sub-01_task-rest\teeg.edf", "PATH_CONTROL_CHARACTER"),
    (None, "PATH_NOT_TEXT"),
    (7, "PATH_NOT_TEXT"),
])
def test_unsafe_or_non_text_paths_are_rejected(path, code):
    assert unsafe_reason(path) == code
    parsed = parse_bids_relpath(path)
    assert not parsed.valid and code in parsed.problems
    assert not hasattr(parsed, "relpath") and not hasattr(parsed, "subject")


def test_rejected_path_is_not_echoed_when_it_is_not_text():
    parsed = parse_bids_relpath(None)
    assert "relpath" not in repr(parsed)


def test_subject_directory_must_match_filename_subject_without_echoing_either():
    marker = "sub-MismatchMarker13"
    parsed = parse_bids_relpath(f"{marker}/eeg/sub-OtherMarker14_task-rest_eeg.edf")
    assert not parsed.valid and "PATH_SUBJECT_MISMATCH" in parsed.problems
    assert marker not in repr(parsed) and "OtherMarker14" not in repr(parsed)


def test_missing_subject_entity_is_reported():
    parsed = parse_bids_relpath("sub-01/eeg/task-rest_eeg.edf")
    assert not parsed.valid and "SUBJECT_ENTITY_MISSING" in parsed.problems


def test_subject_entity_must_come_first():
    parsed = parse_bids_relpath("sub-01/eeg/task-rest_sub-01_eeg.edf")
    assert not parsed.valid and "SUBJECT_ENTITY_NOT_FIRST" in parsed.problems


def test_duplicate_entity_within_a_filename_is_reported():
    parsed = parse_bids_relpath("sub-01/eeg/sub-01_task-rest_task-stroop_eeg.edf")
    assert not parsed.valid and "DUPLICATE_ENTITY:task" in parsed.problems


def test_entity_without_a_hyphen_is_malformed():
    parsed = parse_bids_relpath("sub-01/eeg/sub-01_taskrest_eeg.edf")
    assert not parsed.valid and "ENTITY_MALFORMED" in parsed.problems


def test_entity_value_with_a_dot_is_a_malformed_suffix():
    parsed = parse_bids_relpath("sub-01/eeg/sub-01_task-rest_run-1.5_eeg.edf")
    assert not parsed.valid and "SUFFIX_MALFORMED" in parsed.problems


def test_missing_extension_is_reported():
    parsed = parse_bids_relpath("sub-01/eeg/sub-01_task-rest_eeg")
    assert not parsed.valid and "EXTENSION_MISSING" in parsed.problems


def test_empty_stem_is_reported():
    parsed = parse_bids_relpath("sub-01/eeg/.edf")
    assert not parsed.valid and "FILENAME_EMPTY_STEM" in parsed.problems


@pytest.mark.parametrize("name", [
    "sub-01/eeg/sub-01_task-rest_eeg.edf.bak",
    "sub-01/eeg/sub-01_task-rest_eeg.edf.tmp",
    "sub-01/eeg/sub-01_task-rest_eeg.edf.partial",
])
def test_backup_or_temporary_copy_is_never_a_valid_data_file(name):
    parsed = parse_bids_relpath(name)
    assert not parsed.valid and "EXTENSION_BACKUP_OR_TEMP" in parsed.problems


def test_public_summaries_do_not_expose_entity_signatures():
    first = parse_bids_relpath("sub-01/eeg/sub-01_task-rest_eeg.edf")
    second = parse_bids_relpath("sub-02/func/sub-02_task-rest_eeg.edf")
    assert first == second
