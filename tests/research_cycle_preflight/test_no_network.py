"""No-network checks: this suite's own code and the preflight package
make no network calls, and the network-violation fixture proves the
preflight only ever *classifies* a requested network/download policy
violation -- it never performs the access it is classifying.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _REPO_ROOT / "tools" / "research_cycle_preflight"
_SCRIPT = _REPO_ROOT / "scripts" / "validate_research_cycle_preflight.py"
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


def test_preflight_package_makes_no_network_imports():
    offenders = {}
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        found = _imported_top_level_modules(path) & _FORBIDDEN_MODULES
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, f"forbidden network imports found: {offenders}"


def test_suite_makes_no_network_imports():
    offenders = {}
    for path in sorted(_SUITE_DIR.glob("*.py")):
        found = _imported_top_level_modules(path) & _FORBIDDEN_MODULES
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert offenders == {}, f"forbidden network imports found: {offenders}"


def test_validation_script_makes_no_network_imports():
    found = _imported_top_level_modules(_SCRIPT) & _FORBIDDEN_MODULES
    assert found == set(), f"forbidden network imports found in {_SCRIPT}: {found}"


def test_network_violation_is_classified_not_performed(load_request):
    from tools.research_cycle_preflight.compose import run_preflight

    result = run_preflight(load_request("network_violation"), now="2026-01-01T00:00:00+00:00")
    data_access = result["validators_composed"]["data_access_policy"]
    assert data_access["status"] == "BLOCKED"
    assert "FULL_DATASET_DOWNLOAD_REJECTED" in data_access["violations"]
    # the classification is purely declarative -- there is no network
    # field anywhere in the output claiming a transfer actually happened
    assert "network_calls_performed" not in data_access


def test_isolated_subprocess_execution_of_the_validation_script(tmp_path):
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_research_cycle_preflight", "--output-dir", str(out_dir), "--now", "2026-01-01T00:00:00+00:00"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (out_dir / "research_cycle_preflight_self_check.json").is_file()


def test_isolated_subprocess_execution_against_a_single_request(tmp_path):
    import json

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"plan": {"plan_id": "x"}}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.validate_research_cycle_preflight",
            "--output-dir", str(out_dir), "--now", "2026-01-01T00:00:00+00:00",
            "--request", str(request_path),
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    # an incomplete plan must fail closed with a non-zero exit code, not
    # crash and not silently succeed
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (out_dir / "research_cycle_preflight_report.json").is_file()

