"""Requirement: invalid JSON must produce an explicit diagnostic."""
from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_malformed_claim_gate_json_is_a_diagnostic_and_makes_the_run_invalid(tmp_path):
    bad_path = tmp_path / "claims.json"
    bad_path.write_text("{not valid json", encoding="utf-8")

    report = compile_inspection(ledger_db=None, claim_gate_report=bad_path, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["sources"]["claim_gate_report"]["available"] is False
    assert "invalid_json" in report["sources"]["claim_gate_report"]["error"]
    assert any(d["kind"] == "invalid_json" for d in report["diagnostics"])
    assert report["exit_code"] == 2


def test_malformed_artifact_report_json_produces_an_invalid_json_diagnostic(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "broken.json").write_text("{not valid json", encoding="utf-8")

    report = compile_inspection(ledger_db=None, claim_gate_report=None, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)

    kinds = [d["kind"] for d in report["diagnostics"]]
    assert "invalid_json" in kinds
    assert report["exit_code"] == 2  # a per-record parse failure is always treated as invalid


def test_ledger_db_pointing_at_a_non_sqlite_file_is_reported_as_invalid(tmp_path):
    fake_db = tmp_path / "not_a_database.sqlite3"
    fake_db.write_text("this is not a sqlite file", encoding="utf-8")

    report = compile_inspection(ledger_db=fake_db, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["sources"]["ledger_db"]["available"] is False
    assert "sqlite_query_error" in report["sources"]["ledger_db"]["error"] or "sqlite_open_error" in report["sources"]["ledger_db"]["error"]
