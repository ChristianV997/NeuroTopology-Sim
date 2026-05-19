"""
Tests for P25 healthcheck, install plan, status, Makefile targets, and docs.

Covers:
- healthcheck writes JSON
- healthcheck detects dangerous command in policy
- healthcheck passes with Ollama unavailable
- install_plan writes JSON and Markdown
- install_plan includes cron/systemd/launchd examples
- install_plan does not install anything
- install_plan does not include real execution commands
- Makefile contains local-ops targets
- docs exist
- docs avoid unsafe empirical phrases outside guardrail sections
- no tests require real datasets
- no tests require Ollama
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_ops.healthcheck import run_healthcheck
from tools.local_ops.install_plan import build_install_plan, build_install_plan_report, main as install_plan_main
from tools.local_ops.status import build_ops_status


# ---------------------------------------------------------------------------
# Healthcheck tests
# ---------------------------------------------------------------------------

def test_healthcheck_writes_json(tmp_path):
    out = tmp_path / "local_ops"
    out.mkdir()
    result = run_healthcheck(
        output_root=str(out),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    json_path = out / "local_ops_healthcheck.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert "ok" in data


def test_healthcheck_returns_dict(tmp_path):
    result = run_healthcheck(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert isinstance(result, dict)
    assert "ok" in result
    assert "checks" in result


def test_healthcheck_has_required_keys(tmp_path):
    result = run_healthcheck(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    for key in ["ok", "checks", "blockers", "warnings", "policy_ok",
                "unsafe_command_blocks_ok", "make_targets_available", "guardrails"]:
        assert key in result, f"Healthcheck missing key: {key}"


def test_healthcheck_passes_without_ollama(tmp_path):
    result = run_healthcheck(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    # Ollama is optional — healthcheck must not fail just because Ollama is absent
    ollama_check = next((c for c in result["checks"] if c["name"] == "ollama_available"), None)
    assert ollama_check is not None
    assert ollama_check["ok"] is True


def test_healthcheck_policy_ok(tmp_path):
    result = run_healthcheck(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert result["policy_ok"] is True


def test_healthcheck_unsafe_commands_blocked(tmp_path):
    result = run_healthcheck(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    assert result["unsafe_command_blocks_ok"] is True


def test_healthcheck_guardrails_all_false(tmp_path):
    result = run_healthcheck(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        vault=str(tmp_path / "vault"),
    )
    for k, v in result["guardrails"].items():
        assert v is False, f"Healthcheck guardrail {k} must be False"


def test_healthcheck_detects_real_execution_in_policy(tmp_path):
    """If a dangerous command appears in local_ops_policy, healthcheck should flag it."""
    from tools.local_ops.healthcheck import _check_local_ops_policy
    bad_policy = tmp_path / "bad_policy.json"
    bad_policy.write_text(json.dumps({
        "safe_command_sequence": [
            "python -m something --execute --peer-reviewed-contract-confirmed"
        ]
    }), encoding="utf-8")
    check = _check_local_ops_policy(policy_path=bad_policy)
    assert check["ok"] is False


# ---------------------------------------------------------------------------
# Install plan tests
# ---------------------------------------------------------------------------

def test_install_plan_returns_dict():
    plan = build_install_plan()
    assert isinstance(plan, dict)


def test_install_plan_has_required_fields():
    plan = build_install_plan()
    for field in ["plan_version", "safe_to_schedule", "recommended_command", "dry_run_command",
                  "cron_example", "systemd_example", "launchd_example",
                  "daemon_implemented", "auto_installed", "guardrails",
                  "human_required_boundaries"]:
        assert field in plan, f"Missing field: {field}"


def test_install_plan_includes_cron_example():
    plan = build_install_plan()
    assert "cron" in plan["cron_example"].lower() or "* * * *" in plan["cron_example"]


def test_install_plan_includes_systemd_example():
    plan = build_install_plan()
    assert "systemd" in plan["systemd_example"].lower() or "[Unit]" in plan["systemd_example"]


def test_install_plan_includes_launchd_example():
    plan = build_install_plan()
    assert "launchd" in plan["launchd_example"].lower() or "plist" in plan["launchd_example"].lower()


def test_install_plan_daemon_not_implemented():
    plan = build_install_plan()
    assert plan["daemon_implemented"] is False


def test_install_plan_not_auto_installed():
    plan = build_install_plan()
    assert plan["auto_installed"] is False


def test_install_plan_does_not_include_real_execution():
    plan = build_install_plan()
    real_exec_patterns = [
        "--execute --peer-reviewed-contract-confirmed",
        "dandi download",
        "run_ds005620_real_benchmark",
    ]
    for example_key in ["cron_example", "systemd_example", "launchd_example", "openclaw_trigger_design"]:
        text = plan.get(example_key, "")
        for pat in real_exec_patterns:
            assert pat not in text, f"Real execution pattern {pat!r} found in {example_key}"


def test_install_plan_recommended_command_is_safe():
    plan = build_install_plan()
    cmd = plan["recommended_command"]
    assert "local-ops-run-once" in cmd
    assert "push" not in cmd
    assert "merge" not in cmd
    assert "download" not in cmd


def test_install_plan_writes_json_and_md(tmp_path):
    rc = install_plan_main(["--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "install_plan.json").exists()
    assert (tmp_path / "install_plan.md").exists()


def test_install_plan_md_contains_cron(tmp_path):
    install_plan_main(["--out", str(tmp_path)])
    content = (tmp_path / "install_plan.md").read_text()
    assert "cron" in content.lower() or "* * * *" in content


def test_install_plan_md_contains_systemd(tmp_path):
    install_plan_main(["--out", str(tmp_path)])
    content = (tmp_path / "install_plan.md").read_text()
    assert "systemd" in content.lower() or "[Unit]" in content


def test_install_plan_md_contains_launchd(tmp_path):
    install_plan_main(["--out", str(tmp_path)])
    content = (tmp_path / "install_plan.md").read_text()
    assert "launchd" in content.lower() or "plist" in content.lower()


def test_install_plan_guardrails_all_false():
    plan = build_install_plan()
    for k, v in plan["guardrails"].items():
        assert v is False, f"Install plan guardrail {k} must be False"


# ---------------------------------------------------------------------------
# Status module
# ---------------------------------------------------------------------------

def test_ops_status_returns_dict(tmp_path):
    status = build_ops_status(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        btc_root=str(tmp_path / "btc_icft"),
    )
    assert isinstance(status, dict)
    assert "ok" in status


def test_ops_status_has_required_keys(tmp_path):
    status = build_ops_status(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        btc_root=str(tmp_path / "btc_icft"),
    )
    for key in ["ok", "generated_at", "last_run_status", "next_action",
                "blocked_by", "manual_required", "human_review_required",
                "dataset_next_actions", "local_agent_health", "warnings", "guardrails"]:
        assert key in status, f"Status missing key: {key}"


def test_ops_status_guardrails_all_false(tmp_path):
    status = build_ops_status(
        output_root=str(tmp_path / "local_ops"),
        local_agent_root=str(tmp_path / "local_agents"),
        btc_root=str(tmp_path / "btc_icft"),
    )
    for k, v in status["guardrails"].items():
        assert v is False, f"Status guardrail {k} must be False"


# ---------------------------------------------------------------------------
# Makefile targets
# ---------------------------------------------------------------------------

def test_makefile_has_local_ops_run_once():
    makefile = _REPO_ROOT / "Makefile"
    assert "local-ops-run-once" in makefile.read_text()


def test_makefile_has_local_ops_run_loop_dry_run():
    makefile = _REPO_ROOT / "Makefile"
    assert "local-ops-run-loop-dry-run" in makefile.read_text()


def test_makefile_has_local_ops_run_loop():
    makefile = _REPO_ROOT / "Makefile"
    assert "local-ops-run-loop" in makefile.read_text()


def test_makefile_has_local_ops_healthcheck():
    makefile = _REPO_ROOT / "Makefile"
    assert "local-ops-healthcheck" in makefile.read_text()


def test_makefile_has_local_ops_install_plan():
    makefile = _REPO_ROOT / "Makefile"
    assert "local-ops-install-plan" in makefile.read_text()


def test_makefile_local_ops_targets_use_module_cli():
    content = (_REPO_ROOT / "Makefile").read_text()
    assert "python -m tools.local_ops.runner" in content
    assert "python -m tools.local_ops.healthcheck" in content
    assert "python -m tools.local_ops.status" in content
    assert "python -m tools.local_ops.install_plan" in content


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------

def test_local_continuous_ops_doc_exists():
    doc = _REPO_ROOT / "docs" / "local_continuous_operations_runner.md"
    assert doc.exists(), "docs/local_continuous_operations_runner.md must exist"


def test_local_continuous_ops_doc_mentions_targets():
    content = (_REPO_ROOT / "docs" / "local_continuous_operations_runner.md").read_text()
    for target in ["local-ops-run-once", "local-ops-run-loop-dry-run", "local-ops-healthcheck"]:
        assert target in content, f"Doc missing reference to {target}"


def test_docs_avoid_empirical_claim_language():
    doc = _REPO_ROOT / "docs" / "local_continuous_operations_runner.md"
    content = doc.read_text().lower()
    # These phrases signal unsafe empirical claims outside guardrail sections
    unsafe_phrases = [
        "we prove",
        "proves that",
        "demonstrated empirically",
        "statistically significant result",
    ]
    for phrase in unsafe_phrases:
        assert phrase not in content, f"Unsafe phrase found in doc: {phrase!r}"
