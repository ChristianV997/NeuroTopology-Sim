"""Operational references resolve to code by static inspection, and a checksum binds them to the current file."""
from __future__ import annotations

import hashlib
import os
import sys
import subprocess
from pathlib import Path

import pytest


def _codes(report):
    return {error["code"] for error in report["errors"]}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tmp_repo(tmp_path: Path, source: str, name: str = "pkg/mod.py") -> Path:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return tmp_path


_TMP_SOURCE = (
    "def helper(x):\n"
    "    return x\n"
    "\n"
    "def measure(phase):\n"
    "    return {'phase_grad': 0.5, 'metric_kind': 'analytic_phase_proxy'}\n"
    "\n"
    "def outer():\n"
    "    def inner():\n"
    "        return {'nested_key': 1}\n"
    "    return inner\n"
)


def _tmp_mapping(valid_mapping, source: str, *, module: str = "pkg/mod.py", symbol: str = "measure"):
    mapping = dict(valid_mapping)
    mapping["operational"] = {
        "feature_id": f"{symbol}.phase_grad",
        "feature_family": None,
        "family_note": "Synthetic fixture module for resolution tests.",
        "implementation": {
            "module": module,
            "symbol": symbol,
            "output_key": "phase_grad",
            "metric_kind_literal": "analytic_phase_proxy",
            "sha256": _sha(source),
        },
    }
    mapping["measurement"] = {**valid_mapping["measurement"], "preprocessing": ["helper"]}
    return mapping


def test_checksum_drift_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["sha256"] = "0" * 64
    report = check(valid_mapping)
    assert "IMPLEMENTATION_DRIFT" in _codes(report)
    assert report["implementation"]["sha256_matches"] is False
    assert report["implementation"]["symbol_found"] is True  # drift is reported alongside a static lookup


def test_checksum_matches_when_module_is_unchanged(valid_mapping, check):
    assert check(valid_mapping)["implementation"]["sha256_matches"] is True


def test_drift_detected_in_a_temporary_repository(valid_mapping, check, tmp_path):
    repo = _tmp_repo(tmp_path, _TMP_SOURCE)
    mapping = _tmp_mapping(valid_mapping, _TMP_SOURCE)
    assert check(mapping, repo_root=repo)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
    (repo / "pkg" / "mod.py").write_text(_TMP_SOURCE.replace("0.5", "0.6"), encoding="utf-8")
    assert "IMPLEMENTATION_DRIFT" in _codes(check(mapping, repo_root=repo))


def test_output_key_not_returned_by_the_function_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["output_key"] = "phase_grad_missing"
    valid_mapping["operational"]["feature_id"] = "channel_phase_gradient_metrics.phase_grad_missing"
    assert "OUTPUT_KEY_UNRESOLVED" in _codes(check(valid_mapping))


def test_metric_kind_not_produced_by_the_function_is_rejected(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["metric_kind_literal"] = "analytic_phase_proxy_v2"
    assert "METRIC_KIND_UNRESOLVED" in _codes(check(valid_mapping))


@pytest.mark.parametrize("module", ["../outside.py", "/etc/passwd", "validation/../../etc/passwd"])
def test_module_outside_the_repository_is_unresolved(valid_mapping, check, module):
    valid_mapping["operational"]["implementation"]["module"] = module
    report = check(valid_mapping)
    assert "IMPLEMENTATION_UNRESOLVED" in _codes(report)
    assert report["implementation"]["resolved"] is False


def test_missing_module_is_unresolved(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["module"] = "validation/does_not_exist.py"
    assert "IMPLEMENTATION_UNRESOLVED" in _codes(check(valid_mapping))


def test_symlink_escaping_the_repository_is_unresolved(valid_mapping, check, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text(_TMP_SOURCE, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    os.symlink(outside / "secret.py", repo / "linked.py")
    mapping = _tmp_mapping(valid_mapping, _TMP_SOURCE, module="linked.py")
    assert "IMPLEMENTATION_UNRESOLVED" in _codes(check(mapping, repo_root=repo))


def test_nested_definition_is_not_a_module_level_symbol(valid_mapping, check, tmp_path):
    repo = _tmp_repo(tmp_path, _TMP_SOURCE)
    mapping = _tmp_mapping(valid_mapping, _TMP_SOURCE, symbol="inner")
    assert "SYMBOL_UNRESOLVED" in _codes(check(mapping, repo_root=repo))


def test_unparseable_module_is_reported_without_crashing(valid_mapping, check, tmp_path):
    broken = "def measure(:\n"
    repo = _tmp_repo(tmp_path, broken)
    mapping = _tmp_mapping(valid_mapping, broken)
    report = check(mapping, repo_root=repo)
    assert "IMPLEMENTATION_UNPARSEABLE" in _codes(report)


def test_preprocessing_step_must_resolve_in_the_same_module(valid_mapping, check, tmp_path):
    repo = _tmp_repo(tmp_path, _TMP_SOURCE)
    mapping = _tmp_mapping(valid_mapping, _TMP_SOURCE)
    mapping["measurement"]["preprocessing"] = ["helper", "no_such_step"]
    report = check(mapping, repo_root=repo)
    unresolved = [error for error in report["errors"] if error["code"] == "PREPROCESSING_UNRESOLVED"]
    assert [error["path"] for error in unresolved] == ["$.measurement.preprocessing[1]"]


def test_validation_does_not_import_or_execute_the_scientific_module(tmp_path):
    script = (
        "import json, sys\n"
        "from datetime import date\n"
        "from pathlib import Path\n"
        "from shared.measurement_hypothesis import validate_mapping, load_mapping\n"
        "fixture = Path('tests/measurement_hypothesis/fixtures/valid_hypothetical_mapping.json')\n"
        "report = validate_mapping(load_mapping(fixture), repo_root=Path('.'), as_of=date(2026, 10, 16))\n"
        "assert report['contract_status'] == 'VALID_HYPOTHESIS_MAPPING'\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in {'scipy', 'numpy', 'sklearn', 'mne'}\n"
        "               or m == 'validation.analytic_phase')\n"
        "print(json.dumps(heavy))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines()[-1] == "[]"
