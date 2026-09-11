"""Requirement 11: synthetic and proxy evidence must remain visibly labeled."""
from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_synthetic_only_cycle_evidence_is_counted_separately_and_never_promoted(build_ledger_db):
    cycles = [{"cycle_id": "CYC-SYNTH", "status": "COMPLETED", "finalized": False, "metadata": {}}]
    records = [
        {"record_id": "SS-1", "cycle_id": "CYC-SYNTH", "record_type": "source_snapshot", "payload": {"snapshot_id": "SS-1", "evidence_class": "synthetic_demonstration"}},
        {"record_id": "EV-1", "cycle_id": "CYC-SYNTH", "record_type": "evidence_record", "payload": {"evidence_id": "EV-1", "evidence_class": "synthetic_demonstration"}},
        {"record_id": "CLM-1", "cycle_id": "CYC-SYNTH", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": ["EV-1"], "evidence_class": "synthetic_demonstration"}},
    ]
    db_path = build_ledger_db(cycles, records)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    breakdown = report["evidence_class_breakdown"]["ledger_records"]
    assert breakdown["synthetic_demonstration"] == 3
    assert breakdown["descriptive_empirical"] == 0
    assert breakdown["formal_statistical_evidence"] == 0
    # It has full provenance (evidence_ids resolves), so it is not itself
    # a "missing provenance" finding -- being synthetic is a distinct fact
    # from lacking provenance, and this CLI keeps the two separate.
    assert report["claims"]["missing_provenance"] == []


def test_artifact_report_synthetic_flag_is_kept_in_its_own_bucket(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "synthetic_run.json").write_text(
        '{"status": "COMPLETE", "artifact_manifest": {"artifacts": []}, "provenance": {"run_id": "RUN-SYN"}, "evidence": {"evidence_class": "synthetic_demonstration", "synthetic": true}, "diagnostics": {}}',
        encoding="utf-8",
    )

    report = compile_inspection(ledger_db=None, claim_gate_report=None, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)

    artifact_bucket = report["evidence_class_breakdown"]["artifact_reports"]
    assert artifact_bucket.get("synthetic_demonstration") == 1
    assert "descriptive_empirical" not in artifact_bucket
    report_obj = report["artifacts"]["reports"][0]
    assert report_obj["synthetic"] is True
