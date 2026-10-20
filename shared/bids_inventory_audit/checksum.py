"""Payload checksum check, kept separate from registration status.

A matching digest shows only that these payload bytes equal the recorded digest. It creates
no external timestamp, and it is not a preregistration. Every result carries
``registration_status: UNREGISTERED_DRAFT``. The recorded digest is never echoed into the
output, so untrusted text cannot leave through this path.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .schema import (
    EMPTY_BYTES_SHA256,
    HEX64_RE,
    PAYLOAD_ACCESS,
    PLACEHOLDER_TOKENS,
    REGISTRATION_STATUS,
    SCHEMA,
    external_registration_block,
)

PAYLOAD_INTEGRITY_VERIFIED = "PAYLOAD_INTEGRITY_VERIFIED"
PAYLOAD_DIGEST_MISMATCH = "PAYLOAD_DIGEST_MISMATCH"
PAYLOAD_MISSING = "PAYLOAD_MISSING"
PAYLOAD_EMPTY = "PAYLOAD_EMPTY"
DIGEST_MISSING = "DIGEST_MISSING"
DIGEST_PLACEHOLDER = "DIGEST_PLACEHOLDER"
DIGEST_MALFORMED = "DIGEST_MALFORMED"

STATEMENT = (
    "payload_integrity states whether the payload bytes equal the recorded digest, and nothing more. "
    "registration_status is UNREGISTERED_DRAFT: no external timestamp or registration exists, "
    "so this result is not preregistration."
)


def _outcome(payload: Any, digest: Any) -> str:
    if not isinstance(payload, (bytes, bytearray)):
        return PAYLOAD_MISSING
    if len(payload) == 0:
        return PAYLOAD_EMPTY  # empty bytes are never a valid analysis plan, whatever digest is supplied
    if digest is None or digest == "":
        return DIGEST_MISSING
    if not isinstance(digest, str):
        return DIGEST_MALFORMED
    if digest.lower() in PLACEHOLDER_TOKENS or digest == EMPTY_BYTES_SHA256:
        return DIGEST_PLACEHOLDER
    if len(digest) == 64 and len(set(digest)) == 1:
        return DIGEST_PLACEHOLDER  # a repeated character is a filler value, not a hash
    if not HEX64_RE.fullmatch(digest):
        return DIGEST_MALFORMED  # must be exactly 64 lowercase hex characters
    if hashlib.sha256(bytes(payload)).hexdigest() == digest:
        return PAYLOAD_INTEGRITY_VERIFIED
    return PAYLOAD_DIGEST_MISMATCH


def check_payload_digest(payload: Any, digest: Any) -> dict[str, Any]:
    outcome = _outcome(payload, digest)
    return {
        "schema": SCHEMA,
        "check": "payload_checksum",
        "digest_supplied": digest is not None and digest != "",
        "payload_integrity": outcome,
        "payload_integrity_verified": outcome == PAYLOAD_INTEGRITY_VERIFIED,
        "registration_status": REGISTRATION_STATUS,
        "external_registration": external_registration_block(),
        "external_timestamp_created": False,
        "preregistration_claim": False,
        "payload_access": PAYLOAD_ACCESS,
        "statement": STATEMENT,
    }
