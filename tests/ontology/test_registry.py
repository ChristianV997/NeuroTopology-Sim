from __future__ import annotations

import pytest

from sciencer_d.ontology.registry import OntologyRegistry
from sciencer_d.ontology.schemas import OntologyClaimLink


EXPECTED_CLAIMS = {
    "O1_STATE_AVAILABILITY",
    "O2_MINIMAL_AWARENESS",
    "O3_NONDUAL_AWARENESS",
    "O4_SELF_BOUNDARY_POLICY",
    "O5_SOUL_IDENTITY_INVARIANT",
    "O6_SURVIVAL_AFTER_DEATH",
    "O7_FIELD_CONSCIOUSNESS",
    "O8_PANPSYCHISM_NEUTRAL_MONISM",
    "O9_BIOELECTRIC_BASAL_COGNITION",
    "O10_HOLOGRAPHIC_HOLARCHY",
    "O11_COSMIC_NATURAL_SELECTION",
    "O12_THERAVADA_REALMS_STATE_SPACE",
}


def test_registry_loads_all_seed_claims_and_p1_evidence():
    registry = OntologyRegistry.load()
    assert {claim.claim_id for claim in registry.claims} == EXPECTED_CLAIMS
    assert registry.papers
    assert registry.claim_links
    assert {item.claim_id for item in registry.falsifiers} == EXPECTED_CLAIMS


def test_registry_claim_lookup_is_explicit():
    registry = OntologyRegistry.load()
    assert registry.claim_by_id("O7_FIELD_CONSCIOUSNESS").status == "O-B"
    with pytest.raises(KeyError):
        registry.claim_by_id("O_UNKNOWN")


def test_registry_rejects_dangling_claim_link():
    registry = OntologyRegistry.load()
    registry.claim_links.append(
        OntologyClaimLink(
            claim_id="O_UNKNOWN",
            paper_id="P_UNKNOWN",
            support_direction="background",
            strength=1,
            notes="Dangling test record",
        )
    )
    with pytest.raises(ValueError, match="Unknown claim link claim_id"):
        registry.validate()
