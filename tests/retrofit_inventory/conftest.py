"""Shared builders for retrofit inventory validator tests (offline only)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from tools.retrofit_inventory.models import (
    ARTIFACT_LABEL_SYNTHETIC,
    HASH_POLICY_CONTENT_SHA256,
    KIND_TEXT,
    ArtifactInventoryEntry,
    FileInventoryEntry,
    InventorySnapshot,
    OverlapOrDuplicateFinding,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _hex32(seed: str) -> str:
    return ("ab" * 16) if seed == "default" else (seed.encode("ascii").hex() + "0" * 32)[:32]


def make_file_entry(
    path: str = "src/app.py",
    *,
    kind: str = KIND_TEXT,
    size: int = 12,
    content_hash: Optional[str] = None,
    hash_policy: str = HASH_POLICY_CONTENT_SHA256,
    mtime: Optional[float] = None,
) -> FileInventoryEntry:
    return FileInventoryEntry(
        path=path,
        kind=kind,
        size=size,
        content_hash=content_hash or _hex32(path),
        mtime=mtime,
        hash_policy=hash_policy,
    )


def make_artifact(
    path: str = "artifacts/synthetic/summary.json",
    *,
    label: str = ARTIFACT_LABEL_SYNTHETIC,
    schema_id: Optional[str] = "run_record.v1",
    size: int = 4,
) -> ArtifactInventoryEntry:
    return ArtifactInventoryEntry(
        path=path,
        label=label,
        schema_id=schema_id,
        size=size,
    )


def make_snapshot(
    *,
    repo_root: str = "/tmp/fixture-repo",
    commit_sha: str = "a" * 40,
    files: Optional[List[FileInventoryEntry]] = None,
    artifacts: Optional[List[ArtifactInventoryEntry]] = None,
    overlaps: Optional[List[OverlapOrDuplicateFinding]] = None,
    report_fields: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> InventorySnapshot:
    return InventorySnapshot(
        repo_root=repo_root,
        commit_sha=commit_sha,
        files=files if files is not None else [make_file_entry()],
        artifacts=artifacts if artifacts is not None else [make_artifact()],
        overlaps=overlaps if overlaps is not None else [],
        report_fields=report_fields if report_fields is not None else {},
        **kwargs,
    )


def init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "retrofit-qa@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Retrofit QA"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def copy_tiny_repo(tmp_path: Path) -> Path:
    src = FIXTURES / "repo_tiny"
    dest = tmp_path / "tiny"
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        if rel.parts and rel.parts[0] == "artifacts":
            # Root .gitignore drops any `artifacts/` path; assemble at runtime.
            continue
        if rel.as_posix() == "synthetic_summary.json":
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    artifact = dest / "artifacts" / "synthetic" / "summary.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes((src / "synthetic_summary.json").read_bytes())
    init_git_repo(dest)
    return dest


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    return copy_tiny_repo(tmp_path)
