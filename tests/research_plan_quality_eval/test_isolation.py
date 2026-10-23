from __future__ import annotations

import dataclasses

import pytest

from tools.research_plan_quality.checks import CHECKS_BY_DIMENSION
from tools.research_plan_quality.models import RUBRIC_DIMENSIONS
from tools.research_plan_quality_eval import isolation
from tools.research_plan_quality_eval.errors import HarnessError
from tools.research_plan_quality_eval.harness import DEFAULT_MANIFEST
from tools.research_plan_quality_eval.isolation import (
    configuration_fingerprint,
    harness_configuration,
    run_development_stage,
    run_held_out_stage,
)
from tools.research_plan_quality_eval.manifest import load_manifest
from tools.research_plan_quality_eval.splits import DEVELOPMENT, LOCKED_INTERNAL_VALIDATION


@pytest.fixture
def shipped_manifest():
    return load_manifest(DEFAULT_MANIFEST)


def _count(manifest, role):
    return sum(entry.split == role for entry in manifest.entries)


def test_development_outcomes_cover_only_development_plans(shipped_manifest):
    dev = run_development_stage(shipped_manifest)
    held_ids = {e.fixture_id for e in shipped_manifest.entries if e.split == LOCKED_INTERNAL_VALIDATION}
    assert dev.role == DEVELOPMENT
    assert len(dev.outcomes) == _count(shipped_manifest, DEVELOPMENT)
    assert {o["fixture_id"] for o in dev.outcomes}.isdisjoint(held_ids)


def test_held_out_stage_requires_a_frozen_development_stage(shipped_manifest):
    dev = run_development_stage(shipped_manifest)
    not_frozen = dataclasses.replace(dev, role=LOCKED_INTERNAL_VALIDATION)
    with pytest.raises(HarnessError, match="frozen development stage"):
        run_held_out_stage(shipped_manifest, not_frozen)


def test_held_out_stage_refuses_a_frozen_result_from_another_split_definition(shipped_manifest):
    dev = run_development_stage(shipped_manifest)
    other = dataclasses.replace(dev, split_definition_sha256="0" * 64)
    with pytest.raises(HarnessError, match="split definition"):
        run_held_out_stage(shipped_manifest, other)


def test_held_out_stage_refuses_outcomes_that_do_not_reproduce_from_the_plan_files(shipped_manifest):
    dev = run_development_stage(shipped_manifest)
    forged = dataclasses.replace(dev, outcomes=dev.outcomes[:-1])
    with pytest.raises(HarnessError, match="does not reproduce"):
        run_held_out_stage(shipped_manifest, forged)


def test_configuration_change_blocks_held_out_evaluation(shipped_manifest, monkeypatch):
    dev = run_development_stage(shipped_manifest)
    monkeypatch.setattr(isolation, "configuration_fingerprint", lambda: "tampered")
    with pytest.raises(HarnessError, match="configuration changed"):
        run_held_out_stage(shipped_manifest, dev)


def test_held_out_evaluation_leaves_rubric_configuration_and_frozen_result_unchanged(shipped_manifest):
    dev = run_development_stage(shipped_manifest)
    before = (harness_configuration(), configuration_fingerprint(), tuple(RUBRIC_DIMENSIONS), dict(CHECKS_BY_DIMENSION))

    held = run_held_out_stage(shipped_manifest, dev)

    assert held.role == LOCKED_INTERNAL_VALIDATION
    assert len(held.outcomes) == _count(shipped_manifest, LOCKED_INTERNAL_VALIDATION)
    assert (harness_configuration(), configuration_fingerprint(), tuple(RUBRIC_DIMENSIONS),
            dict(CHECKS_BY_DIMENSION)) == before
    assert run_development_stage(shipped_manifest) == dev


def test_development_stage_is_a_pure_function_of_the_pinned_manifest(shipped_manifest):
    assert run_development_stage(shipped_manifest) == run_development_stage(shipped_manifest)


def test_held_out_outcomes_do_not_feed_back_into_a_later_development_run(shipped_manifest):
    dev = run_development_stage(shipped_manifest)
    held = run_held_out_stage(shipped_manifest, dev)
    assert len(held.outcomes) == _count(shipped_manifest, LOCKED_INTERNAL_VALIDATION)
    assert run_development_stage(shipped_manifest) == dev


def test_the_harness_declares_no_fitted_or_tuned_parameters():
    config = harness_configuration()
    assert config["rubric_dimension_count"] == 20
    assert set(config) == {
        "rubric_dimension_count", "rubric_dimensions_sha256", "rubric_source_sha256",
        "near_duplicate_threshold", "shingle_size", "normalization_version",
        "min_plans_per_role", "min_groups_per_role",
    }
