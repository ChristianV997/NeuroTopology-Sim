import pytest

from tools.release_manifest.merge_state import MergeStateContext, classify_merge_state, classify_release_state
from tools.release_manifest.models import PRSnapshot


def test_unresolvable_commit_is_unknown():
    ctx = MergeStateContext(commit_resolves=False)
    state, blockers = classify_merge_state(ctx)
    assert state == "unknown"
    assert blockers


def test_ancestor_of_target_is_merged_into_main():
    ctx = MergeStateContext(commit_resolves=True, is_ancestor_of_target=True)
    state, _ = classify_merge_state(ctx)
    assert state == "merged_into_main"


def test_pr_snapshot_merged_true_overrides_missing_ancestry():
    pr = PRSnapshot(number=1, state="closed", merged=True, base_ref="main")
    ctx = MergeStateContext(commit_resolves=True, target_branch="main", pr_snapshot=pr)
    state, blockers = classify_merge_state(ctx)
    assert state == "merged_into_main"
    assert any("contradiction" in b for b in blockers)


def test_pr_merged_to_different_base_is_not_merged_into_target():
    pr = PRSnapshot(number=1, state="closed", merged=True, base_ref="release")
    ctx = MergeStateContext(commit_resolves=True, target_branch="main", pr_snapshot=pr)

    state, blockers = classify_merge_state(ctx)

    assert state != "merged_into_main"
    assert any("target_branch" in blocker for blocker in blockers)


def test_pr_snapshot_says_not_merged_but_ancestry_says_merged_ancestry_wins():
    pr = PRSnapshot(number=1, state="open", merged=False)
    ctx = MergeStateContext(commit_resolves=True, is_current_head_of_target=True, pr_snapshot=pr)
    state, blockers = classify_merge_state(ctx)
    assert state == "merged_into_main"
    assert any("contradiction" in b for b in blockers)


def test_integration_only():
    ctx = MergeStateContext(commit_resolves=True, is_ancestor_of_integration=True)
    state, _ = classify_merge_state(ctx)
    assert state == "integration_only"


def test_stale_off_all_lineages_with_no_pr_snapshot():
    ctx = MergeStateContext(commit_resolves=True)
    state, _ = classify_merge_state(ctx)
    assert state == "ancestor_stale"


def test_open_unintegrated_with_pr_snapshot():
    pr = PRSnapshot(number=7, state="open", merged=False)
    ctx = MergeStateContext(commit_resolves=True, pr_snapshot=pr)
    state, _ = classify_merge_state(ctx)
    assert state == "open_unintegrated"


def test_superseded_closed_pr_with_superseded_by():
    pr = PRSnapshot(number=7, state="closed", merged=False)
    ctx = MergeStateContext(commit_resolves=True, pr_snapshot=pr, superseded_by="PR #99")
    state, blockers = classify_merge_state(ctx)
    assert state == "superseded"


def test_blocked_by_ci_outranks_infrastructure():
    ctx = MergeStateContext(commit_resolves=True, worst_ci_state="failing")
    state, _ = classify_merge_state(ctx)
    assert state == "blocked_by_ci"


def test_blocked_by_infrastructure():
    ctx = MergeStateContext(commit_resolves=True, worst_ci_state="infrastructure_blocked")
    state, _ = classify_merge_state(ctx)
    assert state == "blocked_by_infrastructure"


def test_blocked_by_scientific_review_outranks_ci():
    ctx = MergeStateContext(commit_resolves=True, worst_ci_state="failing", scientific_blocking=True)
    state, _ = classify_merge_state(ctx)
    assert state == "blocked_by_scientific_review"


def test_blocked_by_dependency():
    ctx = MergeStateContext(commit_resolves=True, dependency_blockers=("needs PR #1",))
    state, _ = classify_merge_state(ctx)
    assert state == "blocked_by_dependency"


def test_duplicate_outranks_ci_and_dependency():
    ctx = MergeStateContext(
        commit_resolves=True,
        duplicate_findings=("['a', 'b']",),
        worst_ci_state="failing",
        dependency_blockers=("dep",),
    )
    state, _ = classify_merge_state(ctx)
    assert state == "duplicate"


def test_merged_into_main_outranks_duplicate():
    ctx = MergeStateContext(
        commit_resolves=True,
        is_ancestor_of_target=True,
        duplicate_findings=("['a', 'b']",),
    )
    state, _ = classify_merge_state(ctx)
    assert state == "merged_into_main"


def test_invalid_ci_state_raises():
    ctx = MergeStateContext(commit_resolves=True, worst_ci_state="not-a-real-state")
    with pytest.raises(ValueError):
        classify_merge_state(ctx)
    with pytest.raises(ValueError):
        classify_release_state(
            ctx,
            merge_state="open_unintegrated",
            scientific_gate_value="insufficient_data",
        )


def test_release_state_is_independent_from_technical_merge_state():
    ctx = MergeStateContext(commit_resolves=True, is_ancestor_of_target=True, scientific_blocking=True)
    merge_state, _ = classify_merge_state(ctx)
    release_state, blockers = classify_release_state(
        ctx,
        merge_state=merge_state,
        scientific_gate_value="blocked",
    )
    assert merge_state == "merged_into_main"
    assert release_state == "blocked_by_scientific_review"
    assert blockers


def test_merged_commit_without_independent_evidence_is_release_inconclusive():
    ctx = MergeStateContext(commit_resolves=True, is_ancestor_of_target=True)
    merge_state, _ = classify_merge_state(ctx)
    release_state, blockers = classify_release_state(
        ctx,
        merge_state=merge_state,
        scientific_gate_value="insufficient_data",
    )
    assert merge_state == "merged_into_main"
    assert release_state == "inconclusive"
    assert blockers


@pytest.mark.parametrize("ci_state", ["unavailable", "pending", "skipped"])
def test_release_is_not_ready_until_required_ci_is_passing(ci_state):
    ctx = MergeStateContext(
        commit_resolves=True,
        is_ancestor_of_target=True,
        worst_ci_state=ci_state,
    )

    release_state, blockers = classify_release_state(
        ctx,
        merge_state="merged_into_main",
        scientific_gate_value="pass",
    )

    assert release_state == "inconclusive"
    assert blockers
