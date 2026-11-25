"""Deterministic checksums and stable id derivation. Stdlib-only."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def content_checksum(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def file_checksum(path: Path) -> str:
    """Real streaming sha256 over raw file bytes -- used to verify a
    local snapshot's declared checksum actually matches its content."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_well_formed_sha256(value: Optional[str]) -> bool:
    return bool(value) and bool(_SHA256_HEX_RE.match(value))


def stable_source_id(*, identifier: Optional[str], identifier_type: str, title: str) -> str:
    if identifier:
        basis = f"{identifier_type}:{normalize_text(identifier)}"
    else:
        basis = f"title:{normalize_text(title)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def stable_claim_id(*, source_id: str, claim_text: str) -> str:
    basis = f"{source_id}:{normalize_text(claim_text)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def stable_snapshot_id(*, source_id: str, kind: str, local_path: Optional[str]) -> str:
    basis = f"{source_id}:{kind}:{local_path or ''}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
