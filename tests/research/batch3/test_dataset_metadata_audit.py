"""Schema checks and contract validation for the Batch 3 metadata audit.

Postures:
- HOLD / SYNTHETIC_ONLY
- Zero participant data downloaded or analyzed
- No scientific PASS or suitability claim
- No inference of permission, analyzed sample size, or cohort identity from catalog metadata
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "reports" / "batch3" / "grok_chat_b" / "dataset_candidates_metadata_audit.json"
DOC = ROOT / "docs" / "research" / "batch3" / "grok_chat_b_dataset_feasibility.md"


def load() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_hold_and_no_download() -> None:
    doc = load()
    assert doc["status"] == "HOLD"
    assert doc["evidence_class"] == "SYNTHETIC_ONLY"
    assert doc["scientific_pass"] is False
    assert doc["validated"] is False
    assert doc["participant_data_downloaded"] is False
    assert doc["participant_data_analyzed"] is False
    assert doc["analysis_performed"] is False
    assert doc["same_mechanism_candidate_present"] is False
    assert doc["permission_inferred"] is False
    assert doc["scientific_suitability_inferred"] is False

    text = DOC.read_text(encoding="utf-8")
    assert "HOLD / SYNTHETIC_ONLY" in text
    assert "No participant data downloaded" in text
    assert "No scientific PASS" in text


def test_license_conflict_preserved_with_sources() -> None:
    doc = load()
    ref = next(item for item in doc["candidates"] if item["accession"] == "ds005620")
    evidence = ref["license_evidence"]
    assert evidence["conflict"] is True
    assert "CC0" in evidence["dataset_description_json"]["statement"]
    assert "CC0" in evidence["nemar_catalog"]["statement"]
    assert "CC-BY-4.0" in evidence["github_readme"]["statement"]

    # Verify primary source URLs and retrieval dates are preserved
    assert evidence["dataset_description_json"]["source_url"].startswith("https://")
    assert evidence["nemar_catalog"]["source_url"].startswith("https://")
    assert evidence["github_readme"]["source_url"].startswith("https://")
    assert evidence["dataset_description_json"]["retrieved_date"] == "2026-10-16"
    assert evidence["nemar_catalog"]["retrieved_date"] == "2026-10-16"
    assert evidence["github_readme"]["retrieved_date"] == "2026-10-16"
    assert evidence["permission_inferred"] is False


def test_all_candidates_have_source_urls_and_retrieval_dates() -> None:
    doc = load()
    for item in doc["candidates"]:
        assert "source_url" in item and item["source_url"].startswith("https://openneuro.org/datasets/")
        assert "retrieved_date" in item and item["retrieved_date"] == "2026-10-16"
        assert item["doi"].startswith("10.18112/openneuro.")
        assert "doi_url" in item and item["doi_url"].startswith("https://doi.org/10.18112/openneuro.")


def test_catalog_n_not_treated_as_analyzed_n() -> None:
    doc = load()
    for item in doc["candidates"]:
        assert "catalog_participants" in item
        assert "paper_inclusion_count" in item
        assert item.get("analyzed_sample_size_inferred") is False
        assert item.get("cohort_identity_inferred") is False
        assert item.get("scientific_suitability_inferred") is False

    # Specific check for ds003969 catalog (98) vs paper analyzed (64 in 4 matched groups of 16)
    c3969 = next(item for item in doc["candidates"] if item["accession"] == "ds003969")
    assert "98" in str(c3969["catalog_participants"])
    assert "4 matched groups of 16" in str(c3969["paper_inclusion_count"])
    assert "not the analyzed N" in str(c3969["paper_inclusion_count"])

    # Specific check for ds005620 reference
    c5620 = next(item for item in doc["candidates"] if item["accession"] == "ds005620")
    assert "21" in str(c5620["catalog_participants"])
    assert "excluded" in str(c5620["catalog_participants"])
    assert "bad_after_preprocessing" in str(c5620["catalog_participants"])


def test_no_same_mechanism_candidate() -> None:
    doc = load()
    assert doc["same_mechanism_candidate_present"] is False
    for item in doc["candidates"]:
        assert item.get("same_mechanism") is False


def test_non_replication_datasets_coverage() -> None:
    doc = load()
    assert "not_replication_datasets" in doc
    names = [entry["name"] for entry in doc["not_replication_datasets"]]
    assert "maziyarpanahi/openmed" in names
    assert "research-agent frameworks" in names
    assert any("ds003171" in name for name in names)


def test_gates_and_blockers_completeness() -> None:
    doc = load()
    assert len(doc["candidates"]) >= 5
    for item in doc["candidates"]:
        assert len(item["blockers"]) >= 2

    required_gates = {
        "confirm_license_from_dataset_description_and_catalog_before_any_transfer",
        "bounded_access_with_explicit_network_permission",
        "preregister_splits_nulls_and_multiplicity_before_analysis",
        "harmonize_montage_and_sampling_or_declare_incomparability",
        "do_not_treat_catalog_n_as_analyzed_n",
    }
    assert required_gates.issubset(set(doc["gates"]))


def test_strict_schema_and_finite_json() -> None:
    doc = load()
    assert doc["schema"] == "NeuroTopology.Batch3ReplicationMetadataAudit.v1"
    assert doc["package_id"] == "batch3_grok_chat_b_metadata_audit"
    assert "sync_base_sha" in doc
    assert len(doc["sync_base_sha"]) == 40
    # Ensure serialization strictly prohibits NaN and Inf
    dumped = json.dumps(doc, sort_keys=True, allow_nan=False)
    roundtripped = json.loads(dumped)
    assert roundtripped["research_date"] == "2026-10-16"


def test_markdown_json_synchronization() -> None:
    doc = load()
    text = DOC.read_text(encoding="utf-8")
    for item in doc["candidates"]:
        assert item["accession"] in text
        assert item["doi"] in text
    for gate in doc["gates"]:
        # Key phrase checks in markdown
        if "confirm_license" in gate:
            assert "License confirmation" in text
        if "bounded_access" in gate:
            assert "Bounded access" in text
        if "preregister" in gate:
            assert "Preregistration" in text
        if "harmonize_montage" in gate:
            assert "Montage and sampling harmonization" in text
        if "do_not_treat_catalog_n" in gate:
            assert "Catalog n is not treated as analyzed n" in text


def test_source_statements_classification() -> None:
    doc = load()
    valid_classifications = {"author-supplied", "independently_verified"}
    assert doc.get("source_statement_classifications_present") is True

    # Check candidates
    for item in doc["candidates"]:
        assert item.get("catalog_participants_classification") in valid_classifications
        if item.get("paper_inclusion_count") is not None:
            assert item.get("paper_inclusion_classification") in valid_classifications
        assert item.get("same_mechanism_classification") == "independently_verified"
        assert item.get("source_url_classification") == "independently_verified"

        # Check license evidence statements
        evidence = item["license_evidence"]
        for key in ("dataset_description_json", "nemar_catalog", "github_readme", "openneuro_catalog"):
            if key in evidence and isinstance(evidence[key], dict):
                assert evidence[key].get("classification") in valid_classifications

    # Check markdown discussion of classification
    text = DOC.read_text(encoding="utf-8")
    assert "author-supplied" in text
    assert "independently verified" in text
