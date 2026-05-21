from tools.github_pr_reconciliation.stale_pr_audit import PRAuditRecord, evaluate, recommended_action


def test_recommended_action_noop_superseded_by_main() -> None:
    record = PRAuditRecord(
        pr_number=144,
        branch="claude/p18-2-runtime-autonomy-kernel",
        mergeability="mergeable",
        changed_files=0,
        additions=0,
        deletions=0,
        status="open",
        unique_commits_vs_main=False,
    )
    assert recommended_action(record) == "close_as_noop_superseded_by_main"


def test_recommended_action_superseded_by_specific_pr() -> None:
    record = PRAuditRecord(
        pr_number=149,
        branch="duplicate",
        mergeability="mergeable",
        changed_files=0,
        additions=0,
        deletions=0,
        status="open",
        unique_commits_vs_main=False,
        superseded_by_pr=150,
    )
    assert recommended_action(record) == "close_as_superseded_by_pr_150"


def test_recommended_action_unique_commits() -> None:
    record = PRAuditRecord(
        pr_number=142,
        branch="legacy",
        mergeability="unknown",
        changed_files=12,
        additions=200,
        deletions=50,
        status="open",
        unique_commits_vs_main=True,
    )
    assert recommended_action(record) == "keep_open_has_unique_commits"


def test_evaluate_includes_required_fields() -> None:
    record = PRAuditRecord(
        pr_number=143,
        branch="legacy-2",
        mergeability="unknown",
        changed_files=0,
        additions=0,
        deletions=0,
        status="open",
        unique_commits_vs_main=None,
    )
    rows = evaluate([record])
    assert rows[0]["pr_number"] == 143
    assert rows[0]["recommended_action"] == "manual_review_required"
    assert "changed_files" in rows[0]
