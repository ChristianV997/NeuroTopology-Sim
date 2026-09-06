"""Local fixtures for tool-admission governance tests.

These tests must not import production packages and must not perform I/O
beyond reading the committed registry files.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        marker = candidate / "configs" / "tool_admission" / "tool_registry.yaml"
        if marker.is_file():
            return candidate
    raise FileNotFoundError("configs/tool_admission/tool_registry.yaml not found")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _find_repo_root()


@pytest.fixture(scope="session")
def registry(repo_root: Path) -> dict:
    path = repo_root / "configs" / "tool_admission" / "tool_registry.yaml"
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise TypeError("tool_registry.yaml must deserialize to a mapping")
    return data


@pytest.fixture(scope="session")
def policies(repo_root: Path) -> dict:
    path = repo_root / "configs" / "tool_admission" / "tool_policies.yaml"
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise TypeError("tool_policies.yaml must deserialize to a mapping")
    return data


@pytest.fixture(scope="session")
def sources(repo_root: Path) -> dict:
    import json

    path = repo_root / "configs" / "tool_admission" / "source_registry.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError("source_registry.json must deserialize to an object")
    return data
