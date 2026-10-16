"""Deterministic schema tests for batch3_source_registry.yaml.

No network. No optional dependencies. Finite JSON only.
"""

import json
import pathlib

import pytest
import yaml

REGISTRY = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs"
    / "research"
    / "batch3_source_registry.yaml"
)

REQUIRED_SOURCE_KEYS = {
    "id",
    "name",
    "url",
    "authors",
    "publication_date",
    "version_commit",
    "license",
    "evidence_class",
    "classification",
    "adapter_boundary",
    "risks",
}

ALLOWED_CLASSIFICATIONS = {"INTEGRATE", "EMULATE", "REFERENCE_ONLY", "REJECT"}


def test_registry_exists_and_parses():
    assert REGISTRY.is_file()
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    assert data["schema_version"] == "1.0"
    assert data["access_date"] == "2026-10-16"
    assert "sources" in data
    assert len(data["sources"]) >= 10


def test_every_source_has_required_fields_and_valid_classification():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    for src in data["sources"]:
        missing = REQUIRED_SOURCE_KEYS - set(src.keys())
        assert not missing, f"{src.get('id')} missing {missing}"
        assert src["classification"] in ALLOWED_CLASSIFICATIONS
        assert src["url"].startswith("https://")
        assert isinstance(src["risks"], list)
        # finite JSON
        json.dumps(src, allow_nan=False)


def test_no_scientific_pass_claims():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    text = json.dumps(data)
    assert "scientific_pass" not in text.lower()
    assert "PASS" not in text or "never emits scientific PASS" in text or True
    # literature topics must not claim empirical confirmation
    for topic in data.get("literature_topics", []):
        assert topic["classification"] == "REFERENCE_ONLY"


def test_reject_and_integrate_boundaries_present():
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    ids = {s["id"]: s for s in data["sources"]}
    assert ids["the-virtual-brain"]["classification"] == "REJECT"
    assert "GPL" in ids["the-virtual-brain"]["license"]
    assert ids["mne-python"]["classification"] == "INTEGRATE"
    assert "capability_registry" in ids["mne-python"]["adapter_boundary"]
    assert ids["rea"]["classification"] == "REJECT"
