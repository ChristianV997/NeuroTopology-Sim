from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_claim_with_no_evidence_ids_is_missing_provenance(build_ledger_db):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [{"record_id": "CLM-1", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": [], "evidence_class": "descriptive_empirical"}}]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    flagged = report["claims"]["missing_provenance"]
    assert len(flagged) == 1
    assert flagged[0]["claim_id"] == "CLM-1"
    assert "evidence_ids is empty" in flagged[0]["reasons"]
    assert any(b["kind"] == "missing_provenance" for b in report["blockers"])


def test_claim_referencing_a_nonexistent_evidence_record_is_missing_provenance(build_ledger_db):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [{"record_id": "CLM-1", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": ["EV-DOES-NOT-EXIST"], "evidence_class": "descriptive_empirical"}}]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    flagged = report["claims"]["missing_provenance"]
    assert len(flagged) == 1
    assert "unresolved evidence record" in flagged[0]["reasons"][0]


def test_claim_gate_provenance_reason_codes_are_also_surfaced(build_ledger_db, write_json):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [{"record_id": "EV-1", "cycle_id": "CYC-1", "record_type": "evidence_record", "payload": {"evidence_id": "EV-1", "evidence_class": "descriptive_empirical"}},
               {"record_id": "CLM-1", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": ["EV-1"], "evidence_class": "descriptive_empirical"}}]
    db_path = build_ledger_db(cycles, records)
    claim_gate_path = write_json([{"claim_id": "CLM-1", "decision": "CLAIM_PROVENANCE_INVALID", "reason_codes": ["INVALID_PROVENANCE"]}])

    report = compile_inspection(ledger_db=db_path, claim_gate_report=claim_gate_path, artifact_reports=None, artifacts_dir=None, now=NOW)

    flagged = report["claims"]["missing_provenance"]
    assert len(flagged) == 1
    assert "INVALID_PROVENANCE" in flagged[0]["reasons"][0]


def test_fully_provenanced_claim_is_not_flagged(build_ledger_db):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [
        {"record_id": "EV-1", "cycle_id": "CYC-1", "record_type": "evidence_record", "payload": {"evidence_id": "EV-1", "evidence_class": "descriptive_empirical"}},
        {"record_id": "CLM-1", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": ["EV-1"], "evidence_class": "descriptive_empirical"}},
    ]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)
    assert report["claims"]["missing_provenance"] == []
