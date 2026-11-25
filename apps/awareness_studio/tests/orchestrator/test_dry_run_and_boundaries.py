"""End-to-end boundaries: dry-run outputs, run-card ingestion, ledger projection, result invariants."""
from __future__ import annotations

import dataclasses
import json
import socket
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from awareness_studio.orchestrator import Orchestrator, OrchestratorResult
from awareness_studio.orchestrator.event_log import EventLog
from awareness_studio.orchestrator.orchestrator import DRY_RUN_STATES, EvidenceState, OrchestratorConfig
from awareness_studio.research_cycle import ResearchCycleLedger
from tests.orchestrator.conftest import LEAK_SENTINEL, make_identified

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_ALLOWED_STAGE_STATES = {state.value for state in DRY_RUN_STATES}


def _reject_constant(name):
    raise ValueError(f"non-finite JSON constant: {name}")


def _write_card(directory: Path, name: str, payload) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload) if not isinstance(payload, str) else payload, encoding="utf-8")


def _run(tmp_path: Path, card_dir: Path | None = None) -> OrchestratorResult:
    cfg = OrchestratorConfig(dry_run=True, run_cards_dir=card_dir, out_base_dir=tmp_path / "out")
    return Orchestrator().run(config=cfg, _now=_NOW)


def _ledger_dump(path: Path) -> str:
    """Every row of every table, including rows still in the SQLite WAL.

    A raw byte search of the main database file misses WAL-resident payloads, so it
    cannot prove absence. Reading rows through SQLite sees the committed state.
    """
    connection = sqlite3.connect(path)
    try:
        parts = []
        for (table,) in connection.execute("select name from sqlite_master where type='table'"):
            for row in connection.execute(f'select * from "{table}"'):
                parts.append(json.dumps([str(value) for value in row]))
        return "\n".join(parts)
    finally:
        connection.close()


def _all_text(result: OrchestratorResult) -> str:
    pieces = [path.read_bytes().decode("latin1") for path in result.out_dir.rglob("*")
              if path.is_file() and path.suffix != ".sqlite3" and not path.name.endswith("-wal")]
    pieces.append(_ledger_dump(result.ledger_path))
    return "\n".join(pieces)


# ── dry-run output ───────────────────────────────────────────────────────────

def test_dry_run_result_is_planning_with_scientific_pass_false_and_null_bayes_factor(tmp_path):
    result = _run(tmp_path)
    assert result.evidence_state == EvidenceState.PLANNING.value
    assert result.scientific_pass is False
    assert result.formal_bayes_factor is None
    assert result.scientific_evidence is False
    payload = result.to_dict()
    assert payload["scientific_pass"] is False
    assert payload["formal_bayes_factor"] is None
    assert payload["evidence_state"] == "planning"


def test_every_dry_run_stage_emits_only_planning_or_review_states(tmp_path):
    result = _run(tmp_path)
    events = EventLog(result.out_dir).load_all()
    ok_events = [event for event in events if event.status == "ok"]
    assert {event.stage for event in ok_events} == set(result.stages_completed)
    for event in ok_events:
        assert event.payload.get("evidence_state") in _ALLOWED_STAGE_STATES, event.stage


def test_dry_run_ledger_projection_carries_no_non_planning_evidence_state(tmp_path):
    result = _run(tmp_path)
    ledger = ResearchCycleLedger(result.ledger_path)
    for event in ledger.events(result.run_id):
        state = event.payload.get("evidence_state") if isinstance(event.payload, dict) else None
        if state is not None:
            assert state in _ALLOWED_STAGE_STATES, event.event_type


def test_dry_run_report_and_evidence_log_show_null_metrics_and_invariants(tmp_path):
    result = _run(tmp_path)
    report = (result.out_dir / "Report.md").read_text(encoding="utf-8")
    evidence_log = (result.out_dir / "EvidenceLogDraft.md").read_text(encoding="utf-8")
    assert "**Scientific pass:** `false`" in report
    assert "**formal Bayes factor:** `null`" in report
    assert "**Scientific pass:** `false`" in evidence_log
    assert "I_mean" not in evidence_log


def test_dry_run_json_artifacts_are_finite(tmp_path):
    result = _run(tmp_path)
    for name in ("GraphUpdate.json", "OpsQueueItem.json"):
        json.loads((result.out_dir / name).read_text(encoding="utf-8"), parse_constant=_reject_constant)
    for line in (result.out_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line, parse_constant=_reject_constant)


def test_dry_run_makes_no_network_call(tmp_path, monkeypatch):
    calls = []

    def _forbidden(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("network access attempted")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    _run(tmp_path)
    assert calls == []


# ── run-card ingestion: synthetic, missing provenance, malformed, admitted ───

def test_synthetic_run_card_metrics_never_reach_outputs_or_ledger(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "synthetic.run.json", make_identified(
        run_id="a" * 16, data_mode="synthetic", evidence_class="synthetic_demonstration"))
    result = _run(tmp_path, cards)
    assert str(LEAK_SENTINEL) not in _all_text(result)
    assert str(LEAK_SENTINEL) not in _ledger_dump(result.ledger_path)


def test_empirical_card_without_provenance_is_incomplete_and_leaks_nothing(tmp_path):
    cards = tmp_path / "cards"
    card = make_identified(run_id="b" * 16, evidence_class="descriptive_empirical")
    del card["source_identity"]
    _write_card(cards, "noprov.run.json", card)
    result = _run(tmp_path, cards)
    summary = EventLog(result.out_dir).load_all()
    ingest = next(e for e in summary if e.stage == "ingest_inputs" and e.status == "ok")
    entry = ingest.payload["run_cards"][0]
    assert entry["evidence_state"] == "incomplete"
    assert entry["metrics"] is None
    assert "source_identity" in entry["missing_identities"]
    assert str(LEAK_SENTINEL) not in _all_text(result)


def test_malformed_and_nonfinite_run_cards_are_invalid_and_never_admitted(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "broken.run.json", "{not valid json")
    # Python's json module accepts the literal NaN, so this card parses. It is still
    # classified invalid, and its metric is withheld. run_cards_loaded counts parses,
    # not admissions.
    _write_card(cards, "nan.run.json", '{"run_id": "c", "metrics": {"x": NaN}}')
    result = _run(tmp_path, cards)
    ingest = next(e for e in EventLog(result.out_dir).load_all() if e.stage == "ingest_inputs" and e.status == "ok")
    assert ingest.payload["run_cards_loaded"] == 1
    assert ingest.payload["run_cards_evidence_ready"] == 0
    states = [entry["evidence_state"] for entry in ingest.payload["run_cards"]]
    assert states == ["invalid", "invalid"]
    assert all(entry["metrics"] is None for entry in ingest.payload["run_cards"])


def test_fully_identified_card_is_not_admitted_in_a_dry_run(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "ok.run.json", make_identified(run_id="d" * 16))
    result = _run(tmp_path, cards)
    ingest = next(e for e in EventLog(result.out_dir).load_all() if e.stage == "ingest_inputs" and e.status == "ok")
    assert ingest.payload["run_cards_evidence_ready"] == 0
    entry = ingest.payload["run_cards"][0]
    assert entry["evidence_state"] == "review_required"
    assert entry["evidence_ready"] is False
    assert "dry_run_no_admission" in entry["reasons"]
    assert entry["metrics"] is None
    assert str(LEAK_SENTINEL) not in _all_text(result)


def test_live_run_admits_identified_metric_to_event_log_but_never_to_ledger(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "ok.run.json", make_identified(run_id="d" * 16))
    cfg = OrchestratorConfig(dry_run=False, run_cards_dir=cards, out_base_dir=tmp_path / "out")
    result = Orchestrator().run(config=cfg, _now=_NOW)
    assert result.evidence_state == EvidenceState.BLOCKED.value
    assert result.scientific_pass is False
    ingest = next(e for e in EventLog(result.out_dir).load_all() if e.stage == "ingest_inputs" and e.status == "ok")
    assert ingest.payload["run_cards_evidence_ready"] == 1
    entry = ingest.payload["run_cards"][0]
    assert entry["evidence_state"] == "engineering"
    assert entry["evidence_ready"] is True
    assert entry["metrics"] == {"I_mean": LEAK_SENTINEL}
    # The event log may carry the admitted value; the ledger boundary is stricter.
    assert str(LEAK_SENTINEL) in (result.out_dir / "events.jsonl").read_text(encoding="utf-8")
    assert str(LEAK_SENTINEL) not in _ledger_dump(result.ledger_path)


# ── result invariants ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"scientific_pass": True}, "scientific_pass"),
        ({"formal_bayes_factor": 0.5}, "formal_bayes_factor"),
        ({"scientific_evidence": True}, "scientific_evidence"),
        ({"dry_run": True, "evidence_state": "empirical"}, "not permitted"),
        ({"dry_run": True, "evidence_state": "engineering"}, "not permitted"),
        ({"dry_run": False, "evidence_state": "planning"}, "not permitted"),
        ({"dry_run": True, "evidence_state": "not_a_state"}, "not_a_state"),
    ],
)
def test_result_construction_rejects_violated_invariants(tmp_path, kwargs, message):
    base = {"run_id": "e" * 16, "out_dir": tmp_path, "stages_completed": [], "stages_failed": [],
            "dry_run": True}
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        OrchestratorResult(**base)


def test_result_defaults_follow_dry_run(tmp_path):
    dry = OrchestratorResult(run_id="f" * 16, out_dir=tmp_path, stages_completed=[], stages_failed=[], dry_run=True)
    live = OrchestratorResult(run_id="f" * 16, out_dir=tmp_path, stages_completed=[], stages_failed=[], dry_run=False)
    assert dry.evidence_state == "planning"
    assert live.evidence_state == "blocked"


def test_dry_run_with_a_failed_stage_reports_review_required_not_a_pass(tmp_path, monkeypatch):
    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated stage failure")

    monkeypatch.setattr(Orchestrator, "_stage_propose_hypotheses", _boom)
    result = _run(tmp_path)
    assert result.stages_failed == ["propose_hypotheses"]
    assert result.evidence_state == EvidenceState.REVIEW_REQUIRED.value
    assert result.scientific_pass is False


def test_result_is_frozen_so_invariants_cannot_be_bypassed_after_construction(tmp_path):
    result = _run(tmp_path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.scientific_pass = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.evidence_state = EvidenceState.EMPIRICAL.value


# ── dry-run admission, run-id basis, seeded records, hostile inputs ─────────

def test_dry_run_stage_result_with_metrics_is_stripped_and_stays_planning():
    item = {"spec_id": "exp_0001_001", "status": "COMPLETED", "metrics": {"I_mean": LEAK_SENTINEL}}
    admitted = Orchestrator._admit_result(item, True)
    assert admitted["metrics"] is None
    assert admitted["evidence_state"] == "planning"
    assert str(LEAK_SENTINEL) not in json.dumps(admitted)


def test_live_stage_result_without_identity_withholds_its_metrics():
    item = {"spec_id": "exp_0001_001", "status": "COMPLETED", "metrics": {"I_mean": LEAK_SENTINEL}}
    admitted = Orchestrator._admit_result(item, False)
    assert admitted["metrics"] is None
    assert admitted["evidence_state"] == "incomplete"


def test_different_run_card_sets_never_share_an_output_directory(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    _write_card(first, "x.run.json", make_identified(run_id="a" * 16))
    _write_card(second, "x.run.json", make_identified(run_id="b" * 16))
    run_a = _run(tmp_path, first)
    run_b = _run(tmp_path, second)
    assert run_a.run_id != run_b.run_id
    assert run_a.out_dir != run_b.out_dir


def test_run_id_is_stable_for_the_same_card_set_and_distinct_from_no_cards(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "x.run.json", make_identified(run_id="a" * 16))
    twin = tmp_path / "twin"
    _write_card(twin, "x.run.json", make_identified(run_id="a" * 16))

    def run_id(directory):
        return Orchestrator._make_run_id(OrchestratorConfig(dry_run=True, run_cards_dir=directory), _NOW)

    assert run_id(cards) == run_id(twin)
    assert run_id(cards) != Orchestrator._make_run_id(OrchestratorConfig(dry_run=True), _NOW)


def test_dry_run_planning_ledger_records_never_carry_an_engineering_or_empirical_class(tmp_path):
    result = _run(tmp_path)
    records = ResearchCycleLedger(result.ledger_path).records(result.run_id)
    planning_types = {"claim", "evidence_record", "hypothesis", "experiment_spec"}
    planning = [record for record in records if record.record_type in planning_types]
    # The seeded claim and evidence record, two hypotheses, and two experiment specs.
    assert len(planning) >= 4
    assert {record.evidence_class.value for record in planning} == {"hypothesis"}
    # The configuration snapshot is the only record that keeps engineering_fact.
    snapshots = [record for record in records if record.record_type == "source_snapshot"]
    assert {record.evidence_class.value for record in snapshots} == {"engineering_fact"}


def test_free_text_run_id_is_not_echoed_into_the_ingest_summary(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "text.run.json", make_identified(run_id=f"I_mean={LEAK_SENTINEL}"))
    result = _run(tmp_path, cards)
    ingest = next(e for e in EventLog(result.out_dir).load_all() if e.stage == "ingest_inputs" and e.status == "ok")
    assert ingest.payload["run_cards"][0]["run_id"] is None
    assert ingest.payload["run_cards"][0]["evidence_state"] == "invalid"
    assert str(LEAK_SENTINEL) not in _all_text(result)


def test_oversized_integer_in_a_live_card_is_withheld_and_does_not_fail_the_stage(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "huge.run.json", json.dumps(make_identified(run_id="h" * 16, metrics={"x": 10 ** 400})))
    cfg = OrchestratorConfig(dry_run=False, run_cards_dir=cards, out_base_dir=tmp_path / "out")
    result = Orchestrator().run(config=cfg, _now=_NOW)
    assert result.stages_failed == []
    ingest = next(e for e in EventLog(result.out_dir).load_all() if e.stage == "ingest_inputs" and e.status == "ok")
    assert ingest.payload["run_cards"][0]["metrics"] == {"x": None}


def test_deeply_nested_card_is_rejected_as_malformed_without_failing_the_stage(tmp_path):
    cards = tmp_path / "cards"
    _write_card(cards, "deep.run.json", "[" * 100000 + "]" * 100000)
    result = _run(tmp_path, cards)
    assert result.stages_failed == []
    ingest = next(e for e in EventLog(result.out_dir).load_all() if e.stage == "ingest_inputs" and e.status == "ok")
    assert ingest.payload["run_cards_loaded"] == 0
    assert ingest.payload["run_cards"][0]["evidence_state"] == "invalid"
    assert ingest.payload["run_cards"][0]["reasons"] == ["malformed_artifact:malformed_json"]
