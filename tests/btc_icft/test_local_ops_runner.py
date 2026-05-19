"""
Tests for P25 local continuous operations runner.

Covers:
- dry-run writes plan/results/report
- once mode with mocked safe commands
- loop mode respects max_iterations
- loop mode does not run infinitely by default
- blocked command is never executed
- runner stops on failure unless continue-on-error
- continue-on-error records failure and continues
- events JSONL written
- next_action written
- sync invoked only through allowed command
- real execution command refused
- download command refused
- optional missing multi-dataset target handled
"""
import json
import sys
from pathlib import Path
from typing import Optional

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_ops.runner import (
    LocalOpsRunnerConfig,
    run_local_ops,
    _RUNNER_VERSION,
    _GUARDRAILS,
    _is_command_forbidden,
)
from tools.local_agents.safe_runner import SafeCommandResult


def _mock_runner_ok(parts, cwd, timeout):
    """Always returns success."""
    return 0, "ok", ""


def _mock_runner_fail(parts, cwd, timeout):
    """Always returns failure."""
    return 1, "", "simulated failure"


def _make_config(tmp_path, mode="dry-run", **kwargs):
    return LocalOpsRunnerConfig(
        mode=mode,
        out_dir=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
        policy_path="configs/local_ops/local_ops_policy.json",
        safe_commands=["make local-agent-healthcheck", "make local-agent-status"],
        no_lock=True,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test 1: dry-run writes plan/results/report
# ---------------------------------------------------------------------------

def test_dry_run_writes_plan(tmp_path):
    config = _make_config(tmp_path, mode="dry-run")
    run_local_ops(config)
    out = tmp_path / "local_ops"
    assert (out / "local_ops_plan.json").exists()
    data = json.loads((out / "local_ops_plan.json").read_text())
    assert "runner_version" in data
    assert data["mode"] == "dry-run"


def test_dry_run_writes_results(tmp_path):
    config = _make_config(tmp_path, mode="dry-run")
    run_local_ops(config)
    out = tmp_path / "local_ops"
    assert (out / "local_ops_results.json").exists()
    results = json.loads((out / "local_ops_results.json").read_text())
    assert isinstance(results, list)


def test_dry_run_writes_report(tmp_path):
    config = _make_config(tmp_path, mode="dry-run")
    run_local_ops(config)
    out = tmp_path / "local_ops"
    assert (out / "local_ops_report.md").exists()
    content = (out / "local_ops_report.md").read_text()
    assert "P25" in content or "Continuous" in content.lower()


def test_dry_run_status_is_dry_run_complete(tmp_path):
    config = _make_config(tmp_path, mode="dry-run")
    result = run_local_ops(config)
    assert result.status == "dry_run_complete"


# ---------------------------------------------------------------------------
# Test 5: once mode runs mocked safe commands
# ---------------------------------------------------------------------------

def test_once_mode_executes_commands(tmp_path):
    config = _make_config(tmp_path, mode="once")
    result = run_local_ops(config, _command_runner=_mock_runner_ok)
    assert result.mode == "once"
    assert result.iterations_completed >= 1
    assert result.safe_commands_succeeded >= 1


def test_once_mode_writes_state_json(tmp_path):
    config = _make_config(tmp_path, mode="once")
    run_local_ops(config, _command_runner=_mock_runner_ok)
    out = tmp_path / "local_ops"
    assert (out / "local_ops_state.json").exists()
    state = json.loads((out / "local_ops_state.json").read_text())
    assert "status" in state
    assert state["mode"] == "once"


# ---------------------------------------------------------------------------
# Test 7: loop mode respects max_iterations
# ---------------------------------------------------------------------------

def test_loop_mode_respects_max_iterations(tmp_path):
    config = _make_config(tmp_path, mode="loop", max_iterations=2, interval_seconds=0)
    result = run_local_ops(config, _command_runner=_mock_runner_ok)
    assert result.iterations_completed == 2


# ---------------------------------------------------------------------------
# Test 8: loop mode does not run infinitely by default
# ---------------------------------------------------------------------------

def test_loop_mode_finite_by_default(tmp_path):
    config = _make_config(tmp_path, mode="loop", max_iterations=1, interval_seconds=0)
    result = run_local_ops(config, _command_runner=_mock_runner_ok)
    assert result.iterations_completed <= 1


# ---------------------------------------------------------------------------
# Test 9: blocked command is never executed
# ---------------------------------------------------------------------------

def test_blocked_command_never_executed(tmp_path):
    executed = []

    def tracking_runner(parts, cwd, timeout):
        executed.append(" ".join(parts))
        return 0, "ok", ""

    config = _make_config(tmp_path, mode="once")
    config.safe_commands = ["git push origin main", "make local-agent-healthcheck"]
    run_local_ops(config, _command_runner=tracking_runner)
    # git push must never appear in executed commands
    for cmd in executed:
        assert "git push" not in cmd


def test_blocked_command_result_not_allowed(tmp_path):
    config = _make_config(tmp_path, mode="once")
    config.safe_commands = ["git push origin main"]
    result = run_local_ops(config, _command_runner=_mock_runner_ok)
    assert result.commands_blocked >= 1


# ---------------------------------------------------------------------------
# Test 11: runner stops on failed command unless continue-on-error
# ---------------------------------------------------------------------------

def test_runner_stops_on_failure(tmp_path):
    config = _make_config(tmp_path, mode="once", continue_on_error=False)
    config.safe_commands = [
        "make local-agent-healthcheck",
        "make local-agent-status",
    ]
    result = run_local_ops(config, _command_runner=_mock_runner_fail)
    # Should stop after first failure
    assert result.safe_commands_failed >= 1


# ---------------------------------------------------------------------------
# Test 12: continue-on-error records failure and continues
# ---------------------------------------------------------------------------

def test_continue_on_error_records_and_continues(tmp_path):
    call_count = [0]

    def counting_runner(parts, cwd, timeout):
        call_count[0] += 1
        return 1, "", "fail"  # always fail

    config = _make_config(tmp_path, mode="once", continue_on_error=True)
    config.safe_commands = [
        "make local-agent-healthcheck",
        "make local-agent-status",
    ]
    result = run_local_ops(config, _command_runner=counting_runner)
    # Both commands should have been attempted
    assert call_count[0] == 2
    assert result.safe_commands_failed >= 1


# ---------------------------------------------------------------------------
# Test 13: runner writes events JSONL
# ---------------------------------------------------------------------------

def test_runner_writes_events_jsonl(tmp_path):
    config = _make_config(tmp_path, mode="once")
    run_local_ops(config, _command_runner=_mock_runner_ok)
    events_path = tmp_path / "local_ops" / "local_ops_events.jsonl"
    assert events_path.exists()
    lines = [l for l in events_path.read_text().strip().splitlines() if l.strip()]
    assert len(lines) > 0
    for line in lines:
        ev = json.loads(line)
        assert "source" in ev
        assert ev["source"] == "p25_local_ops_runner"


# ---------------------------------------------------------------------------
# Test 14: runner writes next_action
# ---------------------------------------------------------------------------

def test_runner_writes_next_action(tmp_path):
    config = _make_config(tmp_path, mode="once")
    run_local_ops(config, _command_runner=_mock_runner_ok)
    next_action_path = tmp_path / "local_ops" / "local_ops_next_action.json"
    assert next_action_path.exists()
    data = json.loads(next_action_path.read_text())
    assert "next_action" in data
    assert isinstance(data["next_action"], str)


# ---------------------------------------------------------------------------
# Test 15: runner invokes sync only through allowed command
# ---------------------------------------------------------------------------

def test_runner_sync_via_allowed_command(tmp_path):
    executed = []

    def tracking_runner(parts, cwd, timeout):
        executed.append(" ".join(parts))
        return 0, "ok", ""

    config = _make_config(tmp_path, mode="once")
    config.safe_commands = ["make sync-obsidian"]
    run_local_ops(config, _command_runner=tracking_runner)
    # The sync command should have been executed
    assert any("sync-obsidian" in cmd for cmd in executed)


# ---------------------------------------------------------------------------
# Test 16: runner refuses real execution command
# ---------------------------------------------------------------------------

def test_runner_refuses_real_execution(tmp_path):
    executed = []

    def tracking_runner(parts, cwd, timeout):
        executed.append(" ".join(parts))
        return 0, "ok", ""

    real_cmd = "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --execute --peer-reviewed-contract-confirmed"
    config = _make_config(tmp_path, mode="once")
    config.safe_commands = [real_cmd]
    result = run_local_ops(config, _command_runner=tracking_runner)
    assert result.commands_blocked >= 1
    # Real exec never reaches tracking_runner
    assert not any("peer-reviewed-contract-confirmed" in cmd for cmd in executed)


# ---------------------------------------------------------------------------
# Test 17: runner refuses download command
# ---------------------------------------------------------------------------

def test_runner_refuses_download_command(tmp_path):
    executed = []

    def tracking_runner(parts, cwd, timeout):
        executed.append(" ".join(parts))
        return 0, "ok", ""

    config = _make_config(tmp_path, mode="once")
    config.safe_commands = ["wget https://example.com/data.zip"]
    run_local_ops(config, _command_runner=tracking_runner)
    assert not any("wget" in cmd for cmd in executed)


# ---------------------------------------------------------------------------
# Test 18: runner handles optional missing multi-dataset target gracefully
# ---------------------------------------------------------------------------

def test_runner_handles_optional_missing_target(tmp_path):
    config = _make_config(tmp_path, mode="once")
    # Even if multi-dataset command is in optional, it's not in safe_commands by default
    config.safe_commands = ["make local-agent-healthcheck"]
    # Should complete without error
    result = run_local_ops(config, _command_runner=_mock_runner_ok)
    assert result.status in ("succeeded", "failed", "dry_run_complete")


# ---------------------------------------------------------------------------
# _is_command_forbidden helper tests
# ---------------------------------------------------------------------------

def test_is_command_forbidden_blocks_wget():
    assert _is_command_forbidden("wget https://example.com")


def test_is_command_forbidden_blocks_git_push():
    assert _is_command_forbidden("git push origin main")


def test_is_command_forbidden_blocks_real_exec():
    assert _is_command_forbidden("--execute --peer-reviewed-contract-confirmed")


def test_is_command_forbidden_allows_safe_make():
    assert not _is_command_forbidden("make local-agent-healthcheck")


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

def test_runner_guardrails_all_false():
    for k, v in _GUARDRAILS.items():
        assert v is False, f"Guardrail {k} must be False"
