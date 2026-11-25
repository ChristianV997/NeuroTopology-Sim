from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_blocked_cycle_is_grouped_and_becomes_a_blocker(build_ledger_db):
    cycles = [{"cycle_id": "CYC-BLOCKED", "status": "BLOCKED", "finalized": False, "metadata": {}}]
    db_path = build_ledger_db(cycles, [])

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["cycles"]["groups"]["blocked"] == ["CYC-BLOCKED"]
    assert any(b["kind"] == "cycle_blocked" and b["id"] == "CYC-BLOCKED" for b in report["blockers"])
    assert report["exit_code"] == 3


def test_failed_cycle_is_grouped_and_becomes_a_blocker(build_ledger_db):
    cycles = [{"cycle_id": "CYC-FAILED", "status": "FAILED", "finalized": False, "metadata": {}}]
    db_path = build_ledger_db(cycles, [])

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["cycles"]["groups"]["failed"] == ["CYC-FAILED"]
    assert any(b["kind"] == "cycle_failed" for b in report["blockers"])
    assert report["exit_code"] == 3


def test_active_and_incomplete_cycles_are_not_blockers(build_ledger_db):
    cycles = [
        {"cycle_id": "CYC-ACTIVE", "status": "IN_PROGRESS", "finalized": False, "metadata": {}},
        {"cycle_id": "CYC-PENDING", "status": "PENDING", "finalized": False, "metadata": {}},
    ]
    db_path = build_ledger_db(cycles, [])

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["cycles"]["groups"]["active"] == ["CYC-ACTIVE"]
    assert report["cycles"]["groups"]["incomplete"] == ["CYC-PENDING"]
    assert report["blockers"] == []
    assert report["exit_code"] == 1
