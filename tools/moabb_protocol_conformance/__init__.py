"""Offline MOABB metadata → benchmark-protocol manifest conformance.

Consumes already-available MOABB candidate metadata or local fixtures.
Never downloads datasets, never imports/runs moabb/mne, never claims a
benchmark executed or that a protocol is scientifically validated.
"""
from __future__ import annotations

from tools.moabb_protocol_conformance.schema import (
    EVIDENCE_CLASS,
    PROTOCOL_SCHEMA_VERSION,
    ConformanceStatus,
)
from tools.moabb_protocol_conformance.manifest import (
    ProtocolManifestV1,
    build_protocol_manifest,
)
from tools.moabb_protocol_conformance.validation import validate_protocol_manifest

__all__ = [
    "EVIDENCE_CLASS",
    "PROTOCOL_SCHEMA_VERSION",
    "ConformanceStatus",
    "ProtocolManifestV1",
    "build_protocol_manifest",
    "validate_protocol_manifest",
]
