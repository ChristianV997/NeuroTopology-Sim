"""Shared fixtures for the measurement/hypothesis mapping tests. Offline, fixture data only."""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from shared.measurement_hypothesis import validate_mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
AS_OF = date(2026, 10, 16)  # fixed so access-date checks do not drift with the calendar


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def as_of() -> date:
    return AS_OF


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def valid_mapping(load_fixture):
    """A fresh copy of the valid, explicitly hypothetical example. Mutate freely."""
    return load_fixture("valid_hypothetical_mapping")


@pytest.fixture
def check():
    """Validate a mapping against the real repository with the fixed date."""

    def _check(mapping, repo_root: Path = REPO_ROOT):
        return validate_mapping(copy.deepcopy(mapping), repo_root=repo_root, as_of=AS_OF)

    return _check
