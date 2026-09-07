from __future__ import annotations

from tools.integration_state import commit_classifier


def test_current_head_classification(state_fixture_repo):
    result = commit_classifier.classify_commit(
        state_fixture_repo["repo"], state_fixture_repo["round3"], state_fixture_repo["round3"],
    )
    assert result.classification == "current_head"
    assert result.resolved_commit == state_fixture_repo["round3"]


def test_ancestor_classification_for_intermediate_commit(state_fixture_repo):
    """round2 is a real, resolvable ancestor of round3 -- the
    "intermediate commit" scenario."""
    result = commit_classifier.classify_commit(
        state_fixture_repo["repo"], state_fixture_repo["round2"], state_fixture_repo["round3"],
    )
    assert result.classification == "ancestor"


def test_ancestor_classification_for_oldest_handoff(state_fixture_repo):
    """round1 (an even older handoff, analogous to the mission's stale
    3b36cb5) is also a genuine ancestor."""
    result = commit_classifier.classify_commit(
        state_fixture_repo["repo"], state_fixture_repo["round1"], state_fixture_repo["round3"],
    )
    assert result.classification == "ancestor"


def test_stale_classification_for_diverged_commit(state_fixture_repo):
    """A real, resolvable commit that is neither the head nor an
    ancestor -- it lives on a completely different line of history."""
    result = commit_classifier.classify_commit(
        state_fixture_repo["repo"], state_fixture_repo["diverged"], state_fixture_repo["round3"],
    )
    assert result.classification == "stale"


def test_unknown_classification_for_unresolvable_commit(state_fixture_repo):
    """A hash that shares a real commit's short prefix but does not
    itself exist -- exactly the real-world case this tool exists to
    catch (a handoff's own body text naming a commit that was never
    actually pushed)."""
    fabricated = state_fixture_repo["round3"][:8] + "f" * 32
    result = commit_classifier.classify_commit(state_fixture_repo["repo"], fabricated, state_fixture_repo["round3"])
    assert result.classification == "unknown"
    assert result.resolved_commit is None


def test_classify_all_labels_each_claim(state_fixture_repo):
    results = commit_classifier.classify_all(
        state_fixture_repo["repo"],
        {"round1": state_fixture_repo["round1"], "round3": state_fixture_repo["round3"]},
        state_fixture_repo["round3"],
    )
    by_label = {v.claim.label: v.classification for v in results}
    assert by_label == {"round1": "ancestor", "round3": "current_head"}


# ---------------------------------------------------------------------------
# Contradictory handoffs
# ---------------------------------------------------------------------------

def test_no_contradiction_for_a_normal_stale_to_current_progression(state_fixture_repo):
    results = commit_classifier.classify_all(
        state_fixture_repo["repo"],
        {"round1": state_fixture_repo["round1"], "round2": state_fixture_repo["round2"], "round3": state_fixture_repo["round3"]},
        state_fixture_repo["round3"],
    )
    contradictory, detail = commit_classifier.detect_contradictory_handoffs(results)
    assert contradictory is False
    assert detail is None


def test_contradiction_when_two_distinct_commits_both_claim_current_head(state_fixture_repo):
    results = [
        commit_classifier.classify_commit(state_fixture_repo["repo"], state_fixture_repo["round3"], state_fixture_repo["round3"]),
    ]
    # Force a second, different commit to ALSO classify as current_head by
    # comparing it against itself as its own "authoritative head" --
    # simulating two handoffs each insisting a different commit is THE head.
    fake_second_head = commit_classifier.classify_commit(
        state_fixture_repo["repo"], state_fixture_repo["diverged"], state_fixture_repo["diverged"]
    )
    contradictory, detail = commit_classifier.detect_contradictory_handoffs(results + [fake_second_head])
    assert contradictory is True
    assert "current head" in detail


def test_contradiction_when_a_handoff_resolves_to_a_diverged_commit(state_fixture_repo):
    results = commit_classifier.classify_all(
        state_fixture_repo["repo"],
        {"round3": state_fixture_repo["round3"], "rogue": state_fixture_repo["diverged"]},
        state_fixture_repo["round3"],
    )
    contradictory, detail = commit_classifier.detect_contradictory_handoffs(results)
    assert contradictory is True
    assert "rogue" in detail
