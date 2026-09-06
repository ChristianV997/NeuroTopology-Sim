from __future__ import annotations

from tools.integration_reconciliation import stacking


def test_unstacked_when_base_is_target():
    relationships = stacking.build_stack_relationships(
        {"a": "feature-a"}, {"a": "main"}, target_branch="main",
    )
    assert relationships["a"].is_stacked is False
    assert relationships["a"].base_work_order_id is None


def test_stacked_when_base_is_another_work_orders_branch():
    relationships = stacking.build_stack_relationships(
        {"base": "feature-a", "dependent": "stacked-on-feature-a"},
        {"base": "main", "dependent": "feature-a"},
        target_branch="main",
    )
    assert relationships["dependent"].is_stacked is True
    assert relationships["dependent"].base_work_order_id == "base"
    assert relationships["base"].is_stacked is False


def test_dependents_are_populated_on_the_base_work_order():
    relationships = stacking.build_stack_relationships(
        {"base": "feature-a", "dependent": "stacked-on-feature-a"},
        {"base": "main", "dependent": "feature-a"},
        target_branch="main",
    )
    assert relationships["base"].dependents == ("dependent",)
    assert relationships["dependent"].dependents == ()


def test_unknown_base_branch_is_still_flagged_stacked_but_no_matching_work_order():
    relationships = stacking.build_stack_relationships(
        {"a": "feature-a"}, {"a": "some-untracked-branch"}, target_branch="main",
    )
    assert relationships["a"].is_stacked is True
    assert relationships["a"].base_work_order_id is None


def test_none_base_ref_is_treated_as_unstacked():
    relationships = stacking.build_stack_relationships(
        {"a": "feature-a"}, {"a": None}, target_branch="main",
    )
    assert relationships["a"].is_stacked is False


def test_origin_prefixed_base_ref_is_normalized():
    relationships = stacking.build_stack_relationships(
        {"a": "feature-a"}, {"a": "origin/main"}, target_branch="origin/main",
    )
    assert relationships["a"].is_stacked is False


# ---- effective diff against a real git fixture ----

def test_effective_diff_for_unstacked_work_order_is_full_diff_against_target(git_fixture_repo):
    relationships = stacking.build_stack_relationships(
        {"a": "feature-a"}, {"a": "main"}, target_branch="main",
    )
    files = stacking.effective_changed_files(git_fixture_repo, relationships["a"], "origin/main")
    assert files == ("shared/a.py",)


def test_effective_diff_for_stacked_work_order_excludes_the_base_prs_files(git_fixture_repo):
    """The whole point of stacked-PR awareness: stacked-on-feature-a's
    OWN diff must be just stacked_only.py, not shared/a.py too (which
    belongs to its base, feature-a) -- proving no double-counting."""
    relationships = stacking.build_stack_relationships(
        {"base": "feature-a", "dependent": "stacked-on-feature-a"},
        {"base": "main", "dependent": "feature-a"},
        target_branch="main",
    )
    files = stacking.effective_changed_files(git_fixture_repo, relationships["dependent"], "origin/main")
    assert files == ("stacked_only.py",)


def test_naive_diff_against_main_would_have_double_counted(git_fixture_repo):
    """Sanity check proving the double-counting problem is real: a plain
    diff of the stacked branch against main DOES include shared/a.py,
    which is why effective_changed_files must diff against the immediate
    base instead."""
    from tools.integration_reconciliation import git_source

    naive = git_source.changed_files(git_fixture_repo, "origin/main", "origin/stacked-on-feature-a")
    assert "shared/a.py" in naive
    assert "stacked_only.py" in naive
