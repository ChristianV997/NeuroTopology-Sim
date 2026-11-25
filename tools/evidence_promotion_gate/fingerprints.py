"""SHA-256 fingerprints of local promotion-gate inputs. No network I/O."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fingerprint_files(paths: Iterable[Path], *, root: Path | None = None) -> dict[str, Any]:
    files: dict[str, str] = {}
    digest = hashlib.sha256()
    ordered = sorted(Path(path) for path in paths)
    for path in ordered:
        checksum = sha256_file(path)
        rel = str(path.relative_to(root)) if root is not None else path.name
        files[rel] = checksum
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(checksum.encode("ascii"))
        digest.update(b"\0")
    return {
        "algorithm": "sha256",
        "files": files,
        "combined": digest.hexdigest() if files else None,
    }
