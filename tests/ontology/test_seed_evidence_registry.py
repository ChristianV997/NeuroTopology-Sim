from __future__ import annotations

import json

from sciencer_d.ontology.firewall import scan_text
from sciencer_d.ontology.registry import (
    REQUIRED_EVIDENCE_CATEGORIES,
    OntologyRegistry,
)
from sciencer_d.ontology.reports import build_ontology_report
from sciencer_d.ontology.scoring import score_claim


def test_seed_registry_covers_every_required_category_and_record_field():
    registry = OntologyRegistry.load()
    assert REQUIRED_EVIDENCE_CATEGORIES <= {
        paper.category for paper in registry.papers
    }
    for paper in registry.papers:
        record = paper.to_dict()
        for field in (
            "paper_id",
            "title",
            "year",
            "field",
            "evidence_type",
            "url_or_doi",
            "notes",
        ):
            assert record[field] not in (None, "")
        assert paper.url_or_doi.startswith("https://")


def test_every_paper_is_linked_and_every_link_is_referentially_valid():
    registry = OntologyRegistry.load()
    claim_ids = {claim.claim_id for claim in registry.claims}
    paper_ids = {paper.paper_id for paper in registry.papers}
    assert {link.paper_id for link in registry.claim_links} == paper_ids
    assert {link.claim_id for link in registry.claim_links} <= claim_ids
    assert all(0 <= link.strength <= 5 for link in registry.claim_links)


def test_every_claim_has_a_falsifier_with_required_fields():
    registry = OntologyRegistry.load()
    claim_ids = {claim.claim_id for claim in registry.claims}
    assert {item.claim_id for item in registry.falsifiers} == claim_ids
    assert len({item.falsifier_id for item in registry.falsifiers}) == len(
        registry.falsifiers
    )
    assert all(item.description and item.required_test for item in registry.falsifiers)


def test_sensitive_claims_remain_below_empirical_status():
    registry = OntologyRegistry.load()
    statuses = {claim.claim_id: score_claim(claim).status for claim in registry.claims}
    assert statuses["O5_SOUL_IDENTITY_INVARIANT"] == "O-C"
    assert statuses["O6_SURVIVAL_AFTER_DEATH"] == "O-C"
    assert statuses["O8_PANPSYCHISM_NEUTRAL_MONISM"] == "O-C"
    assert statuses["O7_FIELD_CONSCIOUSNESS"] in {"O-B", "O-C"}


def test_seed_yaml_payload_and_generated_report_are_firewall_clean(tmp_path):
    registry = OntologyRegistry.load()
    payload = json.dumps(
        {
            "papers": [item.to_dict() for item in registry.papers],
            "links": [item.to_dict() for item in registry.claim_links],
            "falsifiers": [item.to_dict() for item in registry.falsifiers],
            "mappings": registry.mappings,
        },
        ensure_ascii=False,
    )
    assert scan_text(payload).allowed is True

    report = build_ontology_report(tmp_path)["report"].read_text(encoding="utf-8")
    assert scan_text(report).allowed is True
