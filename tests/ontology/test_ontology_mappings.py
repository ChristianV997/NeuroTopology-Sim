from __future__ import annotations

from sciencer_d.ontology.registry import OntologyRegistry


def test_every_mapping_surface_is_populated_and_referentially_valid():
    registry = OntologyRegistry.load()
    claim_ids = {claim.claim_id for claim in registry.claims}
    assert set(registry.mappings) == {
        "btc_icft",
        "theravada",
        "cosmology",
        "philosophy",
    }
    for rows in registry.mappings.values():
        assert rows
        for row in rows:
            assert row["claim_id"] in claim_ids
            assert row["source_constructs"]
            assert row["mapping_type"]
            assert row["guardrail"]


def test_mapping_scopes_preserve_required_quarantines():
    registry = OntologyRegistry.load()
    cosmology_text = str(registry.mappings["cosmology"]).lower()
    theravada_text = str(registry.mappings["theravada"]).lower()
    philosophy_text = str(registry.mappings["philosophy"]).lower()
    assert "structural_analogy" in cosmology_text
    assert "not verified astrophysical planes" in theravada_text
    assert "quarantined_ontology_candidate" in philosophy_text
