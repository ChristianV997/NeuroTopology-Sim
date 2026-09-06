"""Stable hashes and sort_keys-stable InventorySnapshot.to_dict dumps."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tools.retrofit_inventory.scanner import (
    build_inventory_snapshot,
    scan_repository_files,
    snapshot_to_json,
)
from tools.retrofit_inventory.validators import (
    HASH_POLICIES,
    validate_hash_fields,
    validate_hash_stability,
    validate_inventory_snapshot,
    validate_snapshot_to_dict_stability,
)

from .conftest import make_file_entry, make_snapshot


def test_hash_policy_and_hex_contract():
    assert validate_hash_fields("deadbeef", "content_sha256", prefix="files[0]") == []
    assert validate_hash_fields("deadbeef", "size_path_v1", prefix="files[0]") == []
    errors = validate_hash_fields("", "nope", prefix="files[0]")
    assert any("content_hash" in item for item in errors)
    assert any("hash_policy" in item for item in errors)
    assert HASH_POLICIES == {"content_sha256", "size_path_v1"}
    assert validate_hash_fields("not-hex!", "content_sha256", prefix="files[0]")


def test_two_file_scans_of_same_tree_have_equal_hashes(tiny_repo: Path):
    first = scan_repository_files(tiny_repo)
    second = scan_repository_files(tiny_repo)
    assert first
    assert [row.content_hash for row in first] == [row.content_hash for row in second]
    assert [row.hash_policy for row in first] == [row.hash_policy for row in second]
    for row in first:
        assert row.content_hash
        assert all(ch in "0123456789abcdef" for ch in row.content_hash.lower())
        assert row.hash_policy in HASH_POLICIES


def test_mtime_change_does_not_change_content_hash(tiny_repo: Path):
    first = {row.path: row.content_hash for row in scan_repository_files(tiny_repo)}
    target = tiny_repo / "src" / "app.py"
    os.utime(target, (target.stat().st_atime, target.stat().st_mtime + 10))
    second = {row.path: row.content_hash for row in scan_repository_files(tiny_repo)}
    assert first == second


def test_two_snapshot_builds_are_hash_and_dict_stable(tiny_repo: Path):
    first = build_inventory_snapshot(tiny_repo)
    second = build_inventory_snapshot(tiny_repo)
    assert validate_hash_stability(first, second) == []
    assert validate_snapshot_to_dict_stability(first, second) == []
    dumped_a = json.dumps(first.to_dict(), sort_keys=True)
    dumped_b = json.dumps(second.to_dict(), sort_keys=True)
    assert dumped_a == dumped_b
    assert snapshot_to_json(first) == snapshot_to_json(second)
    assert validate_inventory_snapshot(first, repo_root=tiny_repo) == []


def test_constructed_to_dict_is_sort_keys_stable_across_two_builds():
    first = make_snapshot(files=[make_file_entry("b.py"), make_file_entry("a.py")])
    second = make_snapshot(files=[make_file_entry("b.py"), make_file_entry("a.py")])
    assert validate_snapshot_to_dict_stability(first, second) == []
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )
