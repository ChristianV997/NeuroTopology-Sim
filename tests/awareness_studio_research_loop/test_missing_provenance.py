from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_claim_referencing_unknown_source_is_blocked_by_provenance(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["literature_evidence"]["claims"][0]["source_id"] = "S-DOES-NOT-EXIST"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["claim_provenance"]["passed"] is False
    assert report["cycle_states"]["H1"]["state"] == "BLOCKED_BY_PROVENANCE"


def test_source_with_no_checksum_is_blocked_by_provenance(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["literature_evidence"]["sources"][0]["source_checksum"] = None
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["gate_results"]["claim_provenance"]["passed"] is False
    assert report["cycle_states"]["H1"]["state"] == "BLOCKED_BY_PROVENANCE"
