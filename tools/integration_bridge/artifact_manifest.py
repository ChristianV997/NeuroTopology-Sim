"""Deterministic artifact manifest generation.

The manifest is a flat, sorted, content-addressed index of every artifact
the ``package`` stage writes. "Deterministic" means: given the same set of
artifact bytes and the same declared metadata, two separate invocations
produce byte-identical manifest JSON (verified by
tests/integration/test_deterministic_manifest.py) -- no wall-clock
timestamp or filesystem-iteration-order dependency is allowed to leak in.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ArtifactManifest:
    schema: str
    run_id: str
    entries: tuple[ManifestEntry, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "metadata": dict(sorted(self.metadata.items())),
            "artifacts": [
                {
                    "relative_path": entry.relative_path,
                    "sha256": entry.sha256,
                    "size_bytes": entry.size_bytes,
                }
                # Sorted by path so file-creation order never affects the
                # serialized manifest.
                for entry in sorted(self.entries, key=lambda e: e.relative_path)
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(
    *,
    run_id: str,
    output_dir: Path,
    artifact_relative_paths: List[str],
    metadata: Dict[str, Any],
    schema: str = "NTS.IntegrationArtifactManifest.v1",
) -> ArtifactManifest:
    """Hash every artifact under ``output_dir`` named in
    ``artifact_relative_paths`` (explicit list, never a directory walk --
    a walk's order and set of entries can vary with the filesystem, an
    explicit list cannot) and return a deterministic manifest."""
    entries: List[ManifestEntry] = []
    for relative_path in artifact_relative_paths:
        full_path = output_dir / relative_path
        data = full_path.read_bytes()
        entries.append(
            ManifestEntry(
                relative_path=relative_path,
                sha256=_sha256_bytes(data),
                size_bytes=len(data),
            )
        )
    return ArtifactManifest(
        schema=schema,
        run_id=run_id,
        entries=tuple(entries),
        metadata=metadata,
    )


def write_manifest(manifest: ArtifactManifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json() + "\n", encoding="utf-8")
    return path
