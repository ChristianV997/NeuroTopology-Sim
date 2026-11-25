from __future__ import annotations

import json

from tools.research_cycle_cli.compiler import compile_inspection

NOW = "2026-01-01T00:00:00+00:00"


def test_artifact_report_with_stale_paths_is_surfaced(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    report_data = {
        "status": "INCOMPLETE",
        "run_directory": "/runs/run1",
        "artifact_manifest": {"artifacts": []},
        "provenance": {"run_id": "RUN-1"},
        "evidence": {"evidence_class": "engineering_fact", "synthetic": False},
        "diagnostics": {"stale": ["old_metrics.json", "old_summary.csv"], "missing": [], "partial": [], "failed": [], "conflicting": []},
    }
    (artifacts_dir / "report1.json").write_text(json.dumps(report_data), encoding="utf-8")

    report = compile_inspection(ledger_db=None, claim_gate_report=None, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)

    stale = report["stale_outputs"]
    assert len(stale) == 1
    assert stale[0]["run_directory"] == "/runs/run1"
    assert stale[0]["stale_paths"] == ["old_metrics.json", "old_summary.csv"]


def test_artifact_report_without_stale_paths_is_not_surfaced(tmp_path):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    report_data = {
        "status": "COMPLETE",
        "artifact_manifest": {"artifacts": []},
        "provenance": {"run_id": "RUN-1"},
        "evidence": {"evidence_class": "engineering_fact", "synthetic": False},
        "diagnostics": {"stale": [], "missing": [], "partial": [], "failed": [], "conflicting": []},
    }
    (artifacts_dir / "report1.json").write_text(json.dumps(report_data), encoding="utf-8")

    report = compile_inspection(ledger_db=None, claim_gate_report=None, artifact_reports=None, artifacts_dir=artifacts_dir, now=NOW)
    assert report["stale_outputs"] == []
