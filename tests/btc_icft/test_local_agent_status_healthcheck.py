"""
Tests for P24 local agent status, healthcheck, and command guard CLI.

21 tests covering:
- Command guard CLI (5 tests)
- Makefile target presence (2 tests)
- Status module (7 tests)
- Healthcheck module (7 tests)
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_agents.command_guard import (
    CommandPolicy,
    check_policy_defaults,
    evaluate_command,
    main as command_guard_main,
)
from tools.local_agents.status import build_local_agent_status
from tools.local_agents.healthcheck import run_healthcheck


# ---------------------------------------------------------------------------
# Command guard CLI (5 tests)
# ---------------------------------------------------------------------------

def test_command_guard_check_defaults_ok():
    policy = CommandPolicy()
    result = check_policy_defaults(policy)
    assert result["ok"] is True
    assert result["violations"] == []


def test_command_guard_check_defaults_returns_dict():
    policy = CommandPolicy()
    result = check_policy_defaults(policy)
    assert "ok" in result
    assert "violations" in result
    assert "warnings" in result


def test_command_guard_cli_check_defaults_exit_zero(tmp_path):
    out = tmp_path / "policy_check.json"
    rc = command_guard_main(["--check-defaults", "--json-out", str(out)])
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert "ok" in data


def test_command_guard_cli_evaluate_allowed_command(tmp_path):
    out = tmp_path / "cmd_result.json"
    rc = command_guard_main(["--command", "make ds005620-e2e-mock", "--json-out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["allowed"] is True


def test_command_guard_cli_evaluate_blocked_command(tmp_path):
    out = tmp_path / "cmd_result.json"
    rc = command_guard_main(["--command", "git push origin main", "--json-out", str(out)])
    # rc == 1 for blocked commands; JSON output still written
    assert rc == 1
    data = json.loads(out.read_text())
    assert data["allowed"] is False


# ---------------------------------------------------------------------------
# Makefile target presence (2 tests)
# ---------------------------------------------------------------------------

def test_makefile_has_p24_local_agent_targets():
    makefile = _REPO_ROOT / "Makefile"
    assert makefile.exists()
    content = makefile.read_text(encoding="utf-8")
    for target in [
        "local-agent-status",
        "local-agent-healthcheck",
        "local-agent-scheduler-plan",
        "local-agent-policy-check",
        "local-agent-loop-dry-run",
        "local-agent-loop-once",
        "sync-obsidian",
    ]:
        assert target in content, f"Makefile missing target: {target}"


def test_makefile_p24_targets_use_module_cli():
    makefile = _REPO_ROOT / "Makefile"
    content = makefile.read_text(encoding="utf-8")
    assert "python -m tools.local_agents.command_guard" in content
    assert "python -m tools.local_agents.obsidian_sync" in content
    assert "python -m tools.local_agents.status" in content
    assert "python -m tools.local_agents.healthcheck" in content
    assert "python -m tools.local_agents.scheduler_plan" in content


# ---------------------------------------------------------------------------
# Status module (7 tests)
# ---------------------------------------------------------------------------

def test_status_returns_dict(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert isinstance(status, dict)


def test_status_ok_field(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert status["ok"] is True


def test_status_has_required_keys(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    required = [
        "ok", "generated_at", "repo_runtime_available",
        "ds005620_status", "multi_dataset_status", "language_status",
        "ontology_status", "local_agent_loop_status", "obsidian_status",
        "next_action", "next_command", "manual_required",
        "human_review_required", "blocked_by", "warnings", "guardrails",
    ]
    for key in required:
        assert key in status, f"Status missing key: {key}"


def test_status_guardrails_safe(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    guardrails = status["guardrails"]
    # These must always be False
    for k in ["executes_real_data", "downloads_data", "auto_confirms_peer_review", "empirical_claims_permitted"]:
        assert guardrails[k] is False, f"Status guardrail {k} must be False"
    # ontology must remain quarantined
    assert guardrails["ontology_quarantined"] is True


def test_status_ds005620_peer_review_not_autoconfirmed(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert status["ds005620_status"]["peer_review_confirmed_by_human"] is False


def test_status_blocked_by_is_list(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert isinstance(status["blocked_by"], list)


def test_status_next_action_is_string(tmp_path):
    status = build_local_agent_status(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert isinstance(status["next_action"], str)
    assert len(status["next_action"]) > 0


# ---------------------------------------------------------------------------
# Healthcheck module (7 tests)
# ---------------------------------------------------------------------------

def test_healthcheck_returns_dict(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert isinstance(result, dict)


def test_healthcheck_ok_field_present(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert "ok" in result


def test_healthcheck_has_required_keys(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    required = [
        "ok", "checks", "blockers", "warnings",
        "ollama_available", "obsidian_writable", "policy_ok",
        "unsafe_command_blocks_ok", "make_targets_available", "guardrails",
    ]
    for key in required:
        assert key in result, f"Healthcheck missing key: {key}"


def test_healthcheck_policy_ok(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert result["policy_ok"] is True


def test_healthcheck_unsafe_commands_blocked(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert result["unsafe_command_blocks_ok"] is True


def test_healthcheck_guardrails_all_false(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    for k, v in result["guardrails"].items():
        assert v is False, f"Healthcheck guardrail {k} must be False"


def test_healthcheck_checks_is_list(tmp_path):
    result = run_healthcheck(
        root=str(tmp_path / "btc_icft"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert isinstance(result["checks"], list)
    assert len(result["checks"]) > 0
    for check in result["checks"]:
        assert "name" in check
        assert "ok" in check
