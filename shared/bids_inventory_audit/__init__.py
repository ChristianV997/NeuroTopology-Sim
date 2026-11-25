"""Synthetic-only BIDS inventory audit and checksum boundary.

Everything here works on text, bytes, and mappings that the caller supplies. No function
opens a file or makes a network call. The inventory reports structure and gaps. It never
identifies an analyzed cohort, never resolves a license conflict, and never treats a digest
as a registration. The result is always HOLD and SYNTHETIC_ONLY.
"""

from .checksum import check_payload_digest
from .inventory import audit_inventory
from .license import license_report, metadata_evidence, readme_evidence, reconcile_license
from .manifest import file_listing_digest
from .paths import ParsedPath, parse_bids_relpath, unsafe_reason
from .schema import COHORT_IDENTITY, REGISTRATION_STATUS, SCHEMA, SCOPE, STATUS
from .tsv import TsvResult, parse_participants_tsv

__all__ = [
    "COHORT_IDENTITY",
    "ParsedPath",
    "REGISTRATION_STATUS",
    "SCHEMA",
    "SCOPE",
    "STATUS",
    "TsvResult",
    "audit_inventory",
    "check_payload_digest",
    "file_listing_digest",
    "license_report",
    "metadata_evidence",
    "parse_bids_relpath",
    "parse_participants_tsv",
    "readme_evidence",
    "reconcile_license",
    "unsafe_reason",
]
