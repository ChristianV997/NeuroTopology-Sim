from __future__ import annotations

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_no_sources_supplied_reports_missing_not_invented(tmp_path):
    report = compile_inspection(ledger_db=None, claim_gate_report=None, artifact_reports=None, artifacts_dir=None, now=NOW)

    assert report["sources"]["ledger_db"] == {"available": False, "path": None, "error": "not_provided"}
    assert report["sources"]["claim_gate_report"] == {"available": False, "path": None, "error": "not_provided"}
    assert report["sources"]["artifact_reports"]["available"] is False
    assert report["cycles"]["records"] == []
    assert report["cycles"]["groups"] == {"frozen": [], "active": [], "blocked": [], "failed": [], "incomplete": [], "other": []}
    assert report["blockers"] == []
    assert report["exit_code"] == 1  # incomplete: nothing was supplied, but nothing is invalid or blocked either
