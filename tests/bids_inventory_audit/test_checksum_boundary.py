"""Payload checksum boundary: byte integrity is kept apart from registration, which is always a draft."""
from __future__ import annotations

import hashlib
import json

import pytest

from shared.bids_inventory_audit import check_payload_digest
from shared.bids_inventory_audit.checksum import (
    DIGEST_MALFORMED,
    DIGEST_MISSING,
    DIGEST_PLACEHOLDER,
    PAYLOAD_DIGEST_MISMATCH,
    PAYLOAD_EMPTY,
    PAYLOAD_INTEGRITY_VERIFIED,
    PAYLOAD_MISSING,
)

PAYLOAD = b'{"synthetic": true, "plan": "fixture"}'
CORRECT = hashlib.sha256(PAYLOAD).hexdigest()
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


class _EqualityRaises:
    def __eq__(self, other):
        raise RuntimeError("caller equality must not run")


class _StringEqualityRaises(str):
    def __eq__(self, other):
        raise RuntimeError("caller string-subclass equality must not run")


def _outcome(payload, digest):
    return check_payload_digest(payload, digest)["payload_integrity"]


def _assert_boundary(result):
    """Every checksum result is a draft with no timestamp and no preregistration claim."""
    assert result["registration_status"] == "UNREGISTERED_DRAFT"
    assert result["external_timestamp_created"] is False
    assert result["preregistration_claim"] is False
    assert "not preregistration" in result["statement"]


# ── input classes named in the assignment ────────────────────────────────────

def test_none_digest_is_missing_not_verified():
    assert _outcome(PAYLOAD, None) == DIGEST_MISSING


def test_empty_string_digest_is_treated_as_missing():
    assert _outcome(PAYLOAD, "") == DIGEST_MISSING


def test_none_payload_is_missing_and_never_verified():
    assert _outcome(None, CORRECT) == PAYLOAD_MISSING


def test_text_payload_is_rejected_because_only_bytes_are_hashed():
    assert _outcome("text payload", CORRECT) == PAYLOAD_MISSING


def test_empty_bytes_payload_is_never_verified_even_with_its_own_digest():
    result = check_payload_digest(b"", EMPTY_DIGEST)
    assert result["payload_integrity"] == PAYLOAD_EMPTY
    assert result["payload_integrity_verified"] is False


def test_empty_bytes_payload_is_rejected_whatever_digest_is_supplied():
    assert _outcome(b"", CORRECT) == PAYLOAD_EMPTY


def test_digest_of_empty_bytes_is_a_placeholder_for_a_nonempty_payload():
    assert _outcome(PAYLOAD, EMPTY_DIGEST) == DIGEST_PLACEHOLDER


@pytest.mark.parametrize("token", ["TBD", "tbd", "TODO", "placeholder", "XXX", "none", "NULL",
                                   "changeme", "<sha256>", "<DIGEST>"])
def test_placeholder_words_are_placeholders_in_any_case(token):
    assert _outcome(PAYLOAD, token) == DIGEST_PLACEHOLDER


@pytest.mark.parametrize("filler", ["0" * 64, "a" * 64, "f" * 64])
def test_repeated_character_digest_is_a_placeholder(filler):
    assert _outcome(PAYLOAD, filler) == DIGEST_PLACEHOLDER


def test_correct_digest_verifies_payload_integrity_only():
    result = check_payload_digest(PAYLOAD, CORRECT)
    assert result["payload_integrity"] == PAYLOAD_INTEGRITY_VERIFIED
    assert result["payload_integrity_verified"] is True
    _assert_boundary(result)


@pytest.mark.parametrize("digest", [
    CORRECT[:-1],                 # 63 characters
    CORRECT + "0",                # 65 characters
    CORRECT.upper(),              # uppercase hex is not the canonical form
    " " + CORRECT,                # padded
    CORRECT + " ",
    "g" + CORRECT[1:],            # non-hex character
    "sha256:" + CORRECT,          # prefixed form
])
def test_malformed_digest_is_rejected_before_any_comparison(digest):
    assert _outcome(PAYLOAD, digest) == DIGEST_MALFORMED


@pytest.mark.parametrize("digest", [12345, b"\x00" * 32, ["abc"], {"sha256": CORRECT}])
def test_non_text_digest_is_malformed(digest):
    assert _outcome(PAYLOAD, digest) == DIGEST_MALFORMED


def test_well_formed_wrong_digest_is_a_mismatch():
    wrong = hashlib.sha256(b"different bytes").hexdigest()
    result = check_payload_digest(PAYLOAD, wrong)
    assert result["payload_integrity"] == PAYLOAD_DIGEST_MISMATCH
    assert result["payload_integrity_verified"] is False
    _assert_boundary(result)


def test_bytearray_payload_is_accepted_and_hashed_as_bytes():
    assert _outcome(bytearray(PAYLOAD), CORRECT) == PAYLOAD_INTEGRITY_VERIFIED


# ── boundary invariants ──────────────────────────────────────────────────────

@pytest.mark.parametrize("payload, digest", [
    (PAYLOAD, CORRECT),
    (PAYLOAD, None),
    (PAYLOAD, "TBD"),
    (PAYLOAD, "0" * 64),
    (b"", CORRECT),
    (None, None),
    (PAYLOAD, hashlib.sha256(b"x").hexdigest()),
])
def test_every_outcome_is_an_unregistered_draft_with_no_timestamp(payload, digest):
    _assert_boundary(check_payload_digest(payload, digest))


def test_verified_integrity_is_still_not_registration():
    result = check_payload_digest(PAYLOAD, CORRECT)
    assert result["payload_integrity_verified"] is True
    assert result["registration_status"] == "UNREGISTERED_DRAFT"
    assert result["external_timestamp_created"] is False


def test_recorded_digest_is_never_echoed_into_the_output():
    secret = "SECRETDIGESTVALUE" + "x" * 47
    rendered = json.dumps(check_payload_digest(PAYLOAD, secret), allow_nan=False)
    assert secret not in rendered


def test_digest_supplied_flag_distinguishes_absence_from_a_bad_value():
    assert check_payload_digest(PAYLOAD, None)["digest_supplied"] is False
    assert check_payload_digest(PAYLOAD, "")["digest_supplied"] is False
    assert check_payload_digest(PAYLOAD, "TBD")["digest_supplied"] is True


def test_hostile_digest_equality_is_never_called_and_is_structured():
    for digest, payload, expected in (
        (_EqualityRaises(), PAYLOAD, DIGEST_MALFORMED),
        (_EqualityRaises(), b"", PAYLOAD_EMPTY),
        (_StringEqualityRaises(CORRECT), PAYLOAD, DIGEST_MALFORMED),
    ):
        result = check_payload_digest(payload, digest)
        assert result["payload_integrity"] == expected
        assert result["digest_supplied"] is True
        _assert_boundary(result)
        json.dumps(result, allow_nan=False)
