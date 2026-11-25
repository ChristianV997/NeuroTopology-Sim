from __future__ import annotations

import pytest

from tools.research_plan_quality_eval.errors import ManifestError, InsufficientEvaluationSetError
from tools.research_plan_quality_eval.records import PlanRecord
from tools.research_plan_quality_eval.splits import (
    DEVELOPMENT,
    LOCKED_INTERNAL_VALIDATION,
    MIN_GROUPS_PER_ROLE,
    MIN_PLANS_PER_ROLE,
    SPLIT_ROLES,
    assign_group_splits,
    check_group_integrity,
    require_sufficient,
    split_summary,
)

GROUPS = [f"src-{chr(ord('A') + i)}/project/topic" for i in range(10)]


def test_split_roles_reuse_the_benchmark_vocabulary():
    from benchmarks.split_policy import DATASET_ROLES

    assert DEVELOPMENT in DATASET_ROLES
    assert LOCKED_INTERNAL_VALIDATION in DATASET_ROLES
    assert set(SPLIT_ROLES) == {DEVELOPMENT, LOCKED_INTERNAL_VALIDATION}


def test_assignment_is_deterministic_for_the_same_inputs():
    first = assign_group_splits(GROUPS, held_out_fraction=0.4, salt="v1")
    second = assign_group_splits(list(reversed(GROUPS)), held_out_fraction=0.4, salt="v1")
    assert first == second


def test_every_group_gets_exactly_one_role_and_both_roles_are_populated():
    assignment = assign_group_splits(GROUPS, held_out_fraction=0.4, salt="v1")
    assert set(assignment) == set(GROUPS)
    assert set(assignment.values()) == set(SPLIT_ROLES)
    assert sum(v == LOCKED_INTERNAL_VALIDATION for v in assignment.values()) == 4


def test_held_out_fraction_is_clamped_to_keep_both_roles_nonempty():
    tiny = assign_group_splits(GROUPS[:4], held_out_fraction=0.01, salt="v1")
    large = assign_group_splits(GROUPS[:4], held_out_fraction=0.99, salt="v1")
    for assignment in (tiny, large):
        counts = {role: list(assignment.values()).count(role) for role in SPLIT_ROLES}
        assert min(counts.values()) >= MIN_GROUPS_PER_ROLE


def test_salt_changes_the_assignment():
    assignments = {
        tuple(sorted(assign_group_splits(GROUPS, held_out_fraction=0.4, salt=s).items()))
        for s in ("a", "b", "c", "d", "e")
    }
    assert len(assignments) > 1


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, 1.5])
def test_out_of_range_fraction_is_rejected(fraction):
    with pytest.raises(ValueError):
        assign_group_splits(GROUPS, held_out_fraction=fraction, salt="v1")


def test_too_few_groups_to_form_both_roles_is_insufficient():
    with pytest.raises(InsufficientEvaluationSetError):
        assign_group_splits(GROUPS[:2], held_out_fraction=0.5, salt="v1")


def test_group_integrity_rejects_a_group_under_two_roles():
    with pytest.raises(ManifestError, match="assigned to both"):
        check_group_integrity([("g1", DEVELOPMENT), ("g1", LOCKED_INTERNAL_VALIDATION)])


def test_group_integrity_accepts_repeated_identical_assignments():
    check_group_integrity([("g1", DEVELOPMENT), ("g1", DEVELOPMENT), ("g2", LOCKED_INTERNAL_VALIDATION)])


def _record(fixture_id: str, group: str, split: str, plan_from) -> PlanRecord:
    return PlanRecord(fixture_id=fixture_id, group_id=group, split=split, plan=plan_from(plan_id=fixture_id))


def test_empty_evaluation_set_is_insufficient():
    with pytest.raises(InsufficientEvaluationSetError, match="empty"):
        require_sufficient([])


def test_missing_held_out_role_is_insufficient(shipped_records):
    dev_only = tuple(r for r in shipped_records if r.split == DEVELOPMENT)
    with pytest.raises(InsufficientEvaluationSetError, match=LOCKED_INTERNAL_VALIDATION):
        require_sufficient(dev_only)


def test_too_few_plans_in_a_role_is_insufficient(plan_from):
    records = [
        _record("d1", "g1", DEVELOPMENT, plan_from),
        _record("d2", "g2", DEVELOPMENT, plan_from),
        _record("h1", "g3", LOCKED_INTERNAL_VALIDATION, plan_from),
        _record("h2", "g4", LOCKED_INTERNAL_VALIDATION, plan_from),
        _record("h3", "g5", LOCKED_INTERNAL_VALIDATION, plan_from),
    ]
    with pytest.raises(InsufficientEvaluationSetError):
        require_sufficient(records)
    assert MIN_PLANS_PER_ROLE == 3


def test_too_few_groups_in_a_role_is_insufficient(plan_from):
    records = [
        _record("d1", "g1", DEVELOPMENT, plan_from),
        _record("d2", "g1", DEVELOPMENT, plan_from),
        _record("d3", "g1", DEVELOPMENT, plan_from),
        _record("h1", "g2", LOCKED_INTERNAL_VALIDATION, plan_from),
        _record("h2", "g3", LOCKED_INTERNAL_VALIDATION, plan_from),
        _record("h3", "g4", LOCKED_INTERNAL_VALIDATION, plan_from),
    ]
    with pytest.raises(InsufficientEvaluationSetError, match="groups"):
        require_sufficient(records)


def test_shipped_fixture_set_is_sufficient_and_keeps_groups_whole(shipped_records):
    require_sufficient(shipped_records)
    pairs = {(r.group_id, r.split) for r in shipped_records}
    assert len({group for group, _ in pairs}) == len(pairs)


def test_split_summary_lists_fixture_ids_and_groups_per_role(shipped_records):
    summary = split_summary(shipped_records)
    assert summary["roles"][DEVELOPMENT]["plan_count"] == 5
    assert summary["roles"][LOCKED_INTERNAL_VALIDATION]["plan_count"] == 5
    assert "fx-v1-P07" in summary["roles"][LOCKED_INTERNAL_VALIDATION]["fixture_ids"]
    assert summary == split_summary(list(reversed(shipped_records)))


def test_group_integrity_rejects_spelling_variants_of_one_group():
    with pytest.raises(ManifestError, match="assigned to both"):
        check_group_integrity([("Proj-A", DEVELOPMENT), ("proj-a", LOCKED_INTERNAL_VALIDATION)])


@pytest.mark.parametrize("variant", ["g1 ", " g1", "G1", "ｇ" + "1"])
def test_group_integrity_compares_normalised_group_ids(variant):
    with pytest.raises(ManifestError, match="assigned to both"):
        check_group_integrity([("g1", DEVELOPMENT), (variant, LOCKED_INTERNAL_VALIDATION)])
