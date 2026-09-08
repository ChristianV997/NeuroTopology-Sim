"""Tests for the Windows-focused isolated-runner acceptance harness.

These validate the harness logic and its portable contracts. Windows-specific
runner behavior is NOT asserted here on non-Windows hosts (it is classified as
``unsupported``). Synthetic fixtures only; no network; finite JSON.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import pytest

from tools.runner_acceptance import harness as H
from tools.runner_acceptance.harness import (
    Outcome,
    PlatformStatus,
    build_powershell_command,
    detect_capability,
    execute,
    ps_single_quote,
    run_acceptance,
)

# Load the CLI script by path (scripts/ is not a package).
_SPEC = importlib.util.spec_from_file_location(
    "run_windows_runner_acceptance",
    Path(__file__).resolve().parents[2] / "scripts" / "run_windows_runner_acceptance.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)

_POSIX = os.name != "nt"


def _assert_finite(obj):
    if isinstance(obj, float):
        assert math.isfinite(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _assert_finite(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_finite(v)


# --------------------------------------------------------------------------- #
# Capability detection
# --------------------------------------------------------------------------- #
def test_windows_capability_detection(monkeypatch):
    monkeypatch.setattr(H, "_IS_WINDOWS", True)
    cap = detect_capability()
    assert cap.is_windows is True
    assert cap.platform_status == PlatformStatus.SUPPORTED


def test_posix_unsupported_classification():
    cap = detect_capability()
    if _POSIX:
        assert cap.is_windows is False
        assert cap.platform_status == PlatformStatus.UNSUPPORTED
    else:  # pragma: no cover - only on Windows
        assert cap.platform_status == PlatformStatus.SUPPORTED


@pytest.mark.skipif(not _POSIX, reason="checks the non-Windows unsupported path")
def test_windows_cases_unsupported_never_pass_on_posix():
    report = run_acceptance(timeout_s=2)
    assert report["platform_status"] == "unsupported"
    assert report["windows_behavior_validated"] is False
    win = [r for r in report["results"] if r["category"] == "windows_runner"]
    assert win, "expected windows_runner cases"
    for r in win:
        assert r["outcome"] == "unsupported"
        assert r["outcome"] != "pass"


# --------------------------------------------------------------------------- #
# Command quoting / construction
# --------------------------------------------------------------------------- #
def test_ps_single_quote_escapes():
    assert ps_single_quote("plain") == "'plain'"
    assert ps_single_quote("o'brien") == "'o''brien'"
    assert ps_single_quote("C:\\a b\\tëst") == "'C:\\a b\\tëst'"


def test_powershell_command_construction():
    argv = [sys.executable, "C:\\tmp\\test x.py", "--timeout-s", "30"]
    ps = build_powershell_command(argv)
    assert ps[0] == "powershell"
    assert "-NoProfile" in ps and "-NonInteractive" in ps and "-Command" in ps
    assert ps[-1].startswith("& ")
    assert ps_single_quote("C:\\tmp\\test x.py") in ps[-1]
    assert all(isinstance(part, str) for part in ps)
    with pytest.raises(ValueError):
        build_powershell_command([])


def test_command_quoting_case_passes():
    cap = detect_capability()
    rec = H.case_path_quoting(cap)
    assert rec.outcome == Outcome.PASS
    assert "''" in rec.details["quoted"]


# --------------------------------------------------------------------------- #
# Executor contracts: timeout + flood (portable)
# --------------------------------------------------------------------------- #
def test_timeout_classification():
    result = execute([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1)
    assert result.timed_out is True
    assert result.exit_code != 0
    assert result.elapsed_s < 20


def test_executor_success_not_timed_out():
    result = execute([sys.executable, "-c", "print('ok')"], timeout_s=30)
    assert result.timed_out is False
    assert result.exit_code == 0
    assert "ok" in result.stdout


def test_output_flood_no_deadlock():
    payload = 5 * 1024 * 1024
    result = execute(
        [sys.executable, "-c", f"import sys; sys.stdout.write('x'*{payload}); sys.stdout.flush()"],
        timeout_s=60,
    )
    assert result.timed_out is False
    assert result.exit_code == 0
    assert result.stdout_total_bytes >= payload


def test_rejects_nonpositive_timeout():
    with pytest.raises(ValueError):
        execute([sys.executable, "-c", "pass"], timeout_s=0)


# --------------------------------------------------------------------------- #
# No-network operation
# --------------------------------------------------------------------------- #
def test_no_network_operation():
    # The harness must complete fully offline. The repo conftest network guard is
    # active in this test process; run the whole portable suite and confirm it
    # produces a report without raising a network error.
    report = run_acceptance(timeout_s=2)
    assert report["ran_ok"] is True
    # No result should reference a network dependency.
    for r in report["results"]:
        assert "network" not in json.dumps(r).lower()


# --------------------------------------------------------------------------- #
# Finite JSON + deterministic structure
# --------------------------------------------------------------------------- #
def test_report_is_finite_json():
    report = run_acceptance(timeout_s=2)
    text = json.dumps(report, allow_nan=False)  # raises on NaN/Inf
    assert "NaN" not in text and "Infinity" not in text
    _assert_finite(json.loads(text))


def test_deterministic_report_structure():
    a = run_acceptance(timeout_s=2)
    b = run_acceptance(timeout_s=2)
    # Same set of case names and categories in the same order (structure stable).
    names_a = [(r["test_case"], r["category"], r["outcome"]) for r in a["results"]]
    names_b = [(r["test_case"], r["category"], r["outcome"]) for r in b["results"]]
    assert names_a == names_b
    assert set(a.keys()) == set(b.keys())
    assert a["schema"] == b["schema"] == "runner_acceptance/v1"


def test_required_record_fields_present():
    report = run_acceptance(timeout_s=2)
    required = {
        "test_case", "platform", "python_version", "runner_version", "capability_state",
        "expected_outcome", "observed_outcome", "timeout_state", "orphan_state",
        "cleanup_state", "evidence_class", "synthetic",
    }
    for r in report["results"]:
        assert required.issubset(r.keys())
        assert r["evidence_class"] == "acceptance_synthetic"
        assert r["synthetic"] is True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_json_smoke(capsys):
    rc = cli.main(["--json", "--timeout-s", "2", "--no-portable-runner"])
    out = capsys.readouterr().out
    assert "NaN" not in out and "Infinity" not in out
    report = json.loads(out)
    assert report["schema"] == "runner_acceptance/v1"
    # On POSIX, unsupported cases are neutral -> run succeeds (exit 0).
    if _POSIX:
        assert rc == 0
        assert report["platform_status"] == "unsupported"


def test_cli_writes_output_file(tmp_path, capsys):
    out = tmp_path / "acc.json"
    rc = cli.main(["--output", str(out), "--timeout-s", "2", "--no-portable-runner"])
    capsys.readouterr()
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "results" in data and data["num_cases"] >= 1
    assert rc in (0, 1)
