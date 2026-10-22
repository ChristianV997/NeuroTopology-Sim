"""Schema and adversarial validation tests for the Batch 3 replication feasibility package.

Strict HOLD / SYNTHETIC_ONLY posture:
- No network access.
- No dataset download.
- No participant data analysis.
- No scientific PASS or empirical confirmation claim.
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "reports" / "batch3" / "grok_chat_b" / "dataset_candidates.json"
DOC = ROOT / "docs" / "research" / "batch3" / "replication_dataset_feasibility.md"

REQUIRED_ACCESSIONS = {
    "ds005620",
    "ds003969",
    "ds008836",
    "ds001787",
    "ds004572",
    "ds004541",
    "ds005555",
    "ds003171",
}

VALID_INSPECTION_LEVELS = {
    "listed_in_catalog",
    "metadata_inspected",
    "files_locally_available",
}

VALID_ANALYZED_N_STATUSES = {
    "no_analysis_performed",
    "unresolved_exclusions",
    "metadata_only",
}

VALID_RECOMMENDATIONS = {
    "rank_1_conditional",
    "rank_2_after_license_check",
    "rank_3_small_n",
    "rank_4_construct_generalization",
    "reference_only",
    "defer",
    "exclude",
}

DISALLOWED_OVERCLAIM_SUBSTRINGS = {
    "ready",
    "production_ready",
    "empirically_validated",
    "validated",
    "theory_confirmed",
}

ACCESSION_PATTERN = re.compile(r"^ds\d{6}$")


def load_candidate_matrix() -> dict[str, Any]:
    doc = json.loads(MATRIX.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("candidate matrix must be a JSON object")
    return doc


def _check_finite_values(val: Any, path: str = "") -> None:
    """Recursively ensure no NaN or infinite float values exist."""
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Non-finite float value found at {path}: {val}")
    elif isinstance(val, dict):
        for k, v in val.items():
            _check_finite_values(v, f"{path}.{k}" if path else str(k))
    elif isinstance(val, list):
        for idx, item in enumerate(val):
            _check_finite_values(item, f"{path}[{idx}]")


def validate_dataset_candidate_record(candidate: dict[str, Any]) -> None:
    """Validates an individual candidate record against the feasibility schema.

    Rejects malformed records, non-https URLs, invalid types, unacknowledged
    license conflicts, promoted analyzed counts, and overclaiming recommendations.
    """
    if not isinstance(candidate, dict):
        raise ValueError(f"Candidate record must be a dict, got {type(candidate).__name__}")

    _check_finite_values(candidate, candidate.get("accession", "unknown_candidate"))

    required_keys = [
        "accession",
        "title",
        "modality",
        "source_url",
        "doi",
        "license",
        "license_conflict",
        "license_declarations",
        "inspection_level",
        "catalog_n",
        "analyzed_n",
        "analyzed_n_status",
        "participants_stated",
        "sessions_stated",
        "tasks_or_conditions",
        "behavioral_labels",
        "access_restrictions",
        "exclusions_or_missingness",
        "compatibility",
        "blockers",
        "recommendation",
        "statement_provenance",
    ]
    for key in required_keys:
        if key not in candidate:
            raise ValueError(f"Candidate missing required field '{key}': {candidate.get('accession')}")

    # Accession format
    acc = candidate["accession"]
    if not isinstance(acc, str) or not ACCESSION_PATTERN.match(acc):
        raise ValueError(f"Invalid accession format: {acc!r}; expected dsXXXXXX")

    # Source URL
    url = candidate["source_url"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"source_url must be a secure https URL: {url!r}")

    # DOI format
    doi = candidate["doi"]
    if not isinstance(doi, str) or not doi.startswith("10."):
        raise ValueError(f"doi must be a valid DOI string starting with '10.': {doi!r}")

    # License and conflict
    if not isinstance(candidate["license"], str) or not candidate["license"].strip():
        raise ValueError("license must be a non-empty string")
    if not isinstance(candidate["license_conflict"], bool):
        raise ValueError("license_conflict must be a boolean")
    if not isinstance(candidate["license_declarations"], dict):
        raise ValueError("license_declarations must be a dict")

    blockers = candidate["blockers"]
    if not isinstance(blockers, list) or len(blockers) == 0:
        raise ValueError(f"blockers must be a non-empty list of strings for {acc}")
    for b in blockers:
        if not isinstance(b, str) or not b.strip():
            raise ValueError(f"Invalid blocker entry in {acc}: {b!r}")

    # If license conflict is flagged, it must be acknowledged in blockers
    if candidate["license_conflict"]:
        if not any("license_conflict" in b for b in blockers):
            raise ValueError(
                f"Candidate {acc} flags license_conflict=True but has no license_conflict blocker."
            )

    # Inspection level: must not claim analysis_performed
    level = candidate["inspection_level"]
    if level not in VALID_INSPECTION_LEVELS:
        raise ValueError(
            f"Invalid inspection_level '{level}' for {acc}. "
            f"Analysis is not performed in this feasibility package."
        )

    # Catalog N vs Analyzed N boundary
    catalog_n = candidate["catalog_n"]
    if not isinstance(catalog_n, int) or catalog_n <= 0:
        raise ValueError(f"catalog_n must be a positive integer, got {catalog_n!r}")

    analyzed_n = candidate["analyzed_n"]
    if analyzed_n is not None:
        raise ValueError(
            f"analyzed_n must be null/None when no participant data analysis was performed; got {analyzed_n!r}"
        )

    status = candidate["analyzed_n_status"]
    if status not in VALID_ANALYZED_N_STATUSES:
        raise ValueError(f"Invalid analyzed_n_status '{status}' for {acc}")

    # Recommendation validation & overclaim rejection
    rec = candidate["recommendation"]
    if rec not in VALID_RECOMMENDATIONS:
        raise ValueError(f"Disallowed recommendation '{rec}' for {acc}")

    rec_lower = rec.lower()
    for bad in DISALLOWED_OVERCLAIM_SUBSTRINGS:
        if bad in rec_lower:
            raise ValueError(f"Overclaiming recommendation '{rec}' contains disallowed '{bad}'")

    # Statement provenance: distinguish author assertions from independent sources
    prov = candidate["statement_provenance"]
    if not isinstance(prov, dict):
        raise ValueError(f"statement_provenance must be a dict for {acc}")
    required_prov_keys = [
        "catalog_n_provenance",
        "license_provenance",
        "doi_provenance",
        "hardware_and_sampling_provenance",
        "empirical_status",
    ]
    for pkey in required_prov_keys:
        if pkey not in prov or not isinstance(prov[pkey], str) or not prov[pkey].strip():
            raise ValueError(f"Missing or invalid provenance key '{pkey}' in statement_provenance for {acc}")
    if "empirical_evidence" in prov["empirical_status"].lower():
        raise ValueError(f"Disallowed empirical claim in provenance for {acc}")


def validate_feasibility_document(doc: dict[str, Any]) -> None:
    """Validates top-level document structure, governance flags, and candidates."""
    if not isinstance(doc, dict):
        raise ValueError("Document must be a dict")

    _check_finite_values(doc, "feasibility_document")

    # Governance flags
    if doc.get("scientific_pass") is not False:
        raise ValueError("scientific_pass must be False in feasibility documentation")
    if doc.get("empirical_claim_allowed") is not False:
        raise ValueError("empirical_claim_allowed must be False")
    if doc.get("participant_data_downloaded") is not False:
        raise ValueError("participant_data_downloaded must be False")
    if doc.get("participant_data_analyzed") is not False:
        raise ValueError("participant_data_analyzed must be False")
    if doc.get("analysis_performed") is not False:
        raise ValueError("analysis_performed must be False")

    posture = doc.get("posture", "")
    if "HOLD" not in posture or "SYNTHETIC_ONLY" not in posture:
        raise ValueError(f"Posture must reflect HOLD / SYNTHETIC_ONLY; got {posture!r}")

    candidates = doc.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 4:
        raise ValueError("Document must contain at least 4 candidate records")

    for cand in candidates:
        validate_dataset_candidate_record(cand)


# ── Canonical Document & Candidate Tests ──────────────────────────────────────


def test_document_passes_full_schema() -> None:
    doc = load_candidate_matrix()
    validate_feasibility_document(doc)


def test_no_download_and_no_pass() -> None:
    doc = load_candidate_matrix()
    assert doc["participant_data_downloaded"] is False
    assert doc["participant_data_analyzed"] is False
    assert doc["analysis_performed"] is False
    assert doc["scientific_pass"] is False
    assert doc["empirical_claim_allowed"] is False
    text = DOC.read_text(encoding="utf-8").lower()
    assert "no participant data were downloaded" in text
    assert "not empirical evidence" in text
    assert "scientific pass" in text


def test_required_accessions_and_sources() -> None:
    doc = load_candidate_matrix()
    accessions = {item["accession"] for item in doc["candidates"]}
    assert REQUIRED_ACCESSIONS.issubset(accessions)
    for item in doc["candidates"]:
        assert item["source_url"].startswith("https://openneuro.org/datasets/")


def test_finite_json_and_deterministic() -> None:
    raw = MATRIX.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    dumped = json.dumps(parsed, sort_keys=True, allow_nan=False)
    assert dumped == json.dumps(json.loads(raw), sort_keys=True, allow_nan=False)
    assert parsed["access_date"] == "2026-10-16"
    assert parsed["last_verified_date"] == "2026-10-22"


def test_ds005620_license_conflict_acknowledged_and_preserved() -> None:
    doc = load_candidate_matrix()
    ds = next(item for item in doc["candidates"] if item["accession"] == "ds005620")
    assert ds["role"] == "reference_not_replication"
    assert ds["recommendation"] == "reference_only"
    assert ds["license_conflict"] is True
    assert "license_conflict_cc0_vs_cc_by_4_0" in ds["blockers"]
    assert "same_cohort_as_primary_reference" in ds["blockers"]
    assert "CC0" in ds["license_declarations"]["dataset_description_license"]
    assert "CC-BY-4.0" in ds["license_declarations"]["readme_license"]
    assert ds["license_declarations"]["conflict_status"] == "unresolved_conflict_preserved"


def test_ds003969_primary_candidate_provenance() -> None:
    doc = load_candidate_matrix()
    ds = next(item for item in doc["candidates"] if item["accession"] == "ds003969")
    assert ds["rank"] == 1
    assert ds["role"] == "primary_independent_replication_candidate"
    assert ds["catalog_n"] == 98
    assert ds["analyzed_n"] is None
    assert ds["doi"] == "10.18112/openneuro.ds003969.v1.0.0"
    assert ds["license"] == "CC0"
    assert ds["license_conflict"] is False
    assert "participant_count_subgroup_discrepancy" in ds["blockers"]
    assert "1024 Hz" in ds["channel_montage_sampling"]
    assert "BioSemi ActiveTwo 64 channels" in ds["channel_montage_sampling"]


def test_ds008836_reconciled_catalog_metadata() -> None:
    doc = load_candidate_matrix()
    ds = next(item for item in doc["candidates"] if item["accession"] == "ds008836")
    assert ds["rank"] == 2
    assert ds["role"] == "autonomic_covariate_candidate"
    assert ds["catalog_n"] == 39
    assert ds["analyzed_n"] is None
    assert ds["doi"] == "10.18112/openneuro.ds008836.v1.0.0"
    assert ds["license"] == "CC0"
    assert ds["license_conflict"] is False
    assert ds["recommendation"] == "rank_2_after_license_check"
    assert "companion_paper_unindexed" in ds["blockers"]
    assert "ECG, respiration, EMG, and electrodermal activity" in ds["channel_montage_sampling"]


def test_catalog_n_not_treated_as_analyzed_n() -> None:
    doc = load_candidate_matrix()
    for item in doc["candidates"]:
        assert item["analyzed_n"] is None
        assert item["analyzed_n_status"] in VALID_ANALYZED_N_STATUSES
        assert item["catalog_n"] > 0


def test_no_unsupported_ready_or_empirical_claims() -> None:
    doc = load_candidate_matrix()
    assert doc.get("empirical_claim_allowed") is False
    assert doc.get("scientific_pass") is False
    for item in doc["candidates"]:
        rec = item.get("recommendation", "").lower()
        for forbidden in DISALLOWED_OVERCLAIM_SUBSTRINGS:
            assert forbidden not in rec


def test_non_eeg_entries_documented() -> None:
    doc = load_candidate_matrix()
    non_eeg = doc.get("not_eeg_datasets", [])
    assert any(entry["name"] == "maziyarpanahi/openmed" for entry in non_eeg)
    for entry in non_eeg:
        assert "Not an EEG" in entry["purpose_from_official_repo"]

    ds003171 = next(item for item in doc["candidates"] if item["accession"] == "ds003171")
    assert ds003171["recommendation"] == "exclude"
    assert "not_eeg_or_meg" in ds003171["blockers"]


def test_statement_provenance_distinguishes_author_assertions_from_independent_sources() -> None:
    doc = load_candidate_matrix()
    for item in doc["candidates"]:
        prov = item["statement_provenance"]
        assert "catalog_n_provenance" in prov
        assert "license_provenance" in prov
        assert "doi_provenance" in prov
        assert "hardware_and_sampling_provenance" in prov
        assert "empirical_status" in prov
        # No candidate may claim empirical status
        assert prov["empirical_status"] in {
            "unverified_feasibility_metadata_only",
            "unverified_no_analysis_performed",
        }


# ── Adversarial & Negative Schema Tests ───────────────────────────────────────


def _get_valid_sample_candidate() -> dict[str, Any]:
    doc = load_candidate_matrix()
    return copy.deepcopy(doc["candidates"][1])  # ds003969


def test_adversarial_rejects_missing_required_field() -> None:
    cand = _get_valid_sample_candidate()
    del cand["accession"]
    with pytest.raises(ValueError, match="missing required field 'accession'"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_malformed_accession() -> None:
    cand = _get_valid_sample_candidate()
    cand["accession"] = "invalid_acc_123"
    with pytest.raises(ValueError, match="Invalid accession format"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_non_https_url() -> None:
    cand = _get_valid_sample_candidate()
    cand["source_url"] = "http://openneuro.org/datasets/ds003969"
    with pytest.raises(ValueError, match="source_url must be a secure https URL"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_non_finite_numeric() -> None:
    cand = _get_valid_sample_candidate()
    cand["catalog_n"] = float("nan")
    with pytest.raises(ValueError, match="Non-finite float value found"):
        validate_dataset_candidate_record(cand)

    cand["catalog_n"] = float("inf")
    with pytest.raises(ValueError, match="Non-finite float value found"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_overclaiming_recommendation() -> None:
    cand = _get_valid_sample_candidate()
    cand["recommendation"] = "ready"
    with pytest.raises(ValueError, match="Disallowed recommendation 'ready'"):
        validate_dataset_candidate_record(cand)

    cand["recommendation"] = "empirically_validated"
    with pytest.raises(ValueError, match="Disallowed recommendation"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_promotion_of_catalog_n_to_analyzed_n() -> None:
    cand = _get_valid_sample_candidate()
    cand["analyzed_n"] = cand["catalog_n"]
    with pytest.raises(ValueError, match="analyzed_n must be null/None"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_unacknowledged_license_conflict() -> None:
    cand = _get_valid_sample_candidate()
    cand["license_conflict"] = True
    # blockers does not have license_conflict
    cand["blockers"] = ["some_other_blocker"]
    with pytest.raises(ValueError, match="flags license_conflict=True but has no license_conflict blocker"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_empty_or_malformed_blockers() -> None:
    cand = _get_valid_sample_candidate()
    cand["blockers"] = []
    with pytest.raises(ValueError, match="blockers must be a non-empty list"):
        validate_dataset_candidate_record(cand)

    cand["blockers"] = ["valid_blocker", ""]
    with pytest.raises(ValueError, match="Invalid blocker entry"):
        validate_dataset_candidate_record(cand)

    cand["blockers"] = [123]  # type: ignore[list-item]
    with pytest.raises(ValueError, match="Invalid blocker entry"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_analysis_performed_inspection_level() -> None:
    cand = _get_valid_sample_candidate()
    cand["inspection_level"] = "analysis_performed"
    with pytest.raises(ValueError, match="Invalid inspection_level 'analysis_performed'"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_document_overclaim() -> None:
    doc = load_candidate_matrix()
    doc_copy = copy.deepcopy(doc)
    doc_copy["scientific_pass"] = True
    with pytest.raises(ValueError, match="scientific_pass must be False"):
        validate_feasibility_document(doc_copy)

    doc_copy = copy.deepcopy(doc)
    doc_copy["empirical_claim_allowed"] = True
    with pytest.raises(ValueError, match="empirical_claim_allowed must be False"):
        validate_feasibility_document(doc_copy)


def test_adversarial_rejects_missing_provenance() -> None:
    cand = _get_valid_sample_candidate()
    del cand["statement_provenance"]
    with pytest.raises(ValueError, match="missing required field 'statement_provenance'"):
        validate_dataset_candidate_record(cand)


def test_adversarial_rejects_empirical_status_claim() -> None:
    cand = _get_valid_sample_candidate()
    cand["statement_provenance"]["empirical_status"] = "validated_empirical_evidence"
    with pytest.raises(ValueError, match="Disallowed empirical claim in provenance"):
        validate_dataset_candidate_record(cand)
