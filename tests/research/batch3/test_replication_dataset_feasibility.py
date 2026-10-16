"""Schema checks for the Batch 3 replication feasibility package.

No network. No dataset download. No scientific PASS.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "reports" / "batch3" / "grok_chat_b" / "dataset_candidates.json"
DOC = ROOT / "docs" / "research" / "batch3" / "replication_dataset_feasibility.md"

REQUIRED = {"ds005620", "ds003969", "ds001787", "ds004572"}


def load() -> dict:
    doc = json.loads(MATRIX.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("matrix must be an object")
    return doc


def test_no_download_and_no_pass() -> None:
    doc = load()
    assert doc["participant_data_downloaded"] is False
    assert doc["participant_data_analyzed"] is False
    assert doc["analysis_performed"] is False
    assert doc["scientific_pass"] is False
    text = DOC.read_text(encoding="utf-8").lower()
    assert "no participant data were downloaded" in text
    assert "not empirical evidence" in text


def test_required_accessions_and_sources() -> None:
    doc = load()
    ids = {item["accession"] for item in doc["candidates"]}
    assert REQUIRED.issubset(ids)
    for item in doc["candidates"]:
        assert item["source_url"].startswith("https://")
        assert item["inspection_level"] in {
            "listed_in_catalog",
            "metadata_inspected",
            "files_locally_available",
            "analysis_performed",
        }
        assert item["inspection_level"] != "analysis_performed"
        assert item["files_locally_available"] is not True if "files_locally_available" in item else True


def test_finite_json_and_deterministic() -> None:
    raw = MATRIX.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    dumped = json.dumps(parsed, sort_keys=True, allow_nan=False)
    assert dumped == json.dumps(json.loads(raw), sort_keys=True, allow_nan=False)
    assert parsed["access_date"] == "2026-10-16"
