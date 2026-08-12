"""Tests for `scripts/summarize_ci_failures.py`. Synthetic log fixtures
only -- no real CI log is read, no network, no GitHub API."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.summarize_ci_failures import parse_log, render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Modeled directly on the real PR #203 Required Checks failure signature
# (scripts/run_tests_isolated.py + pytest's short summary), so this test
# doubles as a regression guard for that exact incident's log shape.
_SAMPLE_LOG_WITH_FAILURE = """\
[isolated 30/44] 8 files
......................................................................   [100%]
70 passed in 6.69s
[isolated 31/44] 8 files
F............................................................            [100%]
=================================== FAILURES ===================================
________ test_api_unavailable_in_this_environment_is_reported_honestly _________
FAILED tests/test_job_runner_api.py::test_api_unavailable_in_this_environment_is_reported_honestly - assert True is False
1 failed, 60 passed in 12.91s
[isolated] batch 31 failed with exit code 1
"""

_SAMPLE_LOG_NO_FAILURE = """\
[isolated 1/44] 8 files
........................................................................ [100%]
93 passed in 4.93s
[isolated 2/44] 8 files
........................................................................ [100%]
124 passed in 4.44s
[isolated] completed 350 test files in 44 fresh processes
"""

_SAMPLE_LOG_MULTIPLE_FAILURES = """\
FAILED tests/btc_icft/test_microstates.py::test_fit_microstates_returns_expected_structure
FAILED tests/btc_icft/test_real_features.py::test_complexity_short_signal_returns_nan - ValueError: short signal
"""

# ERROR lines cover pytest collection/fixture-setup failures, which use a
# different short-summary prefix than a normal assertion failure and can
# omit the "::test_id" part for a whole-file collection error.
_SAMPLE_LOG_WITH_ERROR = """\
ERROR tests/test_cross_modal_fusion.py
ERROR tests/test_job_runner_api.py::test_create_job_via_plain_function - ModuleNotFoundError: no module named 'x'
"""


def test_extracts_failed_test_node_ids():
    summary = parse_log(_SAMPLE_LOG_WITH_FAILURE)
    assert summary["total_failed_tests"] == 1
    assert summary["failed_tests"][0]["status"] == "FAILED"
    assert summary["failed_tests"][0]["node_id"] == (
        "tests/test_job_runner_api.py::test_api_unavailable_in_this_environment_is_reported_honestly"
    )
    assert summary["failed_tests"][0]["reason"] == "assert True is False"


def test_extracts_error_lines_alongside_failed_lines():
    # pytest's collection/fixture-setup failures use "ERROR ..." rather than
    # "FAILED ...", and a whole-file collection error can omit "::test_id".
    summary = parse_log(_SAMPLE_LOG_WITH_ERROR)
    assert summary["total_failed_tests"] == 2
    assert summary["has_failures"] is True
    assert summary["failed_tests"][0]["status"] == "ERROR"
    assert summary["failed_tests"][0]["node_id"] == "tests/test_cross_modal_fusion.py"
    assert summary["failed_tests"][0]["reason"] == ""
    assert summary["failed_tests"][1]["status"] == "ERROR"
    assert summary["failed_tests"][1]["node_id"] == "tests/test_job_runner_api.py::test_create_job_via_plain_function"
    assert summary["failed_tests"][1]["reason"] == "ModuleNotFoundError: no module named 'x'"


def test_extracts_failed_isolated_batch_number():
    summary = parse_log(_SAMPLE_LOG_WITH_FAILURE)
    assert summary["failed_batch"] == 31
    assert summary["total_batches"] == 44
    assert summary["failed_batch_exit_code"] == 1


def test_handles_no_failures():
    summary = parse_log(_SAMPLE_LOG_NO_FAILURE)
    assert summary["has_failures"] is False
    assert summary["total_failed_tests"] == 0
    assert summary["failed_tests"] == []
    assert summary["failed_batch"] is None


def test_handles_multiple_failed_tests_with_and_without_reason():
    summary = parse_log(_SAMPLE_LOG_MULTIPLE_FAILURES)
    assert summary["total_failed_tests"] == 2
    assert summary["failed_tests"][0]["reason"] == ""
    assert summary["failed_tests"][1]["reason"] == "ValueError: short signal"


def test_handles_empty_log():
    summary = parse_log("")
    assert summary["has_failures"] is False
    assert summary["total_failed_tests"] == 0


def test_json_output_is_deterministic():
    s1 = parse_log(_SAMPLE_LOG_WITH_FAILURE)
    s2 = parse_log(_SAMPLE_LOG_WITH_FAILURE)
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)


def test_markdown_render_no_failures():
    summary = parse_log(_SAMPLE_LOG_NO_FAILURE)
    text = render_markdown(summary)
    assert "No failures detected" in text


def test_markdown_render_with_failures_lists_node_ids():
    summary = parse_log(_SAMPLE_LOG_WITH_FAILURE)
    text = render_markdown(summary)
    assert "test_api_unavailable_in_this_environment_is_reported_honestly" in text
    assert "[FAILED]" in text
    assert "failed_batch: 31 / 44" in text


def test_markdown_render_distinguishes_error_status():
    summary = parse_log(_SAMPLE_LOG_WITH_ERROR)
    text = render_markdown(summary)
    assert "[ERROR]" in text


def test_cli_json_output(tmp_path):
    log_path = tmp_path / "ci.log"
    log_path.write_text(_SAMPLE_LOG_WITH_FAILURE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/summarize_ci_failures.py", "--log", str(log_path)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["failed_batch"] == 31


def test_cli_missing_log_fails_clearly():
    result = subprocess.run(
        [sys.executable, "scripts/summarize_ci_failures.py", "--log", "does/not/exist.txt"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr


def test_cli_stdin_input(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/summarize_ci_failures.py", "--log", "-", "--format", "markdown"],
        input=_SAMPLE_LOG_NO_FAILURE, capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No failures detected" in result.stdout
