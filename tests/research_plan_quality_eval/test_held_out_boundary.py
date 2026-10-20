"""Held-out integrity: the development/held-out stage boundary and the pinned split definition.

Reproduced on PR #383 before the fix, and each was accepted: relabelled held-out records passed the
development stage, a forged frozen stage released held-out evaluation, the public loader returned
held-out records to any caller, and a reassigned or re-hashed held-out plan changed the evaluation
set with no check against a pinned definition. Labels stay single-author expectations.
"""
from __future__ import annotations

import json

import pytest

from tools.research_plan_quality_eval.errors import HarnessError, ManifestError
from tools.research_plan_quality_eval.harness import DEFAULT_MANIFEST, build_report
from tools.research_plan_quality_eval.isolation import StageResult, configuration_fingerprint, run_held_out_stage
from tools.research_plan_quality_eval.manifest import load_manifest, load_plan_records, split_definition_sha256
from tools.research_plan_quality_eval.splits import DEVELOPMENT, LOCKED_INTERNAL_VALIDATION

from .conftest import rehash_plan


def _held_ids(manifest_path):
    return [e.fixture_id for e in load_manifest(manifest_path).entries if e.split == LOCKED_INTERNAL_VALIDATION]


def test_forged_frozen_stage_cannot_release_held_out_evaluation():
    manifest = load_manifest(DEFAULT_MANIFEST)
    forged = StageResult(role=DEVELOPMENT, config_fingerprint=configuration_fingerprint(),
                         split_definition_sha256=split_definition_sha256(manifest.entries), outcomes=())
    with pytest.raises(HarnessError, match="does not reproduce"):
        run_held_out_stage(manifest, forged)


def test_public_loader_returns_only_the_requested_role():
    manifest = load_manifest(DEFAULT_MANIFEST)
    development = load_plan_records(manifest, roles={DEVELOPMENT})
    held = load_plan_records(manifest, roles={LOCKED_INTERNAL_VALIDATION})
    assert development and all(r.split == DEVELOPMENT for r in development)
    assert held and all(r.split == LOCKED_INTERNAL_VALIDATION for r in held)
    assert not {r.fixture_id for r in development} & {r.fixture_id for r in held}


def test_shipped_split_definition_matches_its_pin():
    report = build_report()
    assert report["fixture_set"]["split_definition_pinned"] is True


def test_reassigned_group_in_a_copied_manifest_is_refused(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    held_group = next(e["group_id"] for e in data["records"] if e["split"] == LOCKED_INTERNAL_VALIDATION)
    for entry in data["records"]:
        if entry["group_id"] == held_group:
            entry["split"] = DEVELOPMENT
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(ManifestError, match="split definition"):
        build_report(manifest_path)


def test_held_out_plan_edited_and_rehashed_is_refused_unless_declared_unpinned(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    fixture_id = _held_ids(manifest_path)[0]
    plan_path = next(e.plan_path for e in load_manifest(manifest_path).entries if e.fixture_id == fixture_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["research_question"] += " (edited after results)"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    rehash_plan(manifest_path, fixture_id)

    with pytest.raises(ManifestError, match="split definition"):
        build_report(manifest_path)

    declared = build_report(manifest_path, allow_unpinned=True)
    assert declared["fixture_set"]["split_definition_pinned"] is False


def test_cli_refuses_a_reassigned_split_with_exit_2_unless_declared(copy_fixture_tree, capsys):
    from tools.research_plan_quality_eval.__main__ import main

    manifest_path = copy_fixture_tree()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    held_group = next(e["group_id"] for e in data["records"] if e["split"] == LOCKED_INTERNAL_VALIDATION)
    for entry in data["records"]:
        if entry["group_id"] == held_group:
            entry["split"] = DEVELOPMENT
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    assert main(["--manifest", str(manifest_path), "--no-label-consistency"]) == 2
    assert "pinned digest" in capsys.readouterr().err
