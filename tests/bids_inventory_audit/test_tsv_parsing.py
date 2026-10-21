"""Aggregate-only parsing of generated caller-supplied participants-table text."""
from __future__ import annotations

import pytest

from shared.bids_inventory_audit import parse_participants_tsv


def _codes(result):
    return [finding["code"] for finding in result.findings]


def test_generated_synthetic_table_parses_as_counts_only(synthetic_tsv):
    result = parse_participants_tsv(synthetic_tsv)
    assert (result.accepted_rows, result.rejected_rows) == (3, 0)
    assert not [f for f in result.findings if f["severity"] == "error"]
    assert not hasattr(result, "participants")


def test_crlf_line_endings_parse_the_same_as_lf(synthetic_tsv):
    crlf = synthetic_tsv.replace("\n", "\r\n")
    assert parse_participants_tsv(crlf) == parse_participants_tsv(synthetic_tsv)


def test_leading_byte_order_mark_is_stripped_and_reported():
    result = parse_participants_tsv("\ufeffparticipant_id\nsub-01\n")
    assert result.accepted_rows == 1
    assert "BOM_STRIPPED" in _codes(result)


def test_trailing_newline_is_not_a_blank_line():
    result = parse_participants_tsv("participant_id\nsub-01\n")
    assert result.blank_lines == 0


def test_interior_blank_line_is_counted_and_reported_with_its_line_number():
    result = parse_participants_tsv("participant_id\nsub-01\n\nsub-02\n")
    assert result.accepted_rows == 2
    assert result.blank_lines == 1
    blank = [f for f in result.findings if f["code"] == "BLANK_LINE"]
    assert blank and blank[0]["line"] == 3


@pytest.mark.parametrize("text", ["", "   \n\t\n", "\n\n"])
def test_empty_or_whitespace_only_table_fails_closed(text):
    result = parse_participants_tsv(text)
    assert result.accepted_rows == 0
    assert "EMPTY_TSV" in _codes(result)


def test_header_without_participant_id_fails_closed_even_with_rows():
    result = parse_participants_tsv("subject\tage\nsub-01\t20\n")
    assert result.accepted_rows == 0
    assert "HEADER_MISSING_PARTICIPANT_ID" in _codes(result)


def test_space_separated_table_is_not_accepted_as_tab_separated():
    result = parse_participants_tsv("participant_id age\nsub-01 20\n")
    assert result.accepted_rows == 0
    assert "HEADER_MISSING_PARTICIPANT_ID" in _codes(result)


def test_repeated_header_column_fails_closed_without_echoing_column_values():
    result = parse_participants_tsv("participant_id\tsub-HeaderMarker\tsub-HeaderMarker\nsub-01\tx\tx\n")
    assert result.accepted_rows == 0
    assert "DUPLICATE_HEADER_COLUMN" in _codes(result)
    assert "sub-HeaderMarker" not in repr(result)


def test_malformed_rows_are_excluded_and_reported_with_line_numbers_only():
    marker = "sub-PrivacyMarker73"
    text = f"participant_id\tage\nsub-01\t20\n{marker}\nsub-03\t25\textra\n"
    result = parse_participants_tsv(text)
    assert result.accepted_rows == 1
    assert result.rejected_rows == 2
    malformed = [f for f in result.findings if f["code"] == "MALFORMED_ROW"]
    assert [f["line"] for f in malformed] == [3, 4]
    assert marker not in repr(result)


@pytest.mark.parametrize("bad_id", ["sub_01", "01", "sub-", "subject-01", "sub-01 ", "SUB-01"])
def test_invalid_participant_identifiers_are_excluded(bad_id):
    result = parse_participants_tsv(f"participant_id\tage\n{bad_id}\t20\nsub-02\t22\n")
    assert result.accepted_rows == 1
    assert "INVALID_PARTICIPANT_ID" in _codes(result)
    assert bad_id not in repr(result)


def test_prefix_only_invalid_participant_is_not_echoed_by_generic_finding():
    bad_id = "sub-"
    result = parse_participants_tsv(f"participant_id\tage\n{bad_id}\t20\nsub-02\t22\n")
    assert result.accepted_rows == 1
    assert "INVALID_PARTICIPANT_ID" in _codes(result)
    assert bad_id not in repr(result)


def test_empty_participant_cell_is_invalid():
    result = parse_participants_tsv("participant_id\tage\n\t20\nsub-02\t22\n")
    assert result.accepted_rows == 1
    assert "INVALID_PARTICIPANT_ID" in _codes(result)


def test_duplicate_participant_excludes_every_occurrence_without_echoing_id():
    marker = "sub-DuplicateMarker74"
    text = f"participant_id\tage\n{marker}\t20\nsub-02\t22\n{marker}\t21\n"
    result = parse_participants_tsv(text)
    assert result.accepted_rows == 1
    assert result.rejected_rows == 2
    duplicates = [f for f in result.findings if f["code"] == "DUPLICATE_PARTICIPANT"]
    assert sorted(f["line"] for f in duplicates) == [2, 4]
    assert all("subject" not in f for f in duplicates)
    assert marker not in repr(result)


@pytest.mark.parametrize("value", [None, b"participant_id\nsub-01\n", ["participant_id"], 7])
def test_non_text_input_is_rejected_without_parsing(value):
    result = parse_participants_tsv(value)
    assert result.accepted_rows == 0
    assert _codes(result) == ["TSV_NOT_TEXT"]


def test_public_parse_summary_omits_identifiers_and_other_columns():
    marker = "sub-PrivacyMarker77"
    result = parse_participants_tsv(f"participant_id\tage\n{marker}\t927\n")
    assert result.accepted_rows == 1
    assert not hasattr(result, "participants")
    assert marker not in repr(result)
    assert "927" not in repr(result)
