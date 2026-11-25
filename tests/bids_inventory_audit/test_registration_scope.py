"""Every output states that no external registration was verified and that no payload was read."""
from __future__ import annotations

import hashlib
import json

from shared.bids_inventory_audit import audit_inventory, check_payload_digest, file_listing_digest

ABSENT = {"status": "ABSENT", "verified": False}
PAYLOAD = b"synthetic-payload"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def test_checksum_result_states_absent_registration_and_no_payload_access():
    result = check_payload_digest(PAYLOAD, DIGEST)
    assert result["external_registration"] == ABSENT
    assert result["payload_access"] == "NONE"
    assert result["external_timestamp_created"] is False
    assert result["preregistration_claim"] is False


def test_a_verified_digest_still_reports_no_registration():
    result = check_payload_digest(PAYLOAD, DIGEST)
    assert result["payload_integrity"] == "PAYLOAD_INTEGRITY_VERIFIED"
    assert result["payload_integrity_verified"] is True
    assert result["external_registration"] == ABSENT
    assert result["registration_status"] == "UNREGISTERED_DRAFT"


def test_listing_digest_states_absent_registration_and_no_payload_access():
    result = file_listing_digest([("sub-01/eeg/sub-01_task-rest_eeg.edf", PAYLOAD)])
    assert result["manifest_sha256"] is not None
    assert result["external_registration"] == ABSENT
    assert result["payload_access"] == "NONE"


def test_inventory_states_absent_registration_and_no_payload_access(synthetic_tsv, synthetic_listing):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing)
    assert report["external_registration"] == ABSENT
    assert report["payload_access"] == "NONE"
    assert report["registration_status"] == "UNREGISTERED_DRAFT"


def test_registration_block_is_a_fresh_object_on_every_call():
    first = check_payload_digest(PAYLOAD, DIGEST)
    first["external_registration"]["verified"] = True
    second = check_payload_digest(PAYLOAD, DIGEST)
    assert second["external_registration"] == ABSENT


def test_no_output_ever_reports_a_verified_registration(synthetic_tsv, synthetic_listing, synthetic_readme,
                                                        synthetic_nemar, synthetic_analysis_record):
    rendered = [
        json.dumps(check_payload_digest(PAYLOAD, DIGEST), allow_nan=False, sort_keys=True),
        json.dumps(check_payload_digest(PAYLOAD, None), allow_nan=False, sort_keys=True),
        json.dumps(file_listing_digest([("a.json", PAYLOAD)]), allow_nan=False, sort_keys=True),
        json.dumps(audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                                   readme_text=synthetic_readme, nemar_metadata=synthetic_nemar,
                                   analysis_record=synthetic_analysis_record), allow_nan=False, sort_keys=True),
    ]
    for text in rendered:
        assert '"verified": true' not in text
        assert '"external_timestamp_created": true' not in text
        assert '"preregistration_claim": true' not in text
        assert '"payload_access": "NONE"' in text
        assert '"external_registration": {"status": "ABSENT", "verified": false}' in text


def test_empty_payload_is_rejected_in_the_listing_digest_and_no_digest_is_quoted():
    result = file_listing_digest([("sub-01/eeg/sub-01_task-rest_eeg.edf", b"")])
    assert result["manifest_sha256"] is None
    assert result["external_registration"] == ABSENT
    assert any(f["code"] == "PAYLOAD_EMPTY" for f in result["findings"])
