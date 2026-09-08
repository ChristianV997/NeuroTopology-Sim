from __future__ import annotations

from tools.integration_state import merge_verification
from tools.integration_state.models import PRSnapshot


def test_integrated_pr_found_in_history(state_fixture_repo):
    findings = merge_verification.verify_integrated_pr_history(
        state_fixture_repo["repo"], "integration", (100, 200),
    )
    by_number = {f["pr_number"]: f for f in findings}
    assert by_number[100]["found_in_integration_branch_history"] is True
    assert by_number[200]["found_in_integration_branch_history"] is True
    assert by_number[100]["merge_commit"] is not None


def test_pr_not_actually_integrated_is_reported_not_found(state_fixture_repo):
    findings = merge_verification.verify_integrated_pr_history(
        state_fixture_repo["repo"], "integration", (999,),
    )
    assert findings[0]["found_in_integration_branch_history"] is False
    assert findings[0]["merge_commit"] is None


def test_merged_into_main_uses_authoritative_pr_field_not_local_ancestry_alone(state_fixture_repo):
    """The fixture's `integration` branch is NOT an ancestor of `main`
    (they diverged), but if a PR snapshot explicitly says merged=True,
    that authoritative field is what's reported -- with a note flagging
    the contradiction against local ancestry, never silently resolved
    one way or the other."""
    pr = PRSnapshot(number=1, merged=True)
    evidence = merge_verification.check_merged_into_main(state_fixture_repo["repo"], "integration", "main", pr)
    assert evidence.value is True
    assert "NOTE" in evidence.source


def test_merged_into_main_false_when_pr_says_not_merged(state_fixture_repo):
    pr = PRSnapshot(number=1, merged=False)
    evidence = merge_verification.check_merged_into_main(state_fixture_repo["repo"], "integration", "main", pr)
    assert evidence.value is False


def test_merged_into_main_none_when_no_pr_snapshot_supplied_never_inferred_from_ancestry_alone(state_fixture_repo):
    """Requirement: never infer merge completion from a local merge
    commit/ancestry alone. With no PR snapshot at all, the field must be
    None, not True/False derived purely from git ancestry."""
    evidence = merge_verification.check_merged_into_main(state_fixture_repo["repo"], "integration", "main", None)
    assert evidence.value is None
    assert "not treated as proof" in evidence.source


def test_merged_into_main_none_when_pr_merged_field_itself_absent(state_fixture_repo):
    pr = PRSnapshot(number=1, merged=None)
    evidence = merge_verification.check_merged_into_main(state_fixture_repo["repo"], "integration", "main", pr)
    assert evidence.value is None
