"""Structural tests for evidence.bundle.EvidenceBundleV1.

Uses small synthetic fixtures (fake TransitionRecord.json /
PhaseSpaceCoordinates.json files written under tmp_path, validated with an
explicit repo_root override) -- no real datasets, no network.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from evidence.bundle import BundleValidationError, EvidenceBundleV1, compute_bundle_id


def _write_transition_record(tmp_path, transition_id: str, *, claim_scope="exploratory_metric", evidence_level="L2_single_subject_real_signal"):
    d = tmp_path / "transitions" / transition_id
    d.mkdir(parents=True)
    payload = {
        "schema_version": "1", "transition_id": transition_id, "dataset_id": "ds_test",
        "claim_scope": claim_scope, "evidence_level": evidence_level,
        "null_control_summary": {"status": "not_provided"},
    }
    (d / "TransitionRecord.json").write_text(json.dumps(payload), encoding="utf-8")
    return f"transitions/{transition_id}/TransitionRecord.json"


def _write_phase_space_coordinates(tmp_path, transition_id: str, coordinate_ids: list[str]):
    d = tmp_path / "phase_space" / transition_id
    d.mkdir(parents=True)
    payload = {
        "schema": "NeuroTopologySim.PhaseSpaceCoordinates.v1",
        "transition_id": transition_id,
        "coordinates": [{"coordinate_id": cid, "transition_id": transition_id} for cid in coordinate_ids],
    }
    (d / "PhaseSpaceCoordinates.json").write_text(json.dumps(payload), encoding="utf-8")
    return f"phase_space/{transition_id}/PhaseSpaceCoordinates.json"


def _base_bundle(tmp_path, **overrides):
    tid = "tx0000000000abcd"
    tx_path = _write_transition_record(tmp_path, tid)
    kwargs = dict(
        dataset_id="ds_test",
        artifact_ids=["art0000000001"],
        requested_use="transition_export",
        transition_record_ids=[tid],
        transition_record_paths=[tx_path],
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L4_cross_subject_dataset_specific",
        generated_claim_scope="exploratory_metric",
        generated_evidence_levels=["L2_single_subject_real_signal"],
        limitations=["synthetic test fixture only"],
        null_control_summary={"status": "not_provided", "per_transition": {tid: "not_provided"}},
        validation_summary={"transition_records_valid": True},
    )
    kwargs.update(overrides)
    return EvidenceBundleV1.make(**kwargs)


# ── serialization / determinism ─────────────────────────────────────────────

def test_serialization_roundtrip(tmp_path):
    bundle = _base_bundle(tmp_path)
    round_tripped = EvidenceBundleV1.from_dict(bundle.to_dict())
    assert round_tripped.to_dict() == bundle.to_dict()


def test_json_roundtrip(tmp_path):
    bundle = _base_bundle(tmp_path)
    round_tripped = EvidenceBundleV1.from_json(bundle.to_json())
    assert round_tripped.to_dict() == bundle.to_dict()


def test_bundle_id_deterministic_ignoring_created_at():
    id1 = compute_bundle_id(
        dataset_id="ds005620", artifact_ids=["a1"], requested_use="transition_export",
        transition_record_ids=["t1", "t2"], phase_space_coordinate_ids=["c1"],
    )
    id2 = compute_bundle_id(
        dataset_id="ds005620", artifact_ids=["a1"], requested_use="transition_export",
        transition_record_ids=["t1", "t2"], phase_space_coordinate_ids=["c1"],
    )
    assert id1 == id2

    b1 = EvidenceBundleV1.make(
        dataset_id="ds005620", artifact_ids=["a1"], requested_use="transition_export",
        transition_record_ids=["t1", "t2"], phase_space_coordinate_ids=["c1"],
        limitations=["x"], _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    b2 = EvidenceBundleV1.make(
        dataset_id="ds005620", artifact_ids=["a1"], requested_use="transition_export",
        transition_record_ids=["t1", "t2"], phase_space_coordinate_ids=["c1"],
        limitations=["x"], _now=datetime(2027, 6, 15, tzinfo=timezone.utc),
    )
    assert b1.bundle_id == b2.bundle_id
    assert b1.created_at != b2.created_at


def test_bundle_id_order_insensitive_for_id_lists():
    id1 = compute_bundle_id(
        dataset_id="ds005620", artifact_ids=["a1", "a2"], requested_use="transition_export",
        transition_record_ids=["t1", "t2"], phase_space_coordinate_ids=[],
    )
    id2 = compute_bundle_id(
        dataset_id="ds005620", artifact_ids=["a2", "a1"], requested_use="transition_export",
        transition_record_ids=["t2", "t1"], phase_space_coordinate_ids=[],
    )
    assert id1 == id2


def test_bundle_id_changes_when_identity_field_changes():
    base = dict(
        dataset_id="ds005620", artifact_ids=["a1"], requested_use="transition_export",
        transition_record_ids=["t1"], phase_space_coordinate_ids=[],
    )
    id_base = compute_bundle_id(**base)
    id_diff_use = compute_bundle_id(**{**base, "requested_use": "phase_space_export"})
    assert id_base != id_diff_use


# ── validation: category 1 required cases ───────────────────────────────────

def test_valid_bundle_passes(tmp_path):
    bundle = _base_bundle(tmp_path)
    assert bundle.validate(repo_root=tmp_path) == []


def test_validation_fails_on_missing_limitations(tmp_path):
    bundle = _base_bundle(tmp_path, limitations=[])
    errors = bundle.validate(repo_root=tmp_path)
    assert any("limitations" in e for e in errors)


def test_validation_fails_on_missing_transition_record_path(tmp_path):
    bundle = _base_bundle(tmp_path)
    bundle.transition_record_paths = ["transitions/does_not_exist/TransitionRecord.json"]
    errors = bundle.validate(repo_root=tmp_path)
    assert any("does not exist" in e for e in errors)


def test_validation_fails_on_missing_phase_space_coordinate_path(tmp_path):
    bundle = _base_bundle(tmp_path)
    bundle.phase_space_coordinate_ids = ["coord_missing"]
    bundle.phase_space_coordinate_paths = ["phase_space/does_not_exist/PhaseSpaceCoordinates.json"]
    errors = bundle.validate(repo_root=tmp_path)
    assert any("does not exist" in e for e in errors)


def test_validation_fails_if_generated_claim_scope_exceeds_ceiling(tmp_path):
    bundle = _base_bundle(
        tmp_path, claim_scope_ceiling="computational_artifact", generated_claim_scope="exploratory_metric",
    )
    errors = bundle.validate(repo_root=tmp_path)
    assert any("exceeds claim_scope_ceiling" in e for e in errors)


def test_validation_fails_if_generated_evidence_level_exceeds_ceiling(tmp_path):
    bundle = _base_bundle(
        tmp_path, evidence_level_ceiling="L0_computational_artifact",
        generated_evidence_levels=["L2_single_subject_real_signal"],
    )
    errors = bundle.validate(repo_root=tmp_path)
    assert any("exceeds evidence_level_ceiling" in e for e in errors)


def test_validate_or_raise_raises_bundle_validation_error(tmp_path):
    bundle = _base_bundle(tmp_path, limitations=[])
    with pytest.raises(BundleValidationError):
        bundle.validate_or_raise(repo_root=tmp_path)


def test_transition_id_mismatch_fails(tmp_path):
    tid = "tx0000000000abcd"
    tx_path = _write_transition_record(tmp_path, tid)
    bundle = EvidenceBundleV1.make(
        dataset_id="ds_test", requested_use="transition_export",
        transition_record_ids=["a_different_id"], transition_record_paths=[tx_path],
        limitations=["test"],
    )
    errors = bundle.validate(repo_root=tmp_path)
    assert any("but" in e and "contains transition_id" in e for e in errors)


def test_mismatched_parallel_list_lengths_fails(tmp_path):
    tid = "tx0000000000abcd"
    tx_path = _write_transition_record(tmp_path, tid)
    bundle = EvidenceBundleV1.make(
        dataset_id="ds_test", requested_use="transition_export",
        transition_record_ids=[tid, "another_id"], transition_record_paths=[tx_path],
        limitations=["test"],
    )
    errors = bundle.validate(repo_root=tmp_path)
    assert any("parallel lists of equal length" in e for e in errors)


def test_coordinate_id_membership_check(tmp_path):
    tid = "tx0000000000abcd"
    coord_path = _write_phase_space_coordinates(tmp_path, tid, ["c1", "c2"])
    bundle = EvidenceBundleV1.make(
        dataset_id="ds_test", requested_use="transition_export",
        phase_space_coordinate_ids=["c1", "c2"], limitations=["test"],
    )
    bundle.phase_space_coordinate_paths = [coord_path]
    assert bundle.validate(repo_root=tmp_path) == []

    bundle.phase_space_coordinate_ids = ["c1", "c_not_present"]
    errors = bundle.validate(repo_root=tmp_path)
    assert any("c_not_present" in e for e in errors)


def test_bundle_id_tamper_detected(tmp_path):
    bundle = _base_bundle(tmp_path)
    bundle.bundle_id = "0000000000000000"
    errors = bundle.validate(repo_root=tmp_path)
    assert any("does not match the deterministic ID" in e for e in errors)


# ── governance ───────────────────────────────────────────────────────────────

def test_always_blocked_requested_use_fails(tmp_path):
    bundle = _base_bundle(tmp_path, requested_use="clinical_claim")
    errors = bundle.validate(repo_root=tmp_path)
    assert any("always blocked" in e for e in errors)


def test_unknown_requested_use_fails(tmp_path):
    bundle = _base_bundle(tmp_path, requested_use="not_a_real_use")
    errors = bundle.validate(repo_root=tmp_path)
    assert any("not a recognized use" in e for e in errors)


def test_denied_registry_decision_fails_validation(tmp_path):
    bundle = _base_bundle(tmp_path, registry_path="benchmarks/registry_seed.json")
    bundle.registry_decisions = [{"id": "ds_test", "kind": "dataset", "requested_use": "transition_export", "allowed": False, "reason": "denied"}]
    errors = bundle.validate(repo_root=tmp_path)
    assert any("denied decision" in e for e in errors)


def test_registry_path_without_decisions_fails(tmp_path):
    bundle = _base_bundle(tmp_path, registry_path="benchmarks/registry_seed.json")
    bundle.registry_decisions = []
    errors = bundle.validate(repo_root=tmp_path)
    assert any("registry_decisions is empty" in e for e in errors)


def test_null_control_passed_without_evidence_fails(tmp_path):
    tid = "tx0000000000abcd"
    bundle = _base_bundle(
        tmp_path,
        null_control_summary={"status": "passed", "per_transition": {tid: "not_provided"}},
    )
    errors = bundle.validate(repo_root=tmp_path)
    assert any("no per_transition entry reports 'passed'" in e for e in errors)


def test_null_control_all_not_provided_must_report_not_provided(tmp_path):
    tid = "tx0000000000abcd"
    bundle = _base_bundle(
        tmp_path,
        null_control_summary={"status": "failed", "per_transition": {tid: "not_provided"}},
    )
    errors = bundle.validate(repo_root=tmp_path)
    assert any("every per_transition null-control entry is 'not_provided'" in e for e in errors)


def test_phase_space_requested_but_empty_fails(tmp_path):
    bundle = _base_bundle(tmp_path, metadata={"include_phase_space": True, "phase_space_status": "estimated"})
    errors = bundle.validate(repo_root=tmp_path)
    assert any("phase_space_coordinate_ids is empty" in e for e in errors)


def test_no_banned_overclaim_text_in_limitations(tmp_path):
    bundle = _base_bundle(tmp_path)
    assert bundle.validate(repo_root=tmp_path) == []


def test_banned_phrase_in_limitations_fails(tmp_path):
    bundle = _base_bundle(tmp_path, limitations=["this proves consciousness beyond doubt"])
    errors = bundle.validate(repo_root=tmp_path)
    assert any("banned phrase detected" in e for e in errors)
