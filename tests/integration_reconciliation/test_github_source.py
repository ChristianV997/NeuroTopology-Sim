"""github_source: pure data-lookup functions over a plain dict, no network."""
from __future__ import annotations

import json

import pytest

from tools.integration_reconciliation import github_source


def _sample_snapshot():
    return {
        "schema": github_source.SNAPSHOT_SCHEMA,
        "pull_requests": [
            {
                "number": 100,
                "head_ref": "feature-a",
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable_state": "clean",
                "checks": {"tests": "success", "lint": "success"},
            },
            {
                "number": 101,
                "head_ref": "feature-b",
                "state": "open",
                "draft": True,
                "merged": False,
                "mergeable_state": "dirty",
                "checks": {"tests": "failure"},
            },
        ],
    }


def test_load_snapshot_from_dict_round_trips():
    snap = github_source.load_snapshot_from_dict(_sample_snapshot())
    assert snap["schema"] == github_source.SNAPSHOT_SCHEMA


def test_load_snapshot_rejects_missing_pull_requests_key():
    with pytest.raises(ValueError):
        github_source.load_snapshot_from_dict({"schema": "x"})


def test_load_snapshot_from_file(tmp_path):
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(_sample_snapshot()), encoding="utf-8")
    snap = github_source.load_snapshot_from_file(path)
    assert len(snap["pull_requests"]) == 2


def test_empty_snapshot_has_no_pull_requests():
    assert github_source.empty_snapshot()["pull_requests"] == []


def test_find_pr_by_branch_found():
    snap = _sample_snapshot()
    pr = github_source.find_pr_by_branch(snap, "feature-a")
    assert pr is not None
    assert pr["number"] == 100


def test_find_pr_by_branch_not_found():
    snap = _sample_snapshot()
    assert github_source.find_pr_by_branch(snap, "no-such-branch") is None


def test_find_pr_by_number_found():
    snap = _sample_snapshot()
    pr = github_source.find_pr_by_number(snap, 101)
    assert pr is not None
    assert pr["head_ref"] == "feature-b"


def test_find_pr_by_number_not_found():
    snap = _sample_snapshot()
    assert github_source.find_pr_by_number(snap, 999) is None


def test_checks_all_passing_none_when_no_checks():
    assert github_source.checks_all_passing(None) is None
    assert github_source.checks_all_passing({}) is None


def test_checks_all_passing_true_when_all_success():
    assert github_source.checks_all_passing({"a": "success", "b": "success"}) is True


def test_checks_all_passing_false_when_any_failure():
    assert github_source.checks_all_passing({"a": "success", "b": "failure"}) is False


def test_checks_all_passing_false_for_non_success_non_failure_conclusion():
    assert github_source.checks_all_passing({"a": "neutral"}) is False


def test_mergeable_from_state_clean_is_true():
    assert github_source.mergeable_from_state("clean") is True


def test_mergeable_from_state_dirty_is_false():
    assert github_source.mergeable_from_state("dirty") is False


def test_mergeable_from_state_conflicting_is_false():
    assert github_source.mergeable_from_state("conflicting") is False


def test_mergeable_from_state_unstable_is_none():
    assert github_source.mergeable_from_state("unstable") is None


def test_mergeable_from_state_none_is_none():
    assert github_source.mergeable_from_state(None) is None
