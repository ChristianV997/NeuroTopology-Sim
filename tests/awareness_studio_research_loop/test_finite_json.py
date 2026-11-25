"""JSON requirement: no NaN/Infinity anywhere, null for unavailable values."""
from __future__ import annotations

import json

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tools.awareness_studio_research_loop.evidence_loader import load_evidence_file
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_json_nan_and_infinity_are_rejected_at_load_time(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"executions": [{"experiment_id": "E1", "runtime_seconds": NaN}]}', encoding="utf-8")
    result = load_evidence_file(path, list_key="executions")
    assert result.ok is False
    assert "non_finite_value" in result.error


def test_overflowing_numeric_literal_is_nulled(manifest_factory):
    overrides = complete_cycle_overrides()
    manifest = manifest_factory(overrides)
    # Directly write an execution_results file containing a silent-overflow literal.
    (manifest.parent / "execution_results.json").write_text('{"executions": [{"experiment_id": "E1", "runtime_seconds": 1e400}]}', encoding="utf-8")

    report = compile_research_cycle(manifest, now=NOW)
    assert report["execution_results"]["executions"][0]["runtime_seconds"] is None


def test_full_report_serializes_with_allow_nan_false(manifest_factory):
    manifest = manifest_factory(complete_cycle_overrides())
    report = compile_research_cycle(manifest, now=NOW)

    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text) == report


def test_missing_fields_are_null_not_fabricated(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["execution_results"]["executions"][0]["software_commit"] = None
    overrides["execution_results"]["executions"][0]["runtime_seconds"] = None
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)
    execution = report["execution_results"]["executions"][0]
    assert execution["software_commit"] is None
    assert execution["runtime_seconds"] is None
