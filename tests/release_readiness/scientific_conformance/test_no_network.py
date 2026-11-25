"""No-network checks: this suite's own code makes no network calls, and
the "full-dataset download" / "network-policy violation" fixtures prove
the claim gate itself never performs the network access it is asked
about -- it only ever *reports* that the request was declined.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from tools.research_claim_gate.gate import evaluate_claim

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUITE_DIR = Path(__file__).resolve().parent
_FORBIDDEN_MODULES = {"socket", "urllib", "requests", "http", "ftplib", "boto3", "botocore"}


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


def test_conformance_suite_makes_no_network_imports():
    offenders = {}
    for path in sorted(_SUITE_DIR.glob("*.py")):
        found = _imported_top_level_modules(path) & _FORBIDDEN_MODULES
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, f"forbidden network imports found: {offenders}"


def test_validation_script_makes_no_network_imports():
    script = _REPO_ROOT / "scripts" / "validate_scientific_release_conformance.py"
    found = _imported_top_level_modules(script) & _FORBIDDEN_MODULES
    assert found == set(), f"forbidden network imports found in {script}: {found}"


def test_network_access_request_is_declined_not_performed(load_fixture):
    raw = load_fixture("full_dataset_download_request")
    result = evaluate_claim(raw)

    assert result.network_access_performed is False
    assert "NETWORK_ACCESS_NOT_APPROVED" in result.reason_codes
    assert result.decision == "CLAIM_REJECTED"


def test_isolated_subprocess_execution_of_the_validation_script(tmp_path):
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_scientific_release_conformance", "--output-dir", str(out_dir), "--now", "2026-01-01T00:00:00+00:00"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (out_dir / "scientific_release_conformance_report.json").is_file()
