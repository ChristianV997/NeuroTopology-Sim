"""End-to-end reconcile() proving stacked-PR awareness and the
scientific-gate/current-status fields are wired together correctly."""
from __future__ import annotations

from tools.integration_reconciliation import github_source, reconcile
from tools.integration_reconciliation.models import WorkOrder


def _stacked_snapshot():
    return {
        "schema": github_source.SNAPSHOT_SCHEMA,
        "pull_requests": [
            {
                "number": 1, "head_ref": "feature-a", "base_ref": "main",
                "state": "open", "draft": False, "merged": False,
                "mergeable_state": "clean",
                "checks": {"tests": "success"},
                "body": "Adds shared/a.py.",
            },
            {
                "number": 2, "head_ref": "stacked-on-feature-a", "base_ref": "feature-a",
                "state": "open", "draft": False, "merged": False,
                "mergeable_state": "unstable",
                "checks": {"tests": {"status": "completed", "conclusion": "failure", "failure_signature": "No space left on device"}},
                "body": "Stacked on #1. Adds stacked_only.py.",
            },
        ],
    }


def _work_orders():
    return (
        WorkOrder("base", "base work", expected_branch="feature-a", reported_pr_number=1),
        WorkOrder("dependent", "dependent work", expected_branch="stacked-on-feature-a", reported_pr_number=2),
    )


def test_dependent_work_order_is_marked_stacked(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    dependent = next(e for e in report.entries if e.work_order.work_order_id == "dependent")
    assert dependent.stack is not None
    assert dependent.stack.is_stacked.value is True
    assert dependent.stack.base_work_order_id.value == "base"


def test_base_work_order_lists_the_dependent(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    base = next(e for e in report.entries if e.work_order.work_order_id == "base")
    assert base.stack is not None
    assert base.stack.dependents.value == ["dependent"]


def test_dependent_effective_diff_excludes_base_files(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    dependent = next(e for e in report.entries if e.work_order.work_order_id == "dependent")
    assert dependent.effective_changed_files is not None
    assert dependent.effective_changed_files.value == ["stacked_only.py"]


def test_dependent_raw_branch_diff_still_shows_full_diff_for_transparency(git_fixture_repo):
    """The raw branch.changed_files field (used for the repo-wide overlap
    check) intentionally still reports the FULL diff against main -- only
    effective_changed_files is base-relative. Both are kept, clearly
    labeled, so neither hides the other's information."""
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    dependent = next(e for e in report.entries if e.work_order.work_order_id == "dependent")
    assert "shared/a.py" in dependent.branch.changed_files.value


def test_infrastructure_blocked_check_surfaces_in_checks_status(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    dependent = next(e for e in report.entries if e.work_order.work_order_id == "dependent")
    assert dependent.current_status is not None
    assert dependent.current_status.checks_status.value == "infrastructure_blocked"
    assert dependent.current_status.billing_blocked.value is False


def test_lifecycle_state_open_for_non_draft_open_pr(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    base = next(e for e in report.entries if e.work_order.work_order_id == "base")
    assert base.current_status.lifecycle_state.value == "open"


def test_mergeability_string_values(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    base = next(e for e in report.entries if e.work_order.work_order_id == "base")
    dependent = next(e for e in report.entries if e.work_order.work_order_id == "dependent")
    assert base.current_status.mergeability.value == "mergeable"
    assert dependent.current_status.mergeability.value == "unknown"


def test_scientific_gate_hints_present_on_every_entry(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    for entry in report.entries:
        assert entry.scientific_gate_hints is not None
        assert "scientific_review_required" in entry.scientific_gate_hints


def test_no_duplicate_flagged_for_a_legitimate_stack(git_fixture_repo):
    """Stacked PRs' effective diffs are disjoint by construction (base's
    files vs. the stacked PR's own new files) -- they must never be
    reported as a possible duplicate of each other."""
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    assert report.possible_duplicates == []


def test_no_superseded_flagged_for_a_legitimate_stack(git_fixture_repo):
    """Regression: a stacked PR's branch is *always* a git descendant of
    its base's branch by construction -- that must never be reported as
    "base is superseded by dependent". This reproduced as a real false
    positive during round-2 development (streaming-performance incorrectly
    reported as superseded by process-memory-telemetry, which is actually
    stacked on top of it) before stacked pairs were excluded from the
    ancestry check."""
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    assert report.superseded_work == []


def test_file_overlaps_use_effective_diffs_not_raw_stacked_diffs(git_fixture_repo):
    """Regression: the raw branch diff of a stacked PR against target_ref
    necessarily repeats its base's files (shared/a.py here) -- reporting
    that as a "file overlap" between the two work orders would be a false
    conflict signal for expected lineage. file_overlaps must be computed
    from effective (base-relative) diffs instead."""
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_stacked_snapshot())
    assert report.file_overlaps == {}
