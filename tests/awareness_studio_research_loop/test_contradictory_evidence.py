"""Rule: every theory update preserves contradictory evidence."""
from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_theory_naming_a_missing_claim_as_contradictory_fails_the_gate(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["theory_state"]["contradictory_evidence_ids"] = ["C-MISSING"]
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["theory_contradictions_preserved"]["passed"] is False
    assert any(v["id"] == "C-MISSING" for v in report["gate_results"]["theory_contradictions_preserved"]["violations"])


def test_theory_naming_a_present_claim_as_contradictory_passes_but_blocks_that_hypothesis(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["theory_state"]["contradictory_evidence_ids"] = ["C1"]
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["theory_contradictions_preserved"]["passed"] is True
    # The contradiction is preserved (gate passes), but a hypothesis whose
    # own claims are named as contradictory evidence cannot be declared
    # paper-ready without resolving it.
    assert report["cycle_states"]["H1"]["state"] == "THEORY_REVISION_REQUIRED"
