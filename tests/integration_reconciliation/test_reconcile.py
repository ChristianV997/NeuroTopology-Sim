"""End-to-end reconcile() against a local git fixture repo + a mocked
(in-memory dict) GitHub snapshot -- no network anywhere in this file."""
from __future__ import annotations

from tools.integration_reconciliation import github_source, reconcile
from tools.integration_reconciliation.models import WorkOrder


def _mock_snapshot():
    return {
        "schema": github_source.SNAPSHOT_SCHEMA,
        "pull_requests": [
            {
                "number": 1,
                "head_ref": "feature-a",
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable_state": "clean",
                "checks": {"tests": "success"},
            },
            {
                "number": 2,
                "head_ref": "with-artifact",
                "state": "open",
                "draft": True,
                "merged": False,
                "mergeable_state": "unstable",
                "checks": {"tests": "failure"},
            },
        ],
    }


def _work_orders():
    return (
        WorkOrder("wo-a", "feature A", expected_branch="feature-a", reported_pr_number=1),
        WorkOrder("wo-b", "feature B", expected_branch="feature-b", reported_pr_number=None),
        WorkOrder(
            "wo-merged", "already merged work", expected_branch="already-merged", reported_pr_number=None,
        ),
        WorkOrder(
            "wo-missing", "reported but branch never pushed", expected_branch="never-pushed",
            reported_pr_number=None, reported_status_note="reported pushed but not found",
        ),
        WorkOrder(
            "wo-artifact", "work with a committed artifact", expected_branch="with-artifact",
            reported_pr_number=None,
        ),
    )


def test_reconcile_marks_branch_and_pr_present_for_feature_a(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    entry = next(e for e in report.entries if e.work_order.work_order_id == "wo-a")
    assert entry.stages["branch_present"].value is True
    assert entry.stages["pr_present"].value is True
    assert entry.stages["checks_passing"].value is True
    assert entry.stages["mergeable"].value is True
    assert entry.stages["merged"].value is False


def test_reconcile_missing_branch_has_all_downstream_stages_none_or_false(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    entry = next(e for e in report.entries if e.work_order.work_order_id == "wo-missing")
    assert entry.stages["branch_present"].value is False
    assert entry.stages["pr_present"].value is False
    assert entry.stages["reported"].value is True  # it was still a reported work order


def test_reconcile_detects_already_merged_branch(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    entry = next(e for e in report.entries if e.work_order.work_order_id == "wo-merged")
    assert entry.branch.is_ancestor_of_target.value is True


def test_reconcile_flags_committed_artifact(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    assert "wo-artifact" in report.artifact_commit_findings
    assert "artifacts/RunRecord.json" in report.artifact_commit_findings["wo-artifact"]


def test_reconcile_reports_file_overlap_between_feature_a_and_feature_b(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    assert report.file_overlaps.get("wo-a|wo-b") == ["shared/a.py"]


def test_reconcile_without_a_snapshot_leaves_pr_fields_null(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=None)
    entry = next(e for e in report.entries if e.work_order.work_order_id == "wo-a")
    assert entry.stages["pr_present"].value is False
    assert entry.pr.number.value is None
    assert "no github snapshot" in entry.pr.number.source or "no matching entry" in entry.pr.number.source


def test_reconcile_base_commit_is_resolved(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    assert report.base_commit is not None
    assert len(report.base_commit) == 40


def test_reconcile_note_flags_stale_no_pr_report_when_pr_now_exists(git_fixture_repo):
    """wo-artifact's branch 'with-artifact' now has PR #2 in the mock
    snapshot even though the work order itself declared no reported_pr_number
    -- the tool should note this as a stale report, not silently accept it."""
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    entry = next(e for e in report.entries if e.work_order.work_order_id == "wo-artifact")
    assert any("now exists" in note and "stale" in note for note in entry.notes)


def test_reconcile_dashboard_isolation_included_when_requested(git_fixture_repo):
    dashboard_src = git_fixture_repo / "dashboard_src"
    dashboard_src.mkdir()
    (dashboard_src / "app.py").write_text("import json\n", encoding="utf-8")
    report = reconcile.reconcile(
        git_fixture_repo, _work_orders(), target_ref="origin/main",
        github_snapshot=_mock_snapshot(), dashboard_src=dashboard_src,
    )
    assert report.dashboard_isolation is not None
    assert report.dashboard_isolation["ok"] is True


def test_reconcile_dashboard_isolation_none_when_not_requested(git_fixture_repo):
    report = reconcile.reconcile(git_fixture_repo, _work_orders(), target_ref="origin/main", github_snapshot=_mock_snapshot())
    assert report.dashboard_isolation is None
