"""Local source-file checksums for research-cycle report provenance.

A checksum computed here proves only that the orchestrator read these
exact bytes -- it is a local integrity check, never independent
verification of the underlying claim, dataset, or execution it describes.
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
