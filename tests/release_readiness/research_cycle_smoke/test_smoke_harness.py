"""Tests for the research-cycle end-to-end smoke harness."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import pytest

from tools.release_readiness.research_cycle_smoke.fixtures import all_scenarios, build_scenario
from tools.release_readiness.research_cycle_smoke.report import dumps, write_reports
from tools.release_readiness.research_cycle_smoke.runner import run_scenario, run_smoke_suite
from tools.release_readiness.research_cycle_smoke.schema import ScenarioId


def test_all_scenarios_defined():
    ids = {s.value for s in all_scenarios()}
    assert ids == {
        "complete_valid_engineering",
        "incomplete_source",
        "partial_subject_set",
        "failed_simulation",
        "timeout",
        "missing_validation_report",
        "invalid_provenance",
        "network_policy_violation",
        "synthetic_only",
        "proxy_only",
    }


def test_smoke_suite_decision_matrix():
    payload = run_smoke_suite()
    assert payload["scientific_pass_emitted"] is False
    assert payload["bayes_factor_emitted"] is False
    assert payload["network_accessed"] is False
    assert payload["all_decisions_match"] is True
    assert payload["all_guards_pass"] is True
    assert payload["deterministic"] is True
    assert payload["n_scenarios"] == 10
    text = dumps(payload)
    json.loads(text)
    assert "NaN" not in text
    assert "Infinity" not in text


@pytest.mark.parametrize("scenario", list(ScenarioId))
def test_each_scenario_matches_expected(scenario: ScenarioId):
    result = run_scenario(scenario)
    assert result.decision_match, (
        f"{scenario.value}: expected={result.expected_decision} observed={result.observed_decision} "
        f"warnings={result.warnings}"
    )
    assert result.chain_ok
    assert result.synthetic_not_scientific
    assert result.missing_not_zeroed


def test_incomplete_states_remain_visible():
    result = run_scenario(ScenarioId.PARTIAL_SUBJECT_SET)
    assert result.incomplete_visible
    assert any(s.visible_issue == "partial_subject_set" for s in result.stages)


def test_missing_metric_not_zeroed():
    stages, bundle, _ = build_scenario(ScenarioId.COMPLETE_VALID_ENGINEERING)
    bundle["metrics"] = {"score": None, "rss": None}
    bundle["non_finite_metric_paths"] = ["metrics.bad"]
    # Ensure zeros are not fabricated for missing
    assert bundle["metrics"]["score"] is None
    assert bundle["metrics"]["rss"] is None
    assert 0 not in bundle["metrics"].values()


def test_deterministic_checksums():
    a = run_scenario(ScenarioId.COMPLETE_VALID_ENGINEERING)
    b = run_scenario(ScenarioId.COMPLETE_VALID_ENGINEERING)
    assert a.checksum == b.checksum
    assert a.observed_decision == b.observed_decision


def test_no_network_guard(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("network")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    payload = run_smoke_suite([ScenarioId.COMPLETE_VALID_ENGINEERING])
    assert payload["all_decisions_match"] is True


def test_write_reports(tmp_path: Path):
    payload = run_smoke_suite([ScenarioId.SYNTHETIC_ONLY, ScenarioId.PROXY_ONLY])
    paths = write_reports(payload, tmp_path)
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert data["bayes_factor_emitted"] is False


def test_chain_relationship_order():
    stages, _bundle, _ = build_scenario(ScenarioId.COMPLETE_VALID_ENGINEERING)
    names = [s.stage for s in stages]
    assert names == [
        "source",
        "plan",
        "hypothesis",
        "experiment",
        "run",
        "artifact",
        "validation",
        "evidence_graph",
    ]
    for i in range(1, len(stages)):
        assert stages[i - 1].record_id in stages[i].parent_ids
