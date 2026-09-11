"""Compile/syntax checks for owned Python and git diff --check on owned paths."""

from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

from tests.ops.research_cycle.conftest import OWNED_PATHS, PACK, REPO_ROOT


def _owned_python_files() -> list[Path]:
    files: list[Path] = []
    for path in PACK.rglob("*.py"):
        files.append(path)
    for path in (REPO_ROOT / "tests" / "ops" / "research_cycle").rglob("*.py"):
        files.append(path)
    return sorted(files)


def test_owned_python_compiles():
    errors: list[str] = []
    for path in _owned_python_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(str(exc))
    assert errors == []


def test_governance_validate_available_or_documented(tmp_path):
    # Invoke existing governance CLI; do not invent a replacement.
    completed = subprocess.run(
        [sys.executable, "-m", "governance.validate"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 and "No module named" in (completed.stderr + completed.stdout):
        # Pack catalog will mark schema_validation NOT_AVAILABLE rather than PASS.
        assert "governance" in completed.stderr or "governance" in completed.stdout
        return
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_git_diff_check_on_owned_paths():
    rels = [
        "ops/research_cycle",
        "scripts/run_research_cycle_audit.sh",
        "scripts/run_research_cycle_audit.ps1",
        "tests/ops/research_cycle",
        "docs/ops/research_cycle_operator_pack.md",
    ]
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--check", "--", *rels],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    for path in OWNED_PATHS:
        assert path.exists(), path
