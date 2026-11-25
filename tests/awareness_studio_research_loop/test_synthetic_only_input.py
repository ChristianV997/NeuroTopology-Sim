"""Rule: every synthetic result remains synthetic."""
from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_synthetic_execution_never_becomes_formal_evidence(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["execution_results"]["executions"][0]["data_mode"] = "synthetic"
    overrides["experiment_plans"]["plans"][0]["synthetic"] = True
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    ledger_row = report["artifact_ledger"][0]
    assert ledger_row["scientific_status"] == "synthetic"
    assert report["evidence_class_summary"]["executions"].get("synthetic") == 1
    assert "empirical" not in report["evidence_class_summary"]["executions"]


def test_validation_report_cannot_relabel_synthetic_execution_as_empirical(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["execution_results"]["executions"][0]["data_mode"] = "synthetic"
    overrides["validation_reports"] = {"reports": [{"report_id": "V1", "experiment_id": "E1", "claim_status": "empirical", "data_mode": "empirical", "verdict": "PASS", "source": "external"}]}
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["synthetic_not_promoted"]["passed"] is False
    assert any(v["id"] == "V1" for v in report["gate_results"]["synthetic_not_promoted"]["violations"])
