"""
Tests for the local autonomous research team runtime (P23).

38 tests covering:
- Research loop core (19 tests)
- Makefile/docs presence (3 tests)
- OpenClaw skills (3 tests)
- Ollama client (3 tests)
- Event log (4 tests)
- Safe runner (3 tests)
- Agent roles (3 tests)
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_agents.command_guard import CommandPolicy, evaluate_command
from tools.local_agents.event_log import append_event, event_hash, read_events
from tools.local_agents.research_loop import (
    ResearchLoopConfig,
    run_research_loop,
    _LOOP_VERSION,
    _GUARDRAILS,
)
from tools.local_agents.safe_runner import run_safe_command, run_command_sequence
from tools.local_agents.agent_roles import load_agent_roster


# ---------------------------------------------------------------------------
# Research loop core (19 tests)
# ---------------------------------------------------------------------------

def test_loop_version_is_p23():
    assert _LOOP_VERSION == "p23.0"


def test_guardrails_all_false():
    for k, v in _GUARDRAILS.items():
        assert v is False, f"Guardrail {k} must be False"


def test_dry_run_returns_result(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path / "out"))
    result = run_research_loop(config)
    assert result.dry_run is True
    assert result.loop_version == _LOOP_VERSION
    assert result.error == ""


def test_dry_run_no_real_execution(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path / "out"))
    result = run_research_loop(config)
    assert result.guardrails["executes_real_data"] is False
    assert result.guardrails["downloads_data"] is False


def test_dry_run_writes_output_files(tmp_path):
    config = ResearchLoopConfig(dry_run=True, out_dir=str(tmp_path / "out"))
    result = run_research_loop(config)
    written = [Path(f).name for f in result.output_files]
    assert "loop_state.json" in written
    assert "loop_next_action.json" in written
    assert "loop_guardrails.json" in written
    assert "loop_report.md" in written


def test_dry_run_writes_events_log(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    events_path = out / "loop_events.jsonl"
    assert events_path.exists()
    events = read_events(events_path)
    assert len(events) >= 2
    event_names = [e.get("event") for e in events]
    assert "loop_start" in event_names
    assert "loop_end" in event_names


def test_loop_events_have_source(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    events = read_events(out / "loop_events.jsonl")
    for e in events:
        assert e.get("source") == "p23_research_loop"


def test_loop_state_json_has_required_fields(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    state = json.loads((out / "loop_state.json").read_text())
    assert "loop_version" in state
    assert "dry_run" in state
    assert "steps_total" in state
    assert "steps_completed" in state


def test_loop_guardrails_file_all_false(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    guardrails = json.loads((out / "loop_guardrails.json").read_text())
    for k, v in guardrails.items():
        assert v is False, f"Guardrail {k} must be False in output file"


def test_loop_next_action_json_has_required_fields(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    next_action = json.loads((out / "loop_next_action.json").read_text())
    assert "next_action" in next_action
    assert "next_command" in next_action
    assert "warnings" in next_action


def test_blocked_command_not_executed(tmp_path):
    executed = []
    def fake_runner(parts, cwd, timeout):
        executed.append(parts)
        return 0, "ok", ""

    config = ResearchLoopConfig(
        dry_run=False,
        out_dir=str(tmp_path / "out"),
        safe_commands=["wget https://example.com/data.zip"],
    )
    result = run_research_loop(config, _command_runner=fake_runner)
    # wget is blocked — fake_runner should never be called
    assert len(executed) == 0
    assert result.steps_blocked >= 1


def test_allowed_command_executed_in_non_dry_run(tmp_path):
    executed = []
    def fake_runner(parts, cwd, timeout):
        executed.append(parts)
        return 0, "ok", ""

    config = ResearchLoopConfig(
        dry_run=False,
        out_dir=str(tmp_path / "out"),
        safe_commands=["make ds005620-e2e-mock"],
    )
    run_research_loop(config, _command_runner=fake_runner)
    assert len(executed) == 1


def test_max_commands_respected(tmp_path):
    config = ResearchLoopConfig(
        dry_run=True,
        out_dir=str(tmp_path / "out"),
        max_commands=3,
        safe_commands=["make ds005620-e2e-mock"] * 10,
    )
    result = run_research_loop(config)
    assert result.steps_run <= 3


def test_once_runs_only_first_command(tmp_path):
    config = ResearchLoopConfig(
        dry_run=True,
        out_dir=str(tmp_path / "out"),
        once=True,
        safe_commands=["make ds005620-e2e-mock", "make validate-ds005620-e2e"],
    )
    result = run_research_loop(config)
    assert result.steps_run == 1


def test_continue_on_error_runs_all(tmp_path):
    executed = []
    def fake_runner(parts, cwd, timeout):
        executed.append(parts)
        return 1, "", "fail"  # always fail

    config = ResearchLoopConfig(
        dry_run=False,
        out_dir=str(tmp_path / "out"),
        continue_on_error=True,
        safe_commands=["make ds005620-e2e-mock", "make validate-ds005620-e2e"],
    )
    run_research_loop(config, _command_runner=fake_runner)
    assert len(executed) == 2


def test_stop_on_error_stops_early(tmp_path):
    executed = []
    def fake_runner(parts, cwd, timeout):
        executed.append(parts)
        return 1, "", "fail"

    config = ResearchLoopConfig(
        dry_run=False,
        out_dir=str(tmp_path / "out"),
        continue_on_error=False,
        safe_commands=["make ds005620-e2e-mock", "make validate-ds005620-e2e"],
    )
    run_research_loop(config, _command_runner=fake_runner)
    assert len(executed) == 1


def test_loop_report_md_exists(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    assert (out / "loop_report.md").exists()


def test_loop_report_md_has_guardrails_section(tmp_path):
    out = tmp_path / "out"
    config = ResearchLoopConfig(dry_run=True, out_dir=str(out))
    run_research_loop(config)
    content = (out / "loop_report.md").read_text()
    assert "Guardrails" in content
    assert "executes_real_data" in content


def test_loop_result_has_auto_push_git_false():
    config = ResearchLoopConfig(dry_run=True, out_dir="/tmp/test_p23_loop_result")
    result = run_research_loop(config)
    assert result.guardrails.get("auto_pushes_git") is False
    assert result.guardrails.get("auto_merges_pr") is False
    assert result.guardrails.get("auto_closes_pr") is False


# ---------------------------------------------------------------------------
# Makefile/docs presence (3 tests)
# ---------------------------------------------------------------------------

def test_makefile_has_local_agent_targets():
    makefile = _REPO_ROOT / "Makefile"
    content = makefile.read_text()
    assert "local-agent-loop-dry-run" in content
    assert "local-agent-loop-once" in content
    assert "local-agent-policy-check" in content
    assert "sync-obsidian" in content


def test_doc_local_autonomous_research_team_exists():
    doc = _REPO_ROOT / "docs" / "local_autonomous_research_team.md"
    assert doc.exists()
    content = doc.read_text()
    assert "P23" in content
    assert "guardrails" in content.lower()


def test_doc_ollama_openclaw_obsidian_setup_exists():
    doc = _REPO_ROOT / "docs" / "ollama_openclaw_obsidian_setup.md"
    assert doc.exists()
    content = doc.read_text()
    assert "Ollama" in content
    assert "Obsidian" in content
    assert "OpenClaw" in content


# ---------------------------------------------------------------------------
# OpenClaw skills (3 tests)
# ---------------------------------------------------------------------------

def test_openclaw_skills_directory_exists():
    skills_dir = _REPO_ROOT / ".openclaw" / "skills"
    assert skills_dir.exists()
    assert skills_dir.is_dir()


def test_all_six_skills_present():
    skills_dir = _REPO_ROOT / ".openclaw" / "skills"
    expected = [
        "sciencer-runtime",
        "sciencer-ontology-guard",
        "sciencer-dataset-operator",
        "sciencer-pr-manager",
        "obsidian-ledger",
        "safety-watcher",
    ]
    for skill in expected:
        skill_md = skills_dir / skill / "SKILL.md"
        assert skill_md.exists(), f"Missing SKILL.md for {skill}"


def test_safety_watcher_skill_lists_forbidden_substrings():
    skill_path = _REPO_ROOT / ".openclaw" / "skills" / "safety-watcher" / "SKILL.md"
    content = skill_path.read_text()
    assert "wget" in content
    assert "curl" in content
    assert "dandi download" in content
    assert "git push" in content


# ---------------------------------------------------------------------------
# Ollama client (3 tests)
# ---------------------------------------------------------------------------

def test_ollama_client_imports():
    from tools.local_agents.ollama_client import OllamaClient
    client = OllamaClient()
    assert client.base_url == "http://localhost:11434"
    assert client.default_model == "llama3"


def test_ollama_is_available_returns_bool_when_offline():
    from tools.local_agents.ollama_client import OllamaClient
    client = OllamaClient(base_url="http://localhost:19999")
    result = client.is_available()
    assert isinstance(result, bool)


def test_ollama_chat_returns_error_dict_when_offline():
    from tools.local_agents.ollama_client import OllamaClient
    client = OllamaClient(base_url="http://localhost:19999")
    result = client.chat("Hello")
    assert "error" in result
    assert result["done"] is False


# ---------------------------------------------------------------------------
# Event log (4 tests)
# ---------------------------------------------------------------------------

def test_event_hash_deterministic():
    ev = {"event": "test", "value": 42}
    assert event_hash(ev) == event_hash(ev)


def test_event_hash_changes_on_different_input():
    ev1 = {"event": "test", "value": 1}
    ev2 = {"event": "test", "value": 2}
    assert event_hash(ev1) != event_hash(ev2)


def test_append_and_read_events(tmp_path):
    log = tmp_path / "events.jsonl"
    append_event(log, {"event": "a", "x": 1})
    append_event(log, {"event": "b", "x": 2})
    events = read_events(log)
    assert len(events) == 2
    assert events[0]["event"] == "a"
    assert events[1]["event"] == "b"


def test_read_events_returns_empty_for_missing_file(tmp_path):
    events = read_events(tmp_path / "no_such_file.jsonl")
    assert events == []


# ---------------------------------------------------------------------------
# Safe runner (3 tests)
# ---------------------------------------------------------------------------

def test_safe_runner_blocks_wget():
    result = run_safe_command("wget https://example.com")
    assert result.allowed is False
    assert result.exit_code is None


def test_safe_runner_dry_run_does_not_call_subprocess():
    called = []
    def fake(parts, cwd, timeout):
        called.append(parts)
        return 0, "ok", ""

    result = run_safe_command("make ds005620-e2e-mock", dry_run=True, _runner=fake)
    assert result.dry_run is True
    assert len(called) == 0


def test_safe_runner_sequence_continues_on_error():
    def fake(parts, cwd, timeout):
        return 1, "", "fail"

    results = run_command_sequence(
        ["make ds005620-e2e-mock", "make validate-ds005620-e2e"],
        cwd=None,
        dry_run=False,
        continue_on_error=True,
        _runner=fake,
    )
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Agent roles (3 tests)
# ---------------------------------------------------------------------------

def test_agent_roster_has_eight_roles():
    roles = load_agent_roster()
    assert len(roles) == 8


def test_real_data_executor_not_safe_to_auto_run():
    roles = load_agent_roster()
    real_exec = next(r for r in roles if r.role_id == "real_data_executor")
    assert real_exec.safe_to_auto_run is False
    assert real_exec.requires_human_review is True


def test_all_roles_have_required_fields():
    roles = load_agent_roster()
    for role in roles:
        assert role.role_id
        assert role.display_name
        assert isinstance(role.safe_to_auto_run, bool)
        assert isinstance(role.requires_human_review, bool)
        assert isinstance(role.requires_real_data, bool)
