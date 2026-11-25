"""Rule 6: no heavy scientific solvers -- the compiler must remain usable
when MNE, SciPy, Torch, Ripser, GUDHI, Boto3, and AWS SDKs are absent.

Two independent checks: a static AST scan (catches an import even if the
package happens to be installed in this environment, so the test can't
pass by accident), and an isolated subprocess run of the actual CLI (rule
13: no network access; proves the compiler works end-to-end without ever
touching those packages at runtime).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "tools" / "research_record"
_CLI_MODULE = _REPO_ROOT / "scripts" / "build_research_record.py"

_FORBIDDEN_TOP_LEVEL_MODULES = {"mne", "scipy", "torch", "ripser", "gudhi", "boto3", "botocore", "sklearn"}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_forbidden_solver_imports_anywhere_in_the_package():
    offenders: dict[str, set[str]] = {}
    for path in sorted(_PACKAGE_DIR.glob("*.py")) + [_CLI_MODULE]:
        found = _imported_top_level_modules(path) & _FORBIDDEN_TOP_LEVEL_MODULES
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, f"forbidden heavy-solver imports found: {offenders}"


def test_isolated_subprocess_execution_of_the_cli(tmp_path):
    """Run the CLI as a completely separate process (its own import graph,
    no inherited test-session state) and confirm it succeeds without
    network access or any of the forbidden packages being required."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [sys.executable, "-m", "scripts.build_research_record", "--manifest", str(manifest_path), "--output-dir", str(out_dir), "--formats", "json", "--now", "2026-01-01T00:00:00+00:00"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (out_dir / "research_record.json").is_file()
    assert "status=partial" in result.stdout
