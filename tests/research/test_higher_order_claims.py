"""Offline tests for the higher-order literature audit registry."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = ROOT / "configs" / "research" / "higher_order_claims.yaml"
DOC_PATH = ROOT / "docs" / "research" / "higher_order_literature_audit.md"

REQUIRED_SOURCE_FIELDS = (
    "id",
    "title",
    "authors",
    "identifier",
    "identifier_type",
    "url",
    "identity_status",
    "source_type",
    "peer_review_status",
    "claim_text",
    "source_location",
    "evidence_tier",
    "causal_status",
    "alternative_interpretations",
    "limitations",
    "replication_requirement",
    "repository_hypothesis_link",
)


def _load():
    document = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_confirmed_source():
    document = _load()
    confirmed = [item for item in document["sources"] if item["identity_status"] == "confirmed"]
    ids = {item["identifier"] for item in confirmed}
    assert "arXiv:2609.03987" in ids
    assert "arXiv:2609.03172" in ids
    assert "10.1016/j.neuron.2026.04.044" in ids
    assert "10.1007/s12671-026-02976-7" in ids
    assert "10.3389/fpsyg.2026.1938434" in ids
    triadic = next(item for item in confirmed if item["id"] == "triadic_fc_arxiv_2609_03987")
    assert triadic["source_type"] == "preprint"
    assert triadic["peer_review_status"] == "not_peer_reviewed"
    spectral = next(item for item in confirmed if item["id"] == "higher_order_spectral_arxiv_2609_03172")
    assert spectral["title"] == "Modulation Analysis with Higher-Order Spectra"
    assert spectral["source_type"] == "preprint"
    neuron = next(item for item in confirmed if item["id"] == "slow_breathing_neuron_2026_04_044")
    assert neuron["source_type"] == "peer_reviewed_article"
    assert neuron["peer_review_status"] == "peer_reviewed"
    for item in confirmed:
        for field in REQUIRED_SOURCE_FIELDS:
            assert field in item


def test_disputed_doi():
    document = _load()
    disputed = [item for item in document["sources"] if item["identity_status"] == "disputed"]
    disputed_ids = {item["identifier"] for item in disputed}
    assert "10.1007/s12671-026-00000-0" in disputed_ids
    assert "arXiv:2609.03172" not in disputed_ids
    assert "10.1007/s12671-026-02976-7" not in disputed_ids
    assert "10.3389/fpsyg.2026.1938434" not in disputed_ids
    nearby = next(item for item in document["sources"] if item["id"] == "discernment_doi_02976_7")
    assert nearby["identity_status"] == "confirmed"
    assert nearby["nearby_confirmed_doi"] == "10.1007/s12671-026-02770-5"
    assert nearby["nearby_title"].startswith("Being Mindful with Discernment")


def test_unsupported_causal_claim():
    document = _load()
    causal = [item for item in document["claims"] if item["claim_class"] == "unsupported_causal"]
    assert causal
    assert all(item["status"] == "rejected_or_downgraded" for item in causal)
    triadic = next(item for item in document["sources"] if item["id"] == "triadic_fc_arxiv_2609_03987")
    assert triadic["causal_status"] == "statistical_dependence_only"
    assert triadic["supported_for_repository"] is False
    breath = next(item for item in document["sources"] if item["id"] == "slow_breathing_neuron_2026_04_044")
    assert breath["causal_status"] == "intervention_associated_not_detachment"
    assert breath["supported_for_repository"] is False
    spectral = next(item for item in document["sources"] if item["id"] == "higher_order_spectral_arxiv_2609_03172")
    assert spectral["causal_status"] == "descriptive_method_not_mechanism"
    assert spectral["supported_for_repository"] is False


def test_theory_paper():
    document = _load()
    ecology = next(item for item in document["sources"] if item["id"] == "buddhist_ecology_doi_1938434")
    assert ecology["identity_status"] == "confirmed"
    assert ecology["source_type"] == "theory_paper"
    assert ecology["evidence_tier"] == "theory_hypothesis_framework"
    assert ecology["causal_status"] == "theoretical_model_not_evidence"
    assert ecology["supported_for_repository"] is False
    theory_claims = [item for item in document["claims"] if item["claim_class"] == "theory_or_construct"]
    assert theory_claims
    assert all(item["status"] == "rejected_or_downgraded" for item in theory_claims)


def test_preprint():
    document = _load()
    preprints = [item for item in document["sources"] if item["source_type"] == "preprint"]
    preprint_ids = {item["identifier"] for item in preprints}
    assert "arXiv:2609.03987" in preprint_ids
    assert "arXiv:2609.03172" in preprint_ids
    assert all(item["peer_review_status"] == "not_peer_reviewed" for item in preprints)
    preprint_claims = [item for item in document["claims"] if item["claim_class"] == "preprint"]
    assert preprint_claims
    assert all(item["status"] == "rejected_or_downgraded" for item in preprint_claims)


def test_deterministic_yaml_json():
    first = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    second = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    encoded = json.dumps(first, sort_keys=True, allow_nan=False)
    assert encoded == json.dumps(second, sort_keys=True, allow_nan=False)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert first["evidence_claim_allowed"] is False
    assert first["repository_theories_established"] is False
    assert first["schema"] == "NeuroTopologySim.HigherOrderLiteratureAudit.v1"
    assert first["scientific_status"] == "literature_audit_only"
    assert DOC_PATH.is_file()


def test_no_network_operation(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    document = _load()
    assert document["scientific_status"] == "literature_audit_only"
    assert {item["id"] for item in document["hypotheses"]} >= {
        "H-AUDIT-TRIADIC-DEPENDENCE",
        "H-AUDIT-SPECTRAL-MODULOGRAM",
        "H-AUDIT-BREATH-PARASYMPATHETIC",
        "H-AUDIT-DISCERNMENT-NE-NONJUDGMENT",
        "H-AUDIT-TRAINING-ECOLOGY-THEORY",
        "H-AUDIT-CONTROL-UNRESOLVED-DOI",
    }
    assert all(item["supported_for_repository"] is False for item in document["sources"])
