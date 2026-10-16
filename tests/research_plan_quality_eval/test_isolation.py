from __future__ import annotations

import dataclasses
import random

import pytest

from tools.research_plan_quality.checks import CHECKS_BY_DIMENSION
from tools.research_plan_quality.models import RUBRIC_DIMENSIONS
from tools.research_plan_quality_eval import isolation
from tools.research_plan_quality_eval.errors import HarnessError, HeldOutAccessError
from tools.research_plan_quality_eval.isolation import (
    configuration_fingerprint,
    harness_configuration,
    run_development_stage,
    run_held_out_stage,
)
from tools.research_plan_quality_eval.records import PlanRecord
from tools.research_plan_quality_eval.splits import DEVELOPMENT, LOCKED_INTERNAL_VALIDATION


def _split(records, role):
    return [r for r in records if r.split == role]


def test_development_stage_refuses_any_held_out_record(shipped_records):
    with pytest.raises(HeldOutAccessError, match="fx-v1-P06"):
        run_development_stage(list(shipped_records))


def test_held_out_stage_requires_a_frozen_development_stage(shipped_records):
    held = _split(shipped_records, LOCKED_INTERNAL_VALIDATION)
    dev = run_development_stage(_split(shipped_records, DEVELOPMENT))
    not_frozen = dataclasses.replace(dev, role=LOCKED_INTERNAL_VALIDATION)
    with pytest.raises(HarnessError, match="frozen development stage"):
        run_held_out_stage(held, not_frozen)


def test_held_out_stage_refuses_development_records(shipped_records):
    dev_records = _split(shipped_records, DEVELOPMENT)
    dev = run_development_stage(dev_records)
    with pytest.raises(ValueError, match="non-held-out"):
        run_held_out_stage(dev_records, dev)


def test_configuration_change_blocks_held_out_evaluation(shipped_records, monkeypatch):
    dev = run_development_stage(_split(shipped_records, DEVELOPMENT))
    monkeypatch.setattr(isolation, "configuration_fingerprint", lambda: "tampered")
    with pytest.raises(HarnessError, match="configuration changed"):
        run_held_out_stage(_split(shipped_records, LOCKED_INTERNAL_VALIDATION), dev)


def _mutate(plan, rng: random.Random):
    return dataclasses.replace(
        plan,
        research_question=f"perturbation {rng.random()} " + plan.research_question,
        sample_size=rng.randint(1, 200),
        claim_language=rng.choice(["This proves the effect.", "Exploratory association.", ""]),
    )


def test_held_out_perturbations_never_change_development_outputs(shipped_records):
    dev_records = _split(shipped_records, DEVELOPMENT)
    held_records = _split(shipped_records, LOCKED_INTERNAL_VALIDATION)
    baseline = run_development_stage(dev_records)
    rng = random.Random(20260916)
    held_outcomes_seen = set()
    for _ in range(25):
        perturbed = [
            PlanRecord(r.fixture_id, r.group_id, r.split, _mutate(r.plan, rng)) for r in held_records
        ]
        held_result = run_held_out_stage(perturbed, baseline)
        held_outcomes_seen.add(tuple(o["overall_status"] for o in held_result.outcomes))
        assert run_development_stage(dev_records) == baseline
    assert len(held_outcomes_seen) > 1, "perturbations should move held-out outcomes, or the test proves nothing"


def test_held_out_evaluation_leaves_rubric_configuration_and_frozen_result_unchanged(shipped_records):
    dev_records = _split(shipped_records, DEVELOPMENT)
    dev = run_development_stage(dev_records)
    before_config = harness_configuration()
    before_fingerprint = configuration_fingerprint()
    before_dimensions = tuple(RUBRIC_DIMENSIONS)
    before_checks = dict(CHECKS_BY_DIMENSION)

    run_held_out_stage(_split(shipped_records, LOCKED_INTERNAL_VALIDATION), dev)

    assert harness_configuration() == before_config
    assert configuration_fingerprint() == before_fingerprint
    assert tuple(RUBRIC_DIMENSIONS) == before_dimensions
    assert dict(CHECKS_BY_DIMENSION) == before_checks
    assert run_development_stage(dev_records) == dev


def test_development_stage_is_a_pure_function_of_its_inputs(shipped_records):
    dev_records = _split(shipped_records, DEVELOPMENT)
    assert run_development_stage(dev_records) == run_development_stage(list(reversed(dev_records)))


def test_held_out_outcomes_do_not_feed_back_into_a_later_development_run(shipped_records):
    dev_records = _split(shipped_records, DEVELOPMENT)
    held_records = _split(shipped_records, LOCKED_INTERNAL_VALIDATION)
    before = run_development_stage(dev_records)
    run_held_out_stage(held_records, before)
    after = run_development_stage(dev_records)
    assert before == after


def test_the_harness_declares_no_fitted_or_tuned_parameters():
    config = harness_configuration()
    assert config["rubric_dimension_count"] == 20
    assert set(config) == {
        "rubric_dimension_count", "rubric_dimensions_sha256", "rubric_source_sha256",
        "near_duplicate_threshold", "shingle_size", "normalization_version",
        "min_plans_per_role", "min_groups_per_role",
    }
