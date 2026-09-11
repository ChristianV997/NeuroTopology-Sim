from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_artifact_report_with_no_matching_ledger_run_is_an_orphan(build_ledger_db, write_json, tmp_path):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    db_path = build_ledger_db(cycles, [])  # no run_record in the ledger at all

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "report1.json").write_text(
        '{"status": "COMPLETE", "artifact_manifest": {"artifacts": []}, "provenance": {"run_id": "RUN-ORPHAN"}, "evidence": {"evidence_class": "engineering_fact", "synthetic": false}, "diagnostics": {}}',
        encoding="utf-8",
    )

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)

    orphans = report["artifacts"]["orphan_artifact_reports"]
    assert len(orphans) == 1
    assert orphans[0]["run_id"] == "RUN-ORPHAN"
    # An orphan report on its own is an "incomplete" finding, not a hard
    # blocker (there's no run/claim it's blocking).
    assert report["blockers"] == []
    assert report["exit_code"] == 1


def test_matching_run_id_is_not_an_orphan(build_ledger_db, tmp_path):
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [{"record_id": "RUN-1", "cycle_id": "CYC-1", "record_type": "run_record", "payload": {"run_record_id": "RUN-1", "evidence_class": "engineering_fact"}}]
    db_path = build_ledger_db(cycles, records)

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "report1.json").write_text(
        '{"status": "COMPLETE", "artifact_manifest": {"artifacts": []}, "provenance": {"run_id": "RUN-1"}, "evidence": {"evidence_class": "engineering_fact", "synthetic": false}, "diagnostics": {}}',
        encoding="utf-8",
    )

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)

    assert report["artifacts"]["orphan_artifact_reports"] == []
    assert report["artifacts"]["runs_without_artifacts"] == []
