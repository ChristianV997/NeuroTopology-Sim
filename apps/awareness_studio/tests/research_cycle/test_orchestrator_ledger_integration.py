from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from awareness_studio.orchestrator import Orchestrator
from awareness_studio.orchestrator.orchestrator import OrchestratorConfig
from awareness_studio.research_cycle import ImmutableCycleError, ResearchCycleLedger


NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_dry_run_is_planning_only_and_ledger_is_authoritative(tmp_path: Path):
    result = Orchestrator().run(config=OrchestratorConfig(dry_run=True, seed=9, out_base_dir=tmp_path), _now=NOW)
    assert result.execution_state == "REVIEW_REQUIRED"
    assert result.scientific_evidence is False
    assert result.ledger_path == result.out_dir / "research_cycle.sqlite3"

    ledger = ResearchCycleLedger(result.ledger_path)
    events = ledger.events(result.run_id)
    records = ledger.records(result.run_id)
    assert ledger.recover(result.run_id)
    assert any(event.event_type == "execution_outcome" and event.status == "BLOCKED" for event in events)
    assert any(event.event_type == "release_review" and event.payload["execution_allowed"] is False for event in events)
    assert {record.record_type for record in records} == {"source_snapshot", "evidence_record", "claim", "hypothesis", "experiment_spec"}

    execution = next(event for event in events if event.event_type == "execution_outcome")
    assert all("metrics" not in item for item in execution.payload["results"])
    assert all(item["status"] == "PLANNING_ONLY" for item in execution.payload["results"])
    assert all(item["scientific_evidence"] is False for item in execution.payload["results"])
    assert "PASS" not in (result.out_dir / "Report.md").read_text(encoding="utf-8")


def test_live_execution_is_explicitly_not_implemented_without_run_record(tmp_path: Path):
    result = Orchestrator().run(config=OrchestratorConfig(dry_run=False, seed=4, out_base_dir=tmp_path), _now=NOW)
    assert result.execution_state == "NOT_IMPLEMENTED"
    assert result.scientific_evidence is False
    ledger = ResearchCycleLedger(result.ledger_path)
    execution = next(event for event in ledger.events(result.run_id) if event.event_type == "execution_outcome")
    assert execution.status == "NOT_IMPLEMENTED"
    assert all(item["status"] == "NOT_IMPLEMENTED" for item in execution.payload["results"])
    assert not any(record.record_type == "run_record" for record in ledger.records(result.run_id))


def test_repeated_dry_run_is_idempotent_and_keeps_checks_review_required(tmp_path: Path):
    config = OrchestratorConfig(dry_run=True, seed=12, out_base_dir=tmp_path)
    first = Orchestrator().run(config=config, _now=NOW)
    second = Orchestrator().run(config=config, _now=NOW)
    assert first.run_id == second.run_id
    ledger = ResearchCycleLedger(first.ledger_path)
    events = ledger.events(first.run_id)
    assert len({event.event_id for event in events}) == len(events)
    validation = [event for event in events if event.event_type == "validation_outcome"]
    assert len(validation) == 1
    assert validation[0].status == "REVIEW_REQUIRED"


def test_ledger_interrupted_execution_recovery_and_freeze(tmp_path: Path):
    ledger = ResearchCycleLedger(tmp_path / "recovery.sqlite3")
    ledger.create_cycle("cycle-recovery")
    with pytest.raises(RuntimeError):
        with ledger._transaction() as connection:
            ledger._append_event_connection(connection, cycle_id="cycle-recovery", event_type="execution_outcome", producer="test", status="BLOCKED", payload={"interrupted": True})
            raise RuntimeError("interrupted execution")
    assert ledger.recover("cycle-recovery")
    assert [event.sequence for event in ledger.events("cycle-recovery")] == [1]
    ledger.finalize_cycle("cycle-recovery")
    with pytest.raises(ImmutableCycleError):
        ledger.append_event("cycle-recovery", "execution_outcome", producer="test", status="FAILED", payload={})


def test_planning_artifacts_are_not_evidence_or_release_authorization(tmp_path: Path):
    result = Orchestrator().run(config=OrchestratorConfig(dry_run=True, out_base_dir=tmp_path), _now=NOW)
    ledger = ResearchCycleLedger(result.ledger_path)
    artifact = next(event for event in ledger.events(result.run_id) if event.event_type == "planning_artifact")
    review = next(event for event in ledger.events(result.run_id) if event.event_type == "release_review")
    assert artifact.payload["planning_only"] is True
    assert artifact.payload["scientific_evidence"] is False
    assert review.payload["execution_allowed"] is False
    assert review.payload["release_state"] == "REVIEW_REQUIRED"
    json.dumps(result.to_dict(), allow_nan=False)
