from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.awareness_studio_research.store import EvidenceRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry(tmp_path: Path) -> EvidenceRegistry:
    return EvidenceRegistry(tmp_path / "events.jsonl")


@pytest.fixture
def five_sources_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "five_scientific_sources.json").read_text())
