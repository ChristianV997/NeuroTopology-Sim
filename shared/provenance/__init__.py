"""Local-first dataset provenance contract."""

from shared.provenance.contract import (
    ATTACHMENT_KEY,
    SCHEMA,
    VALIDATOR_VERSION,
    ProvenanceError,
    ProvenanceRecord,
    attach_provenance,
    consumer_view,
    serialize_record,
    sha256_file,
    validate_declaration,
    write_sidecar,
)

__all__ = [
    "ATTACHMENT_KEY",
    "SCHEMA",
    "VALIDATOR_VERSION",
    "ProvenanceError",
    "ProvenanceRecord",
    "attach_provenance",
    "consumer_view",
    "serialize_record",
    "sha256_file",
    "validate_declaration",
    "write_sidecar",
]
