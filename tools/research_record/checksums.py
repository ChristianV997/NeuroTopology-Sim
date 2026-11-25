"""Local source-file checksums for record provenance.

A checksum computed here proves only that the compiler read these exact
bytes -- it is a *local* integrity check, never a substitute for a source
system's own independent verification (rule 6: "a checksum is not
independent validation").
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
