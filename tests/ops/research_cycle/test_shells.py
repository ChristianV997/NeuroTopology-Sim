"""POSIX and PowerShell wrapper smoke tests."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
import pytest

from ops.research_cycle.exit_codes import BLOCKED, NOT_AVAILABLE, PASS, INCOMPLETE

from tests.ops.research_cycle.conftest import POSIX_SH, POWERSHELL, REPO_ROOT


def test_posix_script_is_not_powershell():
    text = POSIX_SH.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "This is not a PowerShell script" in text
    assert "ops.research_cycle" in text
    assert "--output-dir" in text


def test_powershell_script_is_not_posix():
    text = POWERSHELL.read_text(encoding="utf-8")
    assert "Windows PowerShell" in text
    assert "This is not a POSIX shell script" in text
    assert "ops.research_cycle" in text
    assert "-OutputDir" in text
    assert text.strip().startswith("#") or "CmdletBinding" in text
    assert not text.startswith("#!/usr/bin/env bash")


@pytest.mark.skipif(os.name == "nt", reason="POSIX wrapper requires POSIX bash path semantics; use the PowerShell wrapper on Windows")
def test_posix_syntax_bash_n():
    completed = subprocess.run(["bash", "-n", str(POSIX_SH)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX wrapper requires POSIX bash path semantics; use the PowerShell wrapper on Windows")
def test_posix_wrapper_requires_output_dir():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        ["bash", str(POSIX_SH)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == BLOCKED


@pytest.mark.skipif(os.name == "nt", reason="POSIX wrapper requires POSIX bash path semantics; use the PowerShell wrapper on Windows")
def test_posix_wrapper_smoke(tmp_path: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    out = tmp_path / "posix-out"
    completed = subprocess.run(
        [
            "bash",
            str(POSIX_SH),
            "--output-dir",
            str(out),
            "--no-surfaces",
            "--steps",
            "repository_state,finite_json_no_network",
            "--now",
            "2026-09-10T00:00:00+00:00",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode in {PASS, INCOMPLETE}, completed.stdout + completed.stderr
    assert (out / "research_cycle_audit.json").is_file()
    assert "scientific PASS" in completed.stdout


def test_powershell_parser_or_not_available():
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        # Documented NOT_AVAILABLE: still assert the file is parseable as text.
        text = POWERSHELL.read_text(encoding="utf-8")
        assert "param(" in text
        assert "ops.research_cycle" in text
        return
    command = (
        "$errs = $null; "
        "$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{POWERSHELL.as_posix()}', [ref]$null, [ref]$errs); "
        "if ($errs) { $errs | ForEach-Object { $_.ToString() }; exit 1 } else { exit 0 }"
    )
    completed = subprocess.run(
        [pwsh, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_posix_script_is_executable_or_bash_invokable():
    mode = POSIX_SH.stat().st_mode
    # Even without +x, tests invoke via bash. Prefer executable bit when present.
    assert POSIX_SH.is_file()
    if mode & stat.S_IXUSR:
        assert True
    else:
        # still valid when invoked as `bash script`
        assert POSIX_SH.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
