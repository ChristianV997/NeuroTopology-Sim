from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.literature_evidence.models import LiteratureRecord
from tools.literature_evidence.store import LiteratureEvidenceStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def load_record(name: str) -> LiteratureRecord:
    return LiteratureRecord.from_dict(load_fixture(name))


@pytest.fixture
def store(tmp_path: Path) -> LiteratureEvidenceStore:
    return LiteratureEvidenceStore(tmp_path / "events.jsonl")
