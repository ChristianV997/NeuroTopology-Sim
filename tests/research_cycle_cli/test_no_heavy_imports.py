"""Safety requirements 4/5: no network access, no solver imports."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "tools" / "research_cycle_cli"
_CLI_MODULE = _REPO_ROOT / "scripts" / "inspect_research_cycle.py"

_FORBIDDEN_TOP_LEVEL_MODULES = {"mne", "scipy", "torch", "ripser", "gudhi", "boto3", "botocore", "sklearn", "socket", "urllib", "requests", "subprocess"}


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


def test_no_forbidden_network_or_solver_imports_anywhere_in_the_package():
    offenders: dict[str, set[str]] = {}
    for path in sorted(_PACKAGE_DIR.glob("*.py")) + [_CLI_MODULE]:
        found = _imported_top_level_modules(path) & _FORBIDDEN_TOP_LEVEL_MODULES
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, f"forbidden imports found: {offenders}"


def test_no_sql_write_statements_anywhere_in_the_package():
    """Requirement 1/2: read-only by default, no hidden writes -- the
    ledger reader must contain no SQL mutation verbs at all."""
    text = (_PACKAGE_DIR / "ledger_reader.py").read_text(encoding="utf-8").upper()
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE", "CREATE TABLE", "ALTER TABLE"):
        assert verb not in text, f"found forbidden SQL verb {verb!r} in ledger_reader.py"


def test_isolated_subprocess_execution_of_the_cli(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.inspect_research_cycle", "summary", "--now", "2026-01-01T00:00:00+00:00", "--format", "json"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert '"report_schema_version"' in result.stdout
