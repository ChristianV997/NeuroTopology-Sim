"""
Tests for P24 scheduler plan, obsidian new vault structure, and research loop P24 outputs.

17 tests covering:
- Scheduler plan module (7 tests)
- Obsidian P24 vault structure (5 tests)
- Research loop P24 outputs (5 tests)
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_agents.scheduler_plan import build_scheduler_plan, build_scheduler_report
from tools.local_agents.obsidian_sync import sync_obsidian
from tools.local_agents.research_loop import ResearchLoopConfig, run_research_loop


# ---------------------------------------------------------------------------
# Scheduler plan module (7 tests)
# ---------------------------------------------------------------------------

def test_scheduler_plan_returns_dict():
    plan = build_scheduler_plan()
    assert isinstance(plan, dict)


def test_scheduler_plan_safe_to_schedule():
    plan = build_scheduler_plan()
    assert plan["safe_to_schedule"] is True


def test_scheduler_plan_daemon_not_implemented():
    plan = build_scheduler_plan()
    assert plan["daemon_implemented"] is False


def test_scheduler_plan_guardrails_all_false():
    plan = build_scheduler_plan()
    for k, v in plan["guardrails"].items():
        assert v is False, f"Scheduler plan guardrail {k} must be False"


def test_scheduler_plan_has_required_fields():
    plan = build_scheduler_plan()
    required = [
        "plan_version", "safe_to_schedule", "recommended_interval_minutes",
        "command", "dry_run_command", "cron_example", "systemd_example",
        "launchd_example", "openclaw_trigger_design", "docker_future_note",
        "daemon_implemented", "guardrails", "forbidden_commands",
        "human_required_boundaries",
    ]
    for field in required:
        assert field in plan, f"Scheduler plan missing field: {field}"


def test_scheduler_plan_forbidden_commands_block_git_push():
    plan = build_scheduler_plan()
    forbidden = plan["forbidden_commands"]
    assert any("git push" in cmd for cmd in forbidden)


def test_scheduler_plan_report_is_string():
    plan = build_scheduler_plan()
    report = build_scheduler_report(plan)
    assert isinstance(report, str)
    assert "Scheduler Plan" in report
    assert "daemon" in report.lower()
    assert "guardrails" in report.lower()


def test_scheduler_plan_writes_files(tmp_path):
    from tools.local_agents.scheduler_plan import main as scheduler_main
    rc = scheduler_main(["--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "scheduler_plan.json").exists()
    assert (tmp_path / "scheduler_report.md").exists()
    data = json.loads((tmp_path / "scheduler_plan.json").read_text())
    assert data["safe_to_schedule"] is True


# ---------------------------------------------------------------------------
# Obsidian P24 vault structure (5 tests)
# ---------------------------------------------------------------------------

def test_obsidian_sync_creates_p24_dashboard(tmp_path):
    vault = tmp_path / "vault"
    result = sync_obsidian(
        outputs_root=str(tmp_path / "btc_icft"),
        vault_root=str(vault),
    )
    assert result.error == "", f"Sync had error: {result.error}"
    dashboard_files = list((vault / "00_Dashboard").iterdir()) if (vault / "00_Dashboard").exists() else []
    assert len(dashboard_files) > 0, "00_Dashboard directory should have files"


def test_obsidian_sync_creates_p24_datasets_dir(tmp_path):
    vault = tmp_path / "vault"
    sync_obsidian(
        outputs_root=str(tmp_path / "btc_icft"),
        vault_root=str(vault),
    )
    assert (vault / "01_Datasets").exists()


def test_obsidian_sync_creates_p24_runtime_dir(tmp_path):
    vault = tmp_path / "vault"
    sync_obsidian(
        outputs_root=str(tmp_path / "btc_icft"),
        vault_root=str(vault),
    )
    assert (vault / "02_Runtime").exists()


def test_obsidian_sync_creates_p24_evidence_dir(tmp_path):
    vault = tmp_path / "vault"
    sync_obsidian(
        outputs_root=str(tmp_path / "btc_icft"),
        vault_root=str(vault),
    )
    assert (vault / "03_Evidence").exists()


def test_obsidian_sync_result_has_next_action(tmp_path):
    vault = tmp_path / "vault"
    result = sync_obsidian(
        outputs_root=str(tmp_path / "btc_icft"),
        vault_root=str(vault),
    )
    assert hasattr(result, "next_action")
    assert isinstance(result.next_action, str)


# ---------------------------------------------------------------------------
# Research loop P24 outputs (5 tests)
# ---------------------------------------------------------------------------

def test_research_loop_writes_p24_plan_json(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path))
    run_research_loop(config)
    assert (tmp_path / "research_loop_plan.json").exists()
    data = json.loads((tmp_path / "research_loop_plan.json").read_text())
    assert "loop_version" in data


def test_research_loop_writes_p24_results_json(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path))
    run_research_loop(config)
    assert (tmp_path / "research_loop_results.json").exists()
    data = json.loads((tmp_path / "research_loop_results.json").read_text())
    # results file is a list of step result dicts
    assert isinstance(data, list)


def test_research_loop_writes_p24_next_action_json(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path))
    run_research_loop(config)
    assert (tmp_path / "research_loop_next_action.json").exists()
    data = json.loads((tmp_path / "research_loop_next_action.json").read_text())
    assert "next_action" in data


def test_research_loop_writes_p24_report_md(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path))
    run_research_loop(config)
    assert (tmp_path / "research_loop_report.md").exists()
    content = (tmp_path / "research_loop_report.md").read_text()
    assert "p24" in content.lower() or "research" in content.lower()


def test_research_loop_writes_p24_events_jsonl(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path))
    run_research_loop(config)
    assert (tmp_path / "events.jsonl").exists()
    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) > 0
    for line in lines:
        event = json.loads(line)
        assert "source" in event
        assert "loop_version" in event or "event" in event
