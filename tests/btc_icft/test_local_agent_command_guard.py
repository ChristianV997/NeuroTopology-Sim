"""
Tests for tools/local_agents/command_guard.py (P23).

11 tests covering policy evaluation, allowlist, blocklist,
CommandDecision fields, and policy loading.
"""
import json

import pytest

from tools.local_agents.command_guard import (
    CommandDecision,
    CommandPolicy,
    evaluate_command,
)


# ---------------------------------------------------------------------------
# 1. Default policy: safe allowed command
# ---------------------------------------------------------------------------
def test_allowlisted_command_allowed():
    result = evaluate_command("make ds005620-e2e-mock")
    assert result.allowed is True
    assert result.category == "allowed_policy"


# ---------------------------------------------------------------------------
# 2. Default policy: blocked by blocklist
# ---------------------------------------------------------------------------
def test_wget_blocked():
    result = evaluate_command("wget https://example.com/data.zip")
    assert result.allowed is False
    assert "wget" in result.matched_blocklist


def test_curl_blocked():
    result = evaluate_command("curl -O https://openneuro.org/data.tar.gz")
    assert result.allowed is False
    assert "curl" in result.matched_blocklist


def test_dandi_download_blocked():
    result = evaluate_command("dandi download https://dandiarchive.org/dandiset/000001")
    assert result.allowed is False
    assert "dandi download" in result.matched_blocklist


def test_execute_flag_blocked():
    result = evaluate_command(
        "python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark "
        "--execute --peer-reviewed-contract-confirmed"
    )
    assert result.allowed is False


def test_git_push_blocked():
    result = evaluate_command("git push origin main")
    assert result.allowed is False
    assert "git push" in result.matched_blocklist


def test_rm_rf_blocked():
    result = evaluate_command("rm -rf /data")
    assert result.allowed is False


# ---------------------------------------------------------------------------
# 3. Unknown command — not in allowlist, not in blocklist
# ---------------------------------------------------------------------------
def test_unknown_command_blocked_by_default():
    result = evaluate_command("echo hello world")
    assert result.allowed is False
    assert result.category == "blocked_not_allowlisted"


def test_unknown_command_allowed_when_allow_unlisted():
    policy = CommandPolicy(allow_unlisted_safe=True)
    result = evaluate_command("echo hello", policy)
    assert result.allowed is True
    assert result.category == "allowed_unlisted"


# ---------------------------------------------------------------------------
# 4. Blocklist always wins over allowlist
# ---------------------------------------------------------------------------
def test_blocklist_wins_over_allowlist():
    policy = CommandPolicy(
        allowlist_prefixes=["make some-target wget"],
        blocklist_substrings=["wget"],
    )
    result = evaluate_command("make some-target wget https://x.com", policy)
    assert result.allowed is False


# ---------------------------------------------------------------------------
# 5. Policy from dict
# ---------------------------------------------------------------------------
def test_policy_from_dict():
    d = {
        "allowlist_prefixes": ["make safe-cmd"],
        "blocklist_substrings": ["bad_thing"],
        "allow_unlisted_safe": False,
    }
    policy = CommandPolicy.from_dict(d)
    assert evaluate_command("make safe-cmd", policy).allowed is True
    assert evaluate_command("do bad_thing", policy).allowed is False


# ---------------------------------------------------------------------------
# 6. Policy load from file
# ---------------------------------------------------------------------------
def test_policy_load_from_file(tmp_path):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({
        "command_policy": {
            "allowlist_prefixes": ["make special-target"],
            "blocklist_substrings": ["evil"],
            "allow_unlisted_safe": False,
        }
    }), encoding="utf-8")
    policy = CommandPolicy.load(policy_file)
    assert evaluate_command("make special-target", policy).allowed is True
    assert evaluate_command("do evil things", policy).allowed is False


def test_policy_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        CommandPolicy.load(tmp_path / "does_not_exist.json")
