"""Schema checks and contract validation for the Batch 3 metadata audit.

Postures:
- HOLD / SYNTHETIC_ONLY
- Zero participant data downloaded or analyzed
- No scientific PASS or suitability claim
- No inference of permission, analyzed sample size, or cohort identity from catalog metadata
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "reports" / "batch3" / "grok_chat_b" / "dataset_candidates_metadata_audit.json"
DOC = ROOT / "docs" / "research" / "batch3" / "grok_chat_b_dataset_feasibility.md"


def load() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def _check_finite_values(val: Any, path: str = "") -> None:
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Non-finite float value found at {path}: {val}")
    elif isinstance(val, dict):
        for key, item in val.items():
            _check_finite_values(item, f"{path}.{key}" if path else str(key))
    elif isinstance(val, list):
        for idx, item in enumerate(val):
            _check_finite_values(item, f"{path}[{idx}]")


def validate_metadata_candidate(candidate: dict[str, Any]) -> None:
    """Fail-closed checks for one metadata-audit candidate record."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    _check_finite_values(candidate, candidate.get("accession", "candidate"))

    accession = candidate.get("accession")
    if not isinstance(accession, str) or not accession.startswith("ds"):
        raise ValueError(f"invalid accession: {accession!r}")

    source_url = candidate.get("source_url")
    if not isinstance(source_url, str) or not source_url.startswith("https://openneuro.org/datasets/"):
        raise ValueError(f"source_url must be https OpenNeuro dataset URL for {accession}")
    retrieved = candidate.get("retrieved_date")
    if not isinstance(retrieved, str) or not retrieved.strip():
        raise ValueError(f"retrieved_date required for {accession}")

    doi = candidate.get("doi")
    if not isinstance(doi, str) or not doi.startswith("10.18112/openneuro."):
        raise ValueError(f"doi must be an OpenNeuro DOI for {accession}")
    if "/versions/" in source_url:
        version = source_url.rstrip("/").rsplit("/", 1)[-1]
        if f".v{version}" not in doi:
            raise ValueError(
                f"DOI version must match source_url version for {accession}: "
                f"doi={doi!r} source_url={source_url!r}"
            )

    for key in (
        "permission_inferred",
        "scientific_suitability_inferred",
        "analyzed_sample_size_inferred",
        "cohort_identity_inferred",
    ):
        if candidate.get(key) is not False:
            raise ValueError(f"{key} must be false for {accession}")

    if candidate.get("same_mechanism") is not False:
        raise ValueError(f"same_mechanism must be false for {accession}")

    if "catalog_participants" not in candidate or "paper_inclusion_count" not in candidate:
        raise ValueError(f"catalog vs paper inclusion fields required for {accession}")

    evidence = candidate.get("license_evidence")
    if not isinstance(evidence, dict):
        raise ValueError(f"license_evidence required for {accession}")
    if evidence.get("permission_inferred") is not False:
        raise ValueError(f"license_evidence.permission_inferred must be false for {accession}")
    if not isinstance(evidence.get("conflict"), bool):
        raise ValueError(f"license_evidence.conflict must be boolean for {accession}")

    statements = []
    for key in ("dataset_description_json", "nemar_catalog", "github_readme", "openneuro_catalog"):
        block = evidence.get(key)
        if not isinstance(block, dict):
            continue
        statement = str(block.get("statement", ""))
        url = block.get("source_url")
        date = block.get("retrieved_date")
        if not statement.strip():
            raise ValueError(f"{accession} {key} statement required")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"{accession} {key} requires https source_url")
        if not isinstance(date, str) or not date.strip():
            raise ValueError(f"{accession} {key} requires retrieved_date")
        statements.append(statement)

    if evidence.get("conflict") is True:
        joined = " ".join(statements)
        if "CC0" not in joined or "CC-BY-4.0" not in joined:
            raise ValueError(
                f"{accession} conflict=true requires both CC0 and CC-BY-4.0 statements to be preserved"
            )
        readme = evidence.get("github_readme") or {}
        readme_url = str(readme.get("source_url", ""))
        if "README.txt" not in readme_url:
            raise ValueError(
                f"{accession} conflicting README source_url must identify README.txt "
                "(bare README paths 404)"
            )
    elif evidence.get("conflict") is False:
        # Do not allow silently dropping a CC0 vs CC-BY conflict
        joined = " ".join(statements)
        if "CC0" in joined and "CC-BY-4.0" in joined:
            raise ValueError(
                f"{accession} preserves disagreeing CC0 and CC-BY-4.0 statements but conflict=false"
            )


def validate_metadata_document(doc: dict[str, Any]) -> None:
    _check_finite_values(doc, "metadata_audit")
    if doc.get("status") != "HOLD":
        raise ValueError("status must be HOLD")
    if doc.get("evidence_class") != "SYNTHETIC_ONLY":
        raise ValueError("evidence_class must be SYNTHETIC_ONLY")
    for key in (
        "scientific_pass",
        "validated",
        "participant_data_downloaded",
        "participant_data_analyzed",
        "analysis_performed",
        "permission_inferred",
        "scientific_suitability_inferred",
        "analyzed_sample_size_inferred",
        "cohort_identity_inferred",
        "same_mechanism_candidate_present",
    ):
        if doc.get(key) is not False:
            raise ValueError(f"{key} must be false")
    candidates = doc.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 5:
        raise ValueError("candidates must contain at least 5 records")
    for candidate in candidates:
        validate_metadata_candidate(candidate)


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

    assert evidence["dataset_description_json"]["source_url"].endswith("/dataset_description.json")
    assert evidence["nemar_catalog"]["source_url"].startswith("https://")
    assert evidence["github_readme"]["source_url"].endswith("/README.txt")
    assert evidence["dataset_description_json"]["retrieved_date"] == "2026-10-23"
    assert evidence["github_readme"]["retrieved_date"] == "2026-10-23"
    assert evidence["permission_inferred"] is False
    validate_metadata_candidate(ref)


def test_all_candidates_have_source_urls_and_retrieval_dates() -> None:
    doc = load()
    for item in doc["candidates"]:
        assert "source_url" in item and item["source_url"].startswith("https://openneuro.org/datasets/")
        assert "retrieved_date" in item and str(item["retrieved_date"]).strip()
        assert item["doi"].startswith("10.18112/openneuro.")
        assert "doi_url" in item and item["doi_url"].startswith("https://doi.org/10.18112/openneuro.")
        validate_metadata_candidate(item)


def test_catalog_n_not_treated_as_analyzed_n() -> None:
    doc = load()
    for item in doc["candidates"]:
        assert "catalog_participants" in item
        assert "paper_inclusion_count" in item
        assert item.get("analyzed_sample_size_inferred") is False
        assert item.get("cohort_identity_inferred") is False
        assert item.get("scientific_suitability_inferred") is False

    c3969 = next(item for item in doc["candidates"] if item["accession"] == "ds003969")
    assert "98" in str(c3969["catalog_participants"])
    assert "4 matched groups of 16" in str(c3969["paper_inclusion_count"])
    assert "not the analyzed N" in str(c3969["paper_inclusion_count"])

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
    dumped = json.dumps(doc, sort_keys=True, allow_nan=False)
    roundtripped = json.loads(dumped)
    assert roundtripped["research_date"] == "2026-10-16"
    validate_metadata_document(doc)


def test_markdown_json_synchronization() -> None:
    doc = load()
    text = DOC.read_text(encoding="utf-8")
    for item in doc["candidates"]:
        assert item["accession"] in text
        assert item["doi"] in text
    assert "README.txt" in text
    assert "blob/master/README" not in text or "404" in text
    for gate in doc["gates"]:
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

    for item in doc["candidates"]:
        assert item.get("catalog_participants_classification") in valid_classifications
        if item.get("paper_inclusion_count") is not None:
            assert item.get("paper_inclusion_classification") in valid_classifications
        assert item.get("same_mechanism_classification") == "independently_verified"
        assert item.get("source_url_classification") == "independently_verified"

        evidence = item["license_evidence"]
        for key in ("dataset_description_json", "nemar_catalog", "github_readme", "openneuro_catalog"):
            if key in evidence and isinstance(evidence[key], dict):
                assert evidence[key].get("classification") in valid_classifications

    text = DOC.read_text(encoding="utf-8")
    assert "author-supplied" in text
    assert "independently verified" in text


def test_ds008836_doi_matches_versioned_source_url() -> None:
    doc = load()
    item = next(c for c in doc["candidates"] if c["accession"] == "ds008836")
    assert item["version"] == "1.0.2"
    assert item["doi"] == "10.18112/openneuro.ds008836.v1.0.2"
    assert item["source_url"].endswith("/versions/1.0.2")
    validate_metadata_candidate(item)


def test_adversarial_rejects_permission_inference() -> None:
    doc = load()
    cand = copy.deepcopy(next(c for c in doc["candidates"] if c["accession"] == "ds005620"))
    cand["permission_inferred"] = True
    try:
        validate_metadata_candidate(cand)
    except ValueError as exc:
        assert "permission_inferred" in str(exc)
    else:
        raise AssertionError("expected permission_inferred rejection")

    cand = copy.deepcopy(next(c for c in doc["candidates"] if c["accession"] == "ds005620"))
    cand["license_evidence"]["permission_inferred"] = True
    try:
        validate_metadata_candidate(cand)
    except ValueError as exc:
        assert "permission_inferred" in str(exc)
    else:
        raise AssertionError("expected license_evidence.permission_inferred rejection")


def test_adversarial_rejects_dropped_license_conflict() -> None:
    doc = load()
    cand = copy.deepcopy(next(c for c in doc["candidates"] if c["accession"] == "ds005620"))
    cand["license_evidence"]["conflict"] = False
    try:
        validate_metadata_candidate(cand)
    except ValueError as exc:
        assert "conflict=false" in str(exc)
    else:
        raise AssertionError("expected conflict=false rejection when CC0 and CC-BY remain")


def test_adversarial_rejects_bare_readme_source_url() -> None:
    doc = load()
    cand = copy.deepcopy(next(c for c in doc["candidates"] if c["accession"] == "ds005620"))
    cand["license_evidence"]["github_readme"]["source_url"] = (
        "https://github.com/OpenNeuroDatasets/ds005620/blob/master/README"
    )
    try:
        validate_metadata_candidate(cand)
    except ValueError as exc:
        assert "README.txt" in str(exc)
    else:
        raise AssertionError("expected bare README URL rejection")


def test_adversarial_rejects_analyzed_sample_size_inference() -> None:
    doc = load()
    cand = copy.deepcopy(next(c for c in doc["candidates"] if c["accession"] == "ds003969"))
    cand["analyzed_sample_size_inferred"] = True
    try:
        validate_metadata_candidate(cand)
    except ValueError as exc:
        assert "analyzed_sample_size_inferred" in str(exc)
    else:
        raise AssertionError("expected analyzed_sample_size_inferred rejection")


def test_adversarial_rejects_doi_version_mismatch() -> None:
    doc = load()
    cand = copy.deepcopy(next(c for c in doc["candidates"] if c["accession"] == "ds008836"))
    cand["source_url"] = "https://openneuro.org/datasets/ds008836/versions/1.0.1"
    cand["doi"] = "10.18112/openneuro.ds008836.v1.0.0"
    try:
        validate_metadata_candidate(cand)
    except ValueError as exc:
        assert "DOI version must match source_url version" in str(exc)
    else:
        raise AssertionError("expected DOI/source_url mismatch rejection")
