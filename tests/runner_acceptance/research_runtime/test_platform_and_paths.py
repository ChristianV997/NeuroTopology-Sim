"""Tests for platform checks, path normalization, PowerShell commands, and Unicode paths."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from tools.runner_acceptance.research_runtime.contracts import ScenarioOutcome
from tools.runner_acceptance.research_runtime.platform_checks import (
    build_powershell_command,
    check_windows_file_locking,
    detect_powershell,
    is_posix,
    is_windows,
    normalize_windows_path,
)
from tools.runner_acceptance.research_runtime.scenarios import (
    run_powershell_smoke,
    run_unicode_and_utf8_paths,
    run_windows_locked_file_cleanup,
    run_windows_path_normalization,
)


def test_platform_consistency() -> None:
    """Verifies that is_windows and is_posix match os.name."""
    if os.name == "nt":
        assert is_windows() is True
        assert is_posix() is False
    else:
        assert is_windows() is False
        assert is_posix() is True


def test_powershell_command_construction() -> None:
    """Verifies argument structure of hardened PowerShell invocation."""
    cmd = build_powershell_command("Get-Process", exe="pwsh")
    assert cmd[0] == "pwsh"
    assert "-NoProfile" in cmd
    assert "-NonInteractive" in cmd
    assert "-ExecutionPolicy" in cmd
    assert cmd[-1] == "Get-Process"


def test_powershell_smoke_scenario(tmp_path: Path) -> None:
    """Verifies PowerShell scenario runner."""
    res = run_powershell_smoke(tmp_path)
    if is_windows() or detect_powershell()[0]:
        assert res.status == ScenarioOutcome.PASS
        assert res.exit_code == 0
    else:
        assert res.status == ScenarioOutcome.UNSUPPORTED


def test_windows_path_normalization_scenario(tmp_path: Path) -> None:
    """Verifies Windows path normalization scenario."""
    res = run_windows_path_normalization(tmp_path)
    if is_windows():
        assert res.status == ScenarioOutcome.PASS
        # Direct normalization assertions
        long_path = "C:/" + "sub_" * 60 + "/file.txt"
        norm = normalize_windows_path(long_path)
        assert norm.startswith("\\\\?\\")
        assert "/" not in norm
    else:
        assert res.status == ScenarioOutcome.UNSUPPORTED


def test_windows_locked_file_cleanup_scenario(tmp_path: Path) -> None:
    """Verifies file lock scenario semantics."""
    res = run_windows_locked_file_cleanup(tmp_path)
    if is_windows():
        assert res.status == ScenarioOutcome.PASS
        assert "detected_error_type" in res.metadata
    else:
        assert res.status == ScenarioOutcome.UNSUPPORTED


def test_unicode_and_utf8_paths_scenario(tmp_path: Path) -> None:
    """Verifies that non-ASCII Unicode paths work reliably on all supported platforms."""
    res = run_unicode_and_utf8_paths(tmp_path)
    assert res.status == ScenarioOutcome.PASS
    assert res.artifact_checksum is not None
    assert len(res.artifact_checksum) == 64
