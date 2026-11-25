"""Tests for process lifecycle, timeout termination, tree cleanup, and output streaming."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.runner_acceptance.research_runtime.contracts import ScenarioOutcome
from tools.runner_acceptance.research_runtime.platform_checks import is_windows
from tools.runner_acceptance.research_runtime.scenarios import (
    run_bounded_output_streaming,
    run_malformed_child_output,
    run_posix_signal_behavior,
    run_process_timeout_termination,
    run_process_tree_cleanup,
)


def test_process_timeout_termination_scenario(tmp_path: Path) -> None:
    """Verifies that timed-out process is killed without hanging."""
    res = run_process_timeout_termination(tmp_path)
    assert res.status == ScenarioOutcome.PASS
    assert res.timeout_state is True
    assert res.orphan_cleanup_state == "clean"


def test_process_tree_cleanup_scenario(tmp_path: Path) -> None:
    """Verifies that terminating a process kills its spawned descendants."""
    res = run_process_tree_cleanup(tmp_path)
    assert res.status == ScenarioOutcome.PASS
    assert res.orphan_cleanup_state == "clean"
    assert "parent_pid" in res.metadata
    assert "grandchild_pid" in res.metadata


def test_bounded_output_streaming_scenario(tmp_path: Path) -> None:
    """Verifies that an output flood is safely bounded."""
    res = run_bounded_output_streaming(tmp_path)
    assert res.status == ScenarioOutcome.PASS
    assert res.metadata["truncated"] is True
    assert res.metadata["bytes_captured"] >= res.metadata["capped_at_bytes"]


def test_malformed_child_output_scenario(tmp_path: Path) -> None:
    """Verifies that invalid binary/non-UTF8 bytes do not crash the runner."""
    res = run_malformed_child_output(tmp_path)
    assert res.status == ScenarioOutcome.PASS
    assert "VALID_HEADER_" in res.metadata["decoded_preview"]


def test_posix_signal_behavior_scenario(tmp_path: Path) -> None:
    """Verifies POSIX signal behavior scenario rules."""
    res = run_posix_signal_behavior(tmp_path)
    if is_windows():
        assert res.status == ScenarioOutcome.UNSUPPORTED
        assert "POSIX-specific" in (res.unsupported_reason or "")
    else:
        assert res.status == ScenarioOutcome.PASS
