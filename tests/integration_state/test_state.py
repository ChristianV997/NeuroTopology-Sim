"""End-to-end build_state_lock_report() tests -- the required scenario
list: current head, stale head, intermediate commit, branch missing, PR
missing, integrated-only branch, merged into main, contradictory
handoffs, failed CI, unavailable logs, deterministic repeat."""
from __future__ import annotations

from tools.integration_state import state
from tools.integration_state.models import PRSnapshot


def test_current_head_scenario(state_fixture_repo):
    pr = PRSnapshot(number=236, state="open", draft=False, merged=False, head_sha=state_fixture_repo["round3"])
    report = state.build_state_lock_report(
        state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr,
        handoff_claims={"latest": state_fixture_repo["round3"]},
    )
    assert report.authoritative_head.value == state_fixture_repo["round3"]
    assert report.handoff_verifications[0].classification == "current_head"


def test_stale_head_scenario(state_fixture_repo):
    """An old handoff claim (round1) against the CURRENT authoritative
    head (round3) must classify as a stale-but-real ancestor, not an
    error and not silently accepted as current."""
    pr = PRSnapshot(number=236, head_sha=state_fixture_repo["round3"])
    report = state.build_state_lock_report(
        state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr,
        handoff_claims={"old_handoff": state_fixture_repo["round1"]},
    )
    assert report.handoff_verifications[0].classification == "ancestor"
    assert report.contradictory_handoffs is False


def test_intermediate_commit_scenario(state_fixture_repo):
    pr = PRSnapshot(number=236, head_sha=state_fixture_repo["round3"])
    report = state.build_state_lock_report(
        state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr,
        handoff_claims={"middle_handoff": state_fixture_repo["round2"]},
    )
    assert report.handoff_verifications[0].classification == "ancestor"
    assert report.handoff_verifications[0].resolved_commit == state_fixture_repo["round2"]


def test_branch_missing_scenario(state_fixture_repo):
    report = state.build_state_lock_report(
        state_fixture_repo["repo"], "origin/does-not-exist", "origin/main", pr_snapshot=None,
    )
    assert report.authoritative_head.value is None
    assert report.merge_base_head_and_main.value is None
    assert report.is_head_ancestor_of_main.value is None


def test_pr_missing_scenario(state_fixture_repo):
    """No PR snapshot at all -- the authoritative head falls back to the
    local branch ref, and every PR-only field is explicitly null."""
    report = state.build_state_lock_report(
        state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=None,
    )
    assert report.authoritative_head.value == state_fixture_repo["round3"]
    assert report.pr_number.value is None
    assert report.pr_state.value is None
    assert report.pr_lifecycle.value is None


def test_integrated_only_branch_scenario(state_fixture_repo):
    """PRs #100/#200 landed on the integration branch's own history but
    the branch is not merged into main -- exactly PR #236's real,
    self-described situation ('no merge to main is claimed')."""
    pr = PRSnapshot(
        number=236, state="open", draft=False, merged=False, head_sha=state_fixture_repo["round3"],
        integrated_pr_numbers=(100, 200),
    )
    report = state.build_state_lock_report(state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr)
    assert all(f["found_in_integration_branch_history"] for f in report.integrated_pr_history_findings)
    assert report.is_head_ancestor_of_main.value is False
    assert report.pr_merged.value is False


def test_merged_into_main_scenario(state_fixture_repo):
    pr = PRSnapshot(number=236, state="closed", draft=False, merged=True, head_sha=state_fixture_repo["round3"])
    report = state.build_state_lock_report(state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr)
    assert report.pr_merged.value is True
    assert report.pr_lifecycle.value == "merged"


def test_contradictory_handoffs_scenario(state_fixture_repo):
    pr = PRSnapshot(number=236, head_sha=state_fixture_repo["round3"])
    report = state.build_state_lock_report(
        state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr,
        handoff_claims={"current": state_fixture_repo["round3"], "rogue": state_fixture_repo["diverged"]},
    )
    assert report.contradictory_handoffs is True
    assert "rogue" in report.contradiction_detail


def test_pr_body_final_commit_claim_that_does_not_exist_is_unknown_and_contradictory(state_fixture_repo):
    """The real-world case this tool was built to catch: a PR body's own
    'Final commit: <hash>' text names something that was never pushed."""
    fabricated = state_fixture_repo["round3"][:8] + "0" * 32
    pr = PRSnapshot(number=236, head_sha=state_fixture_repo["round3"], body_final_commit_claim=fabricated)
    report = state.build_state_lock_report(state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr)
    unknowns = [v for v in report.handoff_verifications if v.classification == "unknown"]
    assert unknowns
    assert unknowns[0].claim.claimed_commit == fabricated


def test_failed_ci_scenario(state_fixture_repo):
    pr = PRSnapshot(
        number=236, head_sha=state_fixture_repo["round3"],
        checks={"core-tests": {"status": "completed", "conclusion": "failure"}},
    )
    report = state.build_state_lock_report(state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr)
    assert report.check_classifications["core-tests"] == "failing"


def test_unavailable_logs_scenario(state_fixture_repo):
    """A check with no status/conclusion data at all (e.g. logs never
    became available) is 'unavailable', never silently 'passing'."""
    pr = PRSnapshot(number=236, head_sha=state_fixture_repo["round3"], checks={"core-tests": {}})
    report = state.build_state_lock_report(state_fixture_repo["repo"], "origin/integration", "origin/main", pr_snapshot=pr)
    assert report.check_classifications["core-tests"] == "unavailable"


def test_deterministic_repeat(state_fixture_repo):
    pr = PRSnapshot(
        number=236, state="open", draft=False, merged=False, head_sha=state_fixture_repo["round3"],
        integrated_pr_numbers=(100, 200),
        checks={"core-tests": {"status": "completed", "conclusion": "failure"}},
    )
    handoff_claims = {"round1": state_fixture_repo["round1"], "round2": state_fixture_repo["round2"]}

    def _build():
        return state.build_state_lock_report(
            state_fixture_repo["repo"], "origin/integration", "origin/main",
            pr_snapshot=pr, handoff_claims=handoff_claims,
        )

    baseline = _build()
    for _ in range(15):
        repeat = _build()
        assert repeat.to_dict() == baseline.to_dict()
