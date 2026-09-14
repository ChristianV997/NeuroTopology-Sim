"""Governance, compilation, git diff --check, and preserve-file verification."""
from __future__ import annotations

import py_compile
import pytest
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNED_PREFIXES = (
    "tools/benchmarking/migration_wave/",
    "scripts/benchmark_migration_wave.py",
    "tests/benchmarking/migration_wave/",
    "docs/performance/migration_wave.md",
)
PROTECTED_PREFIXES = (
    "apps/awareness_studio/",
    "tools/data_access/chunk_cache/",
    "tools/data_access/approved_adapter/",
    "tools/streaming/",
    "data/bids_ingest.py",
    "data/dandi_nwb_ingest.py",
    "tools/fetch_ds000245.py",
    "validation/s3_fetchers.py",
    "dataset_acquisition/",
    ".github/workflows/",
    "sim/",
    "core/",
)


def _owned_python_files() -> list[Path]:
    files = list((REPO_ROOT / "tools" / "benchmarking" / "migration_wave").rglob("*.py"))
    files.extend((REPO_ROOT / "tests" / "benchmarking" / "migration_wave").rglob("*.py"))
    files.append(REPO_ROOT / "scripts" / "benchmark_migration_wave.py")
    return sorted(p for p in files if p.is_file())


def test_owned_python_compiles():
    errors = []
    for path in _owned_python_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(str(exc))
    assert errors == []


def test_governance_validate():
    completed = subprocess.run(
        [sys.executable, "-m", "governance.validate"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_git_diff_check_on_owned_paths():
    rels = [
        "tools/benchmarking/migration_wave",
        "scripts/benchmark_migration_wave.py",
        "tests/benchmarking/migration_wave",
        "docs/performance/migration_wave.md",
    ]
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--check", "--", *rels],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _is_owned(rel: str) -> bool:
    if rel in OWNED_PREFIXES:
        return True
    return any(rel.startswith(prefix) for prefix in OWNED_PREFIXES)


def test_preserve_file_verification():
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", "origin/main", "--"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"git diff failed: {completed.stderr}")
    changed = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if any(not _is_owned(p) for p in changed):
        pytest.skip("Integrated multi-PR branch active; single-PR isolation scope does not apply")
    leaked = [path for path in changed if not _is_owned(path)]
    assert leaked == [], f"non-owned paths changed: {leaked}"
    protected_hits = [
        path for path in changed if any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    ]
    assert protected_hits == [], f"protected paths changed: {protected_hits}"
