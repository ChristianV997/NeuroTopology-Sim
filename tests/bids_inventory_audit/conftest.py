"""Shared fixtures for the synthetic-only BIDS inventory tests. Offline; fixtures are labelled synthetic."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def synthetic_tsv() -> str:
    return (FIXTURES / "synthetic_participants.tsv").read_text(encoding="utf-8")


@pytest.fixture
def synthetic_readme() -> str:
    return (FIXTURES / "synthetic_readme.txt").read_text(encoding="utf-8")


@pytest.fixture
def synthetic_nemar() -> dict:
    return json.loads((FIXTURES / "synthetic_nemar.json").read_text(encoding="utf-8"))


@pytest.fixture
def synthetic_listing() -> list[str]:
    return json.loads((FIXTURES / "synthetic_file_listing.json").read_text(encoding="utf-8"))["paths"]
