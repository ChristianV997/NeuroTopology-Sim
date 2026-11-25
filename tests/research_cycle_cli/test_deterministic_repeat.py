from __future__ import annotations

import json

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_repeated_compile_is_byte_identical(build_ledger_db, write_json, tmp_path):
    cycles = [{"cycle_id": "CYC-1", "status": "BLOCKED", "finalized": False, "metadata": {}}]
    records = [{"record_id": "CLM-1", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": [], "evidence_class": "descriptive_empirical"}}]
    db_path = build_ledger_db(cycles, records)
    claim_gate_path = write_json([{"claim_id": "CLM-1", "decision": "CLAIM_REQUIRES_REVIEW", "reason_codes": ["MISSING_PROVENANCE"]}])

    report1 = compile_inspection(ledger_db=db_path, claim_gate_report=claim_gate_path, artifact_reports=None, artifacts_dir=None, now=NOW)
    report2 = compile_inspection(ledger_db=db_path, claim_gate_report=claim_gate_path, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert json.dumps(report1, sort_keys=True, allow_nan=False) == json.dumps(report2, sort_keys=True, allow_nan=False)
    assert report1["report_sha256"] == report2["report_sha256"]
    assert report1["exit_code"] == 3


def test_omitted_now_only_changes_generated_at_and_checksum(build_ledger_db):
    db_path = build_ledger_db([{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}], [])

    report1 = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None)
    report2 = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None)

    volatile = {"generated_at", "report_sha256"}
    stable1 = {k: v for k, v in report1.items() if k not in volatile}
    stable2 = {k: v for k, v in report2.items() if k not in volatile}
    assert stable1 == stable2
