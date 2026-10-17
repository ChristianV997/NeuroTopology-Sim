"""Deterministic digest of a supplied file listing: read-only, order-independent, and not an identity claim."""
from __future__ import annotations

import builtins
import os

import pytest

from shared.bids_inventory_audit import file_listing_digest

ENTRIES = [
    ("sub-01/eeg/sub-01_task-rest_eeg.edf", b"synthetic-a"),
    ("participants.tsv", b"participant_id\nsub-01\n"),
]


def test_digest_is_the_same_for_any_entry_order():
    forward = file_listing_digest(ENTRIES)
    backward = file_listing_digest(list(reversed(ENTRIES)))
    assert forward["manifest_sha256"] == backward["manifest_sha256"]
    assert forward["manifest_sha256"] is not None


def test_digest_changes_when_any_content_byte_changes():
    base = file_listing_digest(ENTRIES)["manifest_sha256"]
    changed = file_listing_digest([(ENTRIES[0][0], b"synthetic-b"), ENTRIES[1]])["manifest_sha256"]
    assert base != changed


def test_digest_changes_when_a_path_changes_but_content_does_not():
    base = file_listing_digest(ENTRIES)["manifest_sha256"]
    renamed = file_listing_digest([("sub-01/eeg/sub-01_task-stroop_eeg.edf", b"synthetic-a"), ENTRIES[1]])
    assert base != renamed["manifest_sha256"]


def test_empty_payload_entry_is_rejected_and_no_digest_is_produced():
    result = file_listing_digest(ENTRIES + [("sub-09/eeg/sub-09_task-rest_eeg.edf", b"")])
    assert result["manifest_sha256"] is None
    assert result["entries_listed"] == 3
    assert any(f["code"] == "PAYLOAD_EMPTY" and f["severity"] == "error" for f in result["findings"])


def test_empty_payload_is_not_silently_equivalent_to_an_absent_entry():
    with_empty = file_listing_digest(ENTRIES + [("sub-09/eeg/sub-09_task-rest_eeg.edf", b"")])
    without = file_listing_digest(ENTRIES)
    assert with_empty["manifest_sha256"] is None
    assert without["manifest_sha256"] is not None


def test_bytearray_content_hashes_the_same_as_bytes():
    assert file_listing_digest([("a.json", bytearray(b"1"))])["manifest_sha256"] == \
        file_listing_digest([("a.json", b"1")])["manifest_sha256"]


def test_duplicate_path_produces_no_digest():
    result = file_listing_digest(ENTRIES + [(ENTRIES[0][0], b"other")])
    assert result["manifest_sha256"] is None
    assert any(f["code"] == "DUPLICATE_PATH" for f in result["findings"])


@pytest.mark.parametrize("path, code", [
    ("../escape.json", "PATH_UNSAFE"),
    ("/abs.json", "PATH_UNSAFE"),
    ("a\tb.json", "PATH_CONTROL_CHARACTER"),
    ("a\nb.json", "PATH_CONTROL_CHARACTER"),
    (None, "PATH_NOT_TEXT"),
])
def test_unsafe_path_fails_closed(path, code):
    result = file_listing_digest([(path, b"x")])
    assert result["manifest_sha256"] is None
    assert code in [f["code"] for f in result["findings"]]


def test_control_character_path_is_not_echoed_into_findings():
    result = file_listing_digest([("bad\tname.json", b"x")])
    assert all("bad" not in f.get("path", "") for f in result["findings"])


def test_text_content_is_rejected_because_only_bytes_are_listed():
    result = file_listing_digest([("a.json", "text")])
    assert result["manifest_sha256"] is None
    assert any(f["code"] == "CONTENT_NOT_BYTES" for f in result["findings"])


def test_malformed_entry_is_reported_with_its_position():
    result = file_listing_digest([("a.json", b"1", "extra")])
    malformed = [f for f in result["findings"] if f["code"] == "ENTRY_MALFORMED"]
    assert malformed and malformed[0]["path"] == "entry[0]"


def test_non_iterable_input_is_rejected():
    result = file_listing_digest(42)
    assert result["manifest_sha256"] is None
    assert result["findings"][0]["code"] == "ENTRIES_NOT_ITERABLE"


def test_empty_listing_has_a_defined_digest_and_claims_nothing():
    result = file_listing_digest([])
    assert result["entries_listed"] == 0
    assert result["manifest_sha256"] is not None
    assert result["dataset_identity_claim"] is False


def test_every_listing_result_is_an_unregistered_draft():
    for entries in (ENTRIES, [], [("a.json", "text")]):
        result = file_listing_digest(entries)
        assert result["registration_status"] == "UNREGISTERED_DRAFT"
        assert result["external_timestamp_created"] is False
        assert result["dataset_identity_claim"] is False


def test_digest_is_read_only_and_never_touches_the_filesystem(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("filesystem access attempted")

    monkeypatch.setattr(builtins, "open", _forbidden)
    monkeypatch.setattr(os, "listdir", _forbidden)
    monkeypatch.setattr(os, "scandir", _forbidden)
    assert file_listing_digest(ENTRIES)["manifest_sha256"] is not None
