from __future__ import annotations

import json
import subprocess

from tools.integration_reconciliation import duplicate_detection, git_source
from tools.integration_reconciliation.fixture_audit import audit_ancestry, audit_references
from tests.integration_reconciliation.fixtures.stacked_repository import (
    build_stacked_fixture,
    repeated_fixture_fingerprint,
)


def test_fixture_has_real_stack_and_explicit_branch_inventory(tmp_path):
    fixture = build_stacked_fixture(tmp_path)
    audited = audit_references(
        fixture.repo,
        fixture.refs.values(),
        required_branches=(
            fixture.refs["parent-feature"],
            fixture.refs["stacked-child"],
            fixture.refs["unrelated"],
            fixture.refs["superseded"],
            fixture.refs["conflicting"],
        ),
    )
    by_ref = {item["reference"]: item for item in audited}
    assert by_ref[fixture.refs["parent-feature"]]["classification"] == "valid_branch"
    assert by_ref[fixture.refs["stacked-child"]]["classification"] == "valid_branch"
    assert by_ref[fixture.refs["missing"]]["classification"] == "missing_reference"
    assert by_ref[fixture.refs["fabricated"]]["classification"] == "missing_reference"
    assert git_source.is_ancestor(
        fixture.repo, fixture.refs["parent-feature"], fixture.refs["stacked-child"]
    ) is True


def test_fixture_covers_supersession_duplicate_and_conflict_cases(tmp_path):
    fixture = build_stacked_fixture(tmp_path)
    assert audit_ancestry(
        fixture.repo, fixture.refs["superseded"], fixture.refs["replacement"]
    )["ancestry_valid"] is True
    missing_parent = audit_ancestry(
        fixture.repo, fixture.refs["missing"], fixture.refs["stacked-child"]
    )
    assert missing_parent["ancestry"] is None
    assert missing_parent["ancestry_valid"] is False
    files_a = git_source.changed_files(
        fixture.repo, fixture.refs["main"], fixture.refs["duplicate-work"]
    )
    files_b = git_source.changed_files(
        fixture.repo, fixture.refs["main"], fixture.refs["duplicate-work-twin"]
    )
    duplicate = duplicate_detection.detect_possible_duplicates(
        {"first": files_a, "second": files_b}
    )
    assert duplicate and duplicate[0]["shared_files"] == ["duplicate.txt"]
    merge_tree = subprocess.run(
        [
            "git", "-C", str(fixture.repo), "merge-tree", "--write-tree",
            fixture.refs["parent-feature"], fixture.refs["conflicting"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert merge_tree.returncode != 0


def test_local_merge_ancestry_does_not_verify_pr_merge_claim(tmp_path):
    fixture = build_stacked_fixture(tmp_path)
    evidence = audit_ancestry(
        fixture.repo,
        fixture.refs["parent-feature"],
        fixture.refs["stacked-child"],
        textual_pr_claim=True,
    )
    assert evidence["ancestry_valid"] is True
    assert evidence["textual_pr_claim"] is True
    assert evidence["pr_merge_verified"] is False


def test_fixture_is_deterministic_and_json_serializable(tmp_path):
    first = build_stacked_fixture(tmp_path / "first")
    second = build_stacked_fixture(tmp_path / "second")
    assert repeated_fixture_fingerprint(first) == repeated_fixture_fingerprint(second)
    payload = audit_references(
        first.repo,
        first.refs.values(),
        required_branches=(first.refs["stacked-child"],),
    )
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_fixture_audit_is_local_only_and_does_not_add_remotes(tmp_path):
    fixture = build_stacked_fixture(tmp_path)
    audit_references(fixture.repo, fixture.refs.values())
    remotes = subprocess.run(
        ["git", "-C", str(fixture.repo), "remote"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert remotes.stdout == ""
