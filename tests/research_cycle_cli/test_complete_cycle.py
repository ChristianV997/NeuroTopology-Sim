from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def _complete_ledger_rows():
    cycles = [{"cycle_id": "CYC-1", "status": "COMPLETED", "finalized": True, "metadata": {}}]
    records = [
        {"record_id": "SS-1", "cycle_id": "CYC-1", "record_type": "source_snapshot", "payload": {"snapshot_id": "SS-1", "evidence_class": "engineering_fact"}},
        {"record_id": "EV-1", "cycle_id": "CYC-1", "record_type": "evidence_record", "payload": {"evidence_id": "EV-1", "source_snapshot_ids": ["SS-1"], "evidence_class": "descriptive_empirical"}},
        {"record_id": "CLM-1", "cycle_id": "CYC-1", "record_type": "claim", "payload": {"claim_id": "CLM-1", "evidence_ids": ["EV-1"], "evidence_class": "descriptive_empirical", "status": "COMPLETED"}},
        {"record_id": "HYP-1", "cycle_id": "CYC-1", "record_type": "hypothesis", "payload": {"hypothesis_id": "HYP-1", "claim_ids": ["CLM-1"], "evidence_class": "hypothesis"}},
        {"record_id": "EXP-1", "cycle_id": "CYC-1", "record_type": "experiment_spec", "payload": {"experiment_id": "EXP-1", "hypothesis_ids": ["HYP-1"], "evidence_class": "engineering_fact"}},
        {"record_id": "RUN-1", "cycle_id": "CYC-1", "record_type": "run_record", "payload": {"run_record_id": "RUN-1", "experiment_id": "EXP-1", "evidence_class": "engineering_fact"}},
        {"record_id": "AM-1", "cycle_id": "CYC-1", "record_type": "artifact_manifest", "payload": {"artifact_manifest_id": "AM-1", "run_record_id": "RUN-1", "evidence_class": "engineering_fact"}},
        {"record_id": "VR-1", "cycle_id": "CYC-1", "record_type": "validation_report", "payload": {"validation_report_id": "VR-1", "artifact_manifest_ids": ["AM-1"], "run_record_id": "RUN-1", "evidence_class": "engineering_fact"}},
    ]
    links = [("CYC-1", "EV-1", "CLM-1"), ("CYC-1", "CLM-1", "HYP-1"), ("CYC-1", "HYP-1", "EXP-1"), ("CYC-1", "EXP-1", "RUN-1"), ("CYC-1", "RUN-1", "AM-1"), ("CYC-1", "AM-1", "VR-1")]
    return cycles, records, links


def test_complete_cycle_has_no_gaps_and_is_clean(build_ledger_db):
    cycles, records, links = _complete_ledger_rows()
    db_path = build_ledger_db(cycles, records, links)

    report = compile_inspection(ledger_db=db_path, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["claims"]["missing_provenance"] == []
    assert report["hypotheses"]["without_experiment"] == []
    assert report["artifacts"]["runs_without_artifacts"] == []
    assert report["artifacts"]["missing_validation"] == []
    assert report["blockers"] == []
    assert "CYC-1" in report["cycles"]["groups"]["frozen"]
    expected_links = {(c, p, ch) for c, p, ch in links}
    actual_links = {(link["cycle_id"], link["parent_id"], link["child_id"]) for link in report["graph"]["links"]}
    assert actual_links == expected_links
    # ledger available and complete; still "incomplete" overall only if
    # claim_gate/artifact sources were never supplied -- exit reflects that.
    assert report["exit_code"] == 1


def test_complete_cycle_with_all_sources_supplied_is_fully_clean(build_ledger_db, tmp_path, write_json):
    cycles, records, links = _complete_ledger_rows()
    db_path = build_ledger_db(cycles, records, links)
    claim_gate_path = write_json({"claim_id": "CLM-1", "decision": "CLAIM_ADMISSIBLE", "severity": "info", "evidence_class": "descriptive_empirical", "provenance_status": "valid", "reason_codes": []})
    artifacts_dir = tmp_path / "artifact_reports"
    artifacts_dir.mkdir()

    report = compile_inspection(ledger_db=db_path, claim_gate_report=claim_gate_path, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)

    assert report["sources"]["ledger_db"]["available"] is True
    assert report["sources"]["claim_gate_report"]["available"] is True
    assert report["sources"]["artifact_reports"]["available"] is False  # empty dir -> no reports found, still "not_provided"-shaped
    assert report["exit_code"] == 1  # the empty artifacts dir still counts as a missing source
