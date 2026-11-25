from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_two_claims_with_identical_content_are_flagged_duplicate(build_ledger_db):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    payload = {"claim_id": "CLM-DUP", "evidence_ids": ["EV-1"], "evidence_class": "descriptive_empirical", "statement": "identical text"}
    records = [
        {"record_id": "CLM-A", "cycle_id": "CYC-1", "record_type": "claim", "payload": payload},
        {"record_id": "CLM-B", "cycle_id": "CYC-1", "record_type": "claim", "payload": payload},
    ]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    duplicates = report["duplicates_and_superseded"]["duplicate_ledger_records"]
    assert len(duplicates) == 1
    assert duplicates[0]["record_ids"] == ["CLM-A", "CLM-B"]


def test_distinct_claims_are_not_flagged_duplicate(build_ledger_db):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [
        {"record_id": "CLM-A", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-A", "evidence_ids": [], "evidence_class": "descriptive_empirical"}},
        {"record_id": "CLM-B", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-B", "evidence_ids": [], "evidence_class": "speculation"}},
    ]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)
    assert report["duplicates_and_superseded"]["duplicate_ledger_records"] == []


def test_a_claim_revising_another_via_parent_ids_is_superseded(build_ledger_db):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [
        {"record_id": "CLM-OLD", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-OLD", "evidence_ids": [], "evidence_class": "descriptive_empirical"}},
        {"record_id": "CLM-NEW", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-NEW", "evidence_ids": [], "evidence_class": "descriptive_empirical", "parent_ids": ["CLM-OLD"]}},
    ]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    superseded = report["duplicates_and_superseded"]["superseded_ledger_records"]
    assert len(superseded) == 1
    assert superseded[0] == {"superseded_record_id": "CLM-OLD", "superseded_by_record_id": "CLM-NEW", "record_type": "claim"}
