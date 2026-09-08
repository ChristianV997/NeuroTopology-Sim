"""Local source-file checksums for report provenance.

A checksum computed here proves only that the compiler read these exact
bytes -- it is a *local* integrity check, never a substitute for the
source system's own independent verification (see the
"local checksum versus independent validation" distinction in
docs/reporting/mobile_report_contract.md).
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
