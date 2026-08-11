"""Use-policy and holdout-lock tests for benchmarks.split_policy / holdout_lock.

Uses the real committed benchmarks/registry_seed.json for the seeded
dataset/artifact scenarios (ds005620, ds000245), and small synthetic
in-memory records for the generic contamination/lock mechanics.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.artifact_registry import ArtifactRecordV1
from benchmarks.dataset_registry import DatasetRecordV1
from benchmarks.export_registry import BenchmarkRegistry
from benchmarks.holdout_lock import (
    HoldoutLockError,
    consume_validation_lock,
    lock_for_validation,
)
from benchmarks.split_policy import (
    PolicyError,
    assert_allowed_use,
    can_use_dataset,
    mark_seen,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED = _REPO_ROOT / "benchmarks" / "registry_seed.json"


@pytest.fixture()
def registry():
    return BenchmarkRegistry.load(_SEED)


def _dev_dataset(**overrides):
    kwargs = dict(
        dataset_id="ds_dev",
        display_name="dev dataset",
        modalities=["EEG"],
        current_role="development",
        allowed_uses=["transition_export", "phase_space_export"],
        forbidden_uses=["final_claim_confirmation", "cross_dataset_replication_claim"],
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L0_computational_artifact",
        provenance="synthetic fixture",
        limitations=["test only"],
    )
    kwargs.update(overrides)
    return DatasetRecordV1.make(**kwargs)


def _locked_dataset(**overrides):
    kwargs = dict(
        dataset_id="ds_locked",
        display_name="locked validation dataset",
        modalities=["EEG"],
        current_role="locked_internal_validation",
        allowed_uses=["internal_validation", "final_claim_confirmation"],
        forbidden_uses=[],
        contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric",
        evidence_level_ceiling="L0_computational_artifact",
        provenance="synthetic fixture",
        limitations=["test only"],
    )
    kwargs.update(overrides)
    return DatasetRecordV1.make(**kwargs)


# ── 3. Use policy ────────────────────────────────────────────────────────────

def test_ds005620_development_artifact_allows_transition_export(registry):
    allowed, reason = registry.check_use("ds005620", "transition_export")
    assert allowed, reason


def test_ds005620_development_artifact_blocks_final_claim_confirmation(registry):
    allowed, reason = registry.check_use("ds005620", "final_claim_confirmation")
    assert not allowed
    assert "forbidden_uses" in reason


def test_ds000245_development_artifact_allows_phase_space_export(registry):
    allowed, reason = registry.check_use("ds000245", "phase_space_export")
    assert allowed, reason


def test_ds005917_candidate_blocks_transition_export(registry):
    allowed, reason = registry.check_use("ds005917", "transition_export")
    assert not allowed


def test_ds005917_candidate_allows_documentation(registry):
    allowed, reason = registry.check_use("ds005917", "documentation")
    assert allowed, reason


def test_seen_by_llm_blocks_independent_validation():
    record = _locked_dataset(current_role="development", contamination_status="seen_by_llm")
    allowed, reason = can_use_dataset(record, "internal_validation", claim_family="fam")
    assert not allowed
    assert "rule 2" in reason


def test_seen_by_theory_generation_blocks_independent_validation():
    record = _locked_dataset(current_role="development", contamination_status="seen_by_theory_generation")
    allowed, reason = can_use_dataset(record, "external_validation", claim_family="fam")
    assert not allowed
    assert "rule 2" in reason


def test_retired_blocks_all_non_documentation_use():
    record = _dev_dataset(current_role="retired", allowed_uses=["transition_export"], forbidden_uses=[])
    for use in ("transition_export", "phase_space_export", "feature_design", "visualization"):
        allowed, reason = can_use_dataset(record, use)
        assert not allowed, use
        assert "rule 5" in reason
    allowed, reason = can_use_dataset(record, "documentation")
    assert allowed, reason


def test_deprecated_blocks_all_non_documentation_use():
    record = _dev_dataset(current_role="deprecated", allowed_uses=["visualization"], forbidden_uses=[])
    allowed, reason = can_use_dataset(record, "visualization")
    assert not allowed
    allowed, reason = can_use_dataset(record, "documentation")
    assert allowed


def test_unknown_requested_use_fails_closed():
    record = _dev_dataset()
    allowed, reason = can_use_dataset(record, "some_made_up_use_that_does_not_exist")
    assert not allowed
    assert "rule 7" in reason


def test_always_blocked_use_rejected_even_if_in_allowed_uses_list():
    # Defense in depth: even a misconfigured record that lists a blocked use
    # in allowed_uses must still be rejected (rule 6 short-circuits first).
    record = _dev_dataset()
    record.allowed_uses = list(record.allowed_uses) + ["clinical_claim"]
    allowed, reason = can_use_dataset(record, "clinical_claim")
    assert not allowed
    assert "rule 6" in reason


def test_exploration_development_role_cannot_confirm_a_claim():
    record = _dev_dataset(allowed_uses=["transition_export", "final_claim_confirmation"], forbidden_uses=[])
    allowed, reason = can_use_dataset(record, "final_claim_confirmation")
    assert not allowed
    assert "rule 1" in reason


def test_assert_allowed_use_raises_policy_error_on_denial():
    record = _dev_dataset()
    with pytest.raises(PolicyError):
        assert_allowed_use(record, "final_claim_confirmation")


def test_assert_allowed_use_passes_silently_when_allowed():
    record = _dev_dataset()
    assert_allowed_use(record, "transition_export")  # should not raise


def test_mark_seen_updates_contamination_status_and_seen_by():
    record = _dev_dataset()
    mark_seen(record, seen_by="llm", note="tested via a fixture")
    assert record.contamination_status == "seen_by_llm"
    assert any("llm" in s for s in record.seen_by)


def test_mark_seen_rejects_unknown_kind():
    record = _dev_dataset()
    with pytest.raises(PolicyError):
        mark_seen(record, seen_by="not_a_real_kind")


def test_mark_seen_refuses_to_mutate_terminal_state():
    record = _dev_dataset(contamination_status="validation_consumed")
    with pytest.raises(PolicyError):
        mark_seen(record, seen_by="exploration")


# ── 4. Holdout locks ─────────────────────────────────────────────────────────

def test_lock_for_validation_requires_reason_and_claim_family():
    record = _locked_dataset()
    with pytest.raises(HoldoutLockError):
        lock_for_validation(record, locked_by="operator", reason="", claim_family="fam_x")
    with pytest.raises(HoldoutLockError):
        lock_for_validation(record, locked_by="operator", reason="valid reason", claim_family="")


def test_lock_for_validation_requires_locked_role():
    record = _dev_dataset()  # role is "development", not a locked_* role
    with pytest.raises(HoldoutLockError):
        lock_for_validation(record, locked_by="operator", reason="valid reason", claim_family="fam_x")


def test_locked_validation_allows_only_matching_validation_use():
    record = _locked_dataset()
    lock_for_validation(record, locked_by="operator", reason="preregistered replication", claim_family="fam_x")
    allowed, _ = can_use_dataset(record, "internal_validation", claim_family="fam_x")
    assert allowed
    allowed, reason = can_use_dataset(record, "internal_validation", claim_family="fam_other")
    assert not allowed
    assert "does not match" in reason
    allowed, reason = can_use_dataset(record, "external_validation", claim_family="fam_x")
    assert not allowed
    assert "requires role 'locked_external_validation'" in reason


def test_validation_consumption_marks_record_consumed():
    record = _locked_dataset()
    lock_for_validation(record, locked_by="operator", reason="preregistered replication", claim_family="fam_x")
    consume_validation_lock(record, claim_family="fam_x", consumed_by="exporter_run_1")
    assert record.validation_lock["consumed"] is True
    assert record.contamination_status == "validation_consumed"


def test_consumed_validation_cannot_be_reused_as_fresh_validation():
    record = _locked_dataset()
    lock_for_validation(record, locked_by="operator", reason="preregistered replication", claim_family="fam_x")
    consume_validation_lock(record, claim_family="fam_x", consumed_by="exporter_run_1")
    with pytest.raises(HoldoutLockError):
        consume_validation_lock(record, claim_family="fam_x", consumed_by="exporter_run_2")
    allowed, reason = can_use_dataset(record, "internal_validation", claim_family="fam_x")
    assert not allowed
    assert "already been consumed" in reason


def test_cannot_issue_new_lock_over_unconsumed_lock():
    record = _locked_dataset()
    lock_for_validation(record, locked_by="operator", reason="first lock", claim_family="fam_x")
    with pytest.raises(HoldoutLockError):
        lock_for_validation(record, locked_by="operator", reason="second lock", claim_family="fam_y")


def test_prospective_role_requires_protocol_id():
    record = _dev_dataset(
        current_role="prospective", allowed_uses=["prospective_prediction"], forbidden_uses=[],
        prospective_protocol_id=None,
    )
    allowed, reason = can_use_dataset(record, "prospective_prediction")
    assert not allowed
    assert "rule 4" in reason

    record.prospective_protocol_id = "PROTO-2026-001"
    allowed, reason = can_use_dataset(record, "prospective_prediction")
    assert allowed, reason
