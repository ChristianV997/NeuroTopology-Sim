"""Tool-source registry validators: modes, count, NotebookLM, duplicates."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from tools.retrofit_inventory.scanner import build_inventory_snapshot
from tools.retrofit_inventory.tool_sources import (
    INTEGRATION_MODES,
    load_tool_sources,
    summarize_tool_sources,
    tool_sources_by_id,
)
from tools.retrofit_inventory.validators import (
    EXPECTED_REAL_TOOL_SOURCE_COUNT,
    NOTEBOOKLM_ADOPTION,
    NOTEBOOKLM_INTEGRATION_MODE,
    NOTEBOOKLM_TOOL_ID,
    validate_integration_mode,
    validate_notebooklm_entry,
    validate_real_tool_sources,
    validate_tool_source_registry,
    validate_tool_source_registry_or_raise,
    validate_tool_source_row,
)

from .conftest import FIXTURES, REPO_ROOT


def test_integration_modes_reuse_research_contract():
    for mode in sorted(INTEGRATION_MODES):
        assert validate_integration_mode(mode) == []
    errors = validate_integration_mode("vendor_into_core")
    assert errors
    assert "vendor_into_core" in errors[0]


def test_real_yaml_has_exactly_fifteen_tools():
    entries = load_tool_sources(REPO_ROOT)
    assert len(entries) == EXPECTED_REAL_TOOL_SOURCE_COUNT == 15
    assert [row["id"] for row in entries] == sorted(row["id"] for row in entries)
    assert validate_real_tool_sources(REPO_ROOT) == []
    assert validate_tool_source_registry(
        entries, expect_count=15, require_notebooklm=True
    ) == []


def test_notebooklm_must_be_experimental_only():
    by_id = tool_sources_by_id(REPO_ROOT)
    row = by_id[NOTEBOOKLM_TOOL_ID]
    assert row["integration_mode"] == NOTEBOOKLM_INTEGRATION_MODE
    assert row["adoption_recommendation"] == NOTEBOOKLM_ADOPTION
    assert validate_notebooklm_entry(row) == []


def test_notebooklm_mutation_fails_if_not_experimental_only():
    mutated = yaml.safe_load(
        (FIXTURES / "malformed" / "notebooklm_not_experimental.yaml").read_text(
            encoding="utf-8"
        )
    )
    errors = validate_notebooklm_entry(mutated)
    assert errors, "notebooklm mutation must hard-fail"
    assert any("experimental" in item for item in errors)
    row_errors = validate_tool_source_row(mutated)
    assert any("experimental" in item for item in row_errors)


def test_duplicate_tool_ids_are_errors_not_warnings():
    entries = load_tool_sources(REPO_ROOT)
    clone = deepcopy(entries[0])
    errors = validate_tool_source_registry(list(entries) + [clone])
    assert any("duplicate tool id" in item for item in errors)
    assert not any("warning" in item.lower() for item in errors)
    with pytest.raises(ValueError, match="duplicate tool id"):
        validate_tool_source_registry_or_raise(list(entries) + [clone], expect_count=16)


def test_secret_in_registry_string_fails():
    entries = load_tool_sources(REPO_ROOT)
    dirty = deepcopy(entries[0])
    dirty["notes"] = "leaked api_key=fixture"
    errors = validate_tool_source_row(dirty)
    assert any("secret pattern" in item for item in errors)


def test_sort_keys_stable_across_two_real_loads():
    first = load_tool_sources(REPO_ROOT)
    second = load_tool_sources(REPO_ROOT)
    dumped_a = json.dumps(first, sort_keys=True)
    dumped_b = json.dumps(second, sort_keys=True)
    assert dumped_a == dumped_b
    summary_a = json.dumps(summarize_tool_sources(entries=first), sort_keys=True)
    summary_b = json.dumps(summarize_tool_sources(entries=second), sort_keys=True)
    assert summary_a == summary_b


def test_build_inventory_snapshot_smoke_on_tiny_fixture(tiny_repo: Path):
    snap = build_inventory_snapshot(tiny_repo)
    assert snap.files
    assert snap.commit_sha
    labeled = [row for row in snap.artifacts if "synthetic" in row.path]
    assert labeled
    assert all(row.label == "synthetic" for row in labeled)
    from tools.retrofit_inventory.validators import validate_inventory_snapshot

    assert validate_inventory_snapshot(snap, repo_root=tiny_repo) == []
