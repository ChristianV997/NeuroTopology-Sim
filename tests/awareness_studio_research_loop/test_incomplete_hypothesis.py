from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_hypothesis_missing_null_prediction_stalls_at_literature_ready(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["hypothesis_registry"]["hypotheses"][0]["null_prediction"] = None
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["null_prediction"]["passed"] is False
    assert report["cycle_states"]["H1"]["state"] == "LITERATURE_READY"


def test_experiment_missing_falsification_criterion_stalls_at_hypothesis_ready(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["experiment_plans"]["plans"][0]["falsification_criterion"] = None
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["falsification_criterion"]["passed"] is False
    assert report["cycle_states"]["H1"]["state"] == "HYPOTHESIS_READY"


def test_hypothesis_with_no_linked_claims_requires_human_review(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["literature_evidence"]["hypothesis_links"] = []
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "HUMAN_REVIEW_REQUIRED"
