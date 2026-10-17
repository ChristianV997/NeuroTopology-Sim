"""Schema checks for the Batch 3 metadata audit. No network. No PASS."""

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
    assert doc["participant_data_downloaded"] is False
    assert doc["same_mechanism_candidate_present"] is False
    text = DOC.read_text(encoding="utf-8")
    assert "HOLD / SYNTHETIC_ONLY" in text
    assert "No participant data downloaded" in text


def test_license_conflict_preserved() -> None:
    doc = load()
    ref = next(item for item in doc["candidates"] if item["accession"] == "ds005620")
    assert ref["license_evidence"]["conflict"] is True
    assert "CC0" in ref["license_evidence"]["dataset_description_json"]
    assert "CC-BY" in ref["license_evidence"]["github_readme"]


def test_required_fields_and_finite_json() -> None:
    doc = load()
    required = {"accession", "doi", "license_evidence", "catalog_participants", "fit"}
    for item in doc["candidates"]:
        assert required.issubset(item)
        assert item["doi"].startswith("10.")
    dumped = json.dumps(doc, sort_keys=True, allow_nan=False)
    assert json.loads(dumped)["research_date"] == "2026-10-16"
