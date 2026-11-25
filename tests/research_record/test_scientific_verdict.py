"""JSON requirement: explicit ``scientific_verdict``."""
from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_formal_evidence_unavailable_yields_not_applicable(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {"results": [{"hypothesis_id": "HYP-1", "claim_class": "unavailable", "data_mode": "unknown", "metric_type": "unset", "metric_value": None, "verdict": "unknown"}]},
            "topology_validation": {"checks": []},
            "scientific_gate_reports": {"gates": []},
        }
    )
    record = compile_record(manifest, now=NOW)
    assert record["scientific_verdict"] == "NOT_APPLICABLE"


def test_scientific_verdict_is_always_present_and_typed(manifest_factory):
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    assert "scientific_verdict" in record
    assert record["scientific_verdict"] in {"PASS", "FAIL", "INCONCLUSIVE", "NOT_APPLICABLE"}


def test_inconclusive_when_only_inconclusive_formal_evidence_present(manifest_factory):
    manifest = manifest_factory(
        {"falsification": {"results": [{"hypothesis_id": "HYP-1", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 1.0, "verdict": "INCONCLUSIVE"}]}}
    )
    record = compile_record(manifest, now=NOW)
    assert record["scientific_verdict"] == "INCONCLUSIVE"
