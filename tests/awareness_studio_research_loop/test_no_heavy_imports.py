"""No heavy scientific solvers: the orchestrator must remain usable when
MNE, SciPy, Torch, Ripser, GUDHI, Boto3, and AWS SDKs are absent -- and
must never itself execute anything it reads (no `exec`/`eval`/dynamic
import of module names found in input data).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "tools" / "awareness_studio_research_loop"
_CLI_MODULE = _REPO_ROOT / "scripts" / "run_awareness_research_cycle.py"

_FORBIDDEN_TOP_LEVEL_MODULES = {"mne", "scipy", "torch", "ripser", "gudhi", "boto3", "botocore", "sklearn", "subprocess", "socket"}


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


def _uses_dynamic_execution(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval", "compile", "__import__"):
            return True
    return False


def test_no_forbidden_solver_or_execution_imports_anywhere_in_the_package():
    offenders: dict[str, set[str]] = {}
    for path in sorted(_PACKAGE_DIR.glob("*.py")) + [_CLI_MODULE]:
        found = _imported_top_level_modules(path) & _FORBIDDEN_TOP_LEVEL_MODULES
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, f"forbidden imports found: {offenders}"


def test_no_dynamic_code_execution_anywhere_in_the_package():
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in sorted(_PACKAGE_DIR.glob("*.py")) + [_CLI_MODULE]
        if _uses_dynamic_execution(path)
    ]
    assert offenders == [], f"dynamic code execution found in: {offenders}"


def test_isolated_subprocess_execution_of_the_cli(tmp_path):
    """No-network execution: run the CLI as a completely separate
    process and confirm it succeeds without network access or any of the
    forbidden packages being required."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"literature_evidence": null, "hypothesis_registry": null, "experiment_plans": null, '
        '"execution_results": null, "null_surrogate_results": null, "validation_reports": null, '
        '"reviewer_decisions": null, "theory_state": null, "cycle_config": null}',
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_awareness_research_cycle", "--manifest", str(manifest_path), "--output-dir", str(out_dir), "--formats", "json,markdown", "--now", "2026-01-01T00:00:00+00:00"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (out_dir / "research_cycle_report.json").is_file()
    assert (out_dir / "paper_draft.md").is_file()
    assert "status=partial" in result.stdout
