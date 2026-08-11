"""DatasetAcquisitionPlanV1: dict/JSON roundtrip, deterministic plan_id,
and structural validation rules. Synthetic fixtures only.
"""
from __future__ import annotations

from dataset_acquisition.acquisition_plan import DatasetAcquisitionPlanV1, compute_plan_id
from dataset_acquisition.validation import DatasetAcquisitionValidationError


def _minimal_valid_plan(**overrides) -> DatasetAcquisitionPlanV1:
    kwargs = dict(
        candidate_id="cand-1",
        requested_action="metadata_only",
        acquisition_mode="fixture_only",
        target_root="outputs/datasets/cand-1",
        disk_limit_bytes=None,
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        risks=["example risk"],
        limitations=["example limitation"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetAcquisitionPlanV1.make(**kwargs)


def test_dict_roundtrip():
    plan = _minimal_valid_plan()
    d = plan.to_dict()
    plan2 = DatasetAcquisitionPlanV1.from_dict(d)
    assert plan2.to_dict() == d


def test_json_roundtrip():
    plan = _minimal_valid_plan()
    text = plan.to_json()
    plan2 = DatasetAcquisitionPlanV1.from_json(text)
    assert plan2.to_dict() == plan.to_dict()


def test_write_json_roundtrip(tmp_path):
    plan = _minimal_valid_plan()
    path = plan.write_json(tmp_path / "plan.json")
    plan2 = DatasetAcquisitionPlanV1.from_json(path.read_text(encoding="utf-8"))
    assert plan2.plan_id == plan.plan_id


def test_plan_id_deterministic():
    plan_a = _minimal_valid_plan()
    plan_b = _minimal_valid_plan(license="MIT")  # non-identity field differs
    assert plan_a.plan_id == plan_b.plan_id
    assert plan_a.plan_id == compute_plan_id(
        candidate_id="cand-1",
        requested_action="metadata_only",
        acquisition_mode="fixture_only",
        target_root="outputs/datasets/cand-1",
        disk_limit_bytes=None,
    )


def test_plan_id_differs_across_identity_fields():
    base = _minimal_valid_plan()
    other_action = _minimal_valid_plan(requested_action="plan_download")
    other_root = _minimal_valid_plan(target_root="outputs/datasets/other")
    assert base.plan_id != other_action.plan_id
    assert base.plan_id != other_root.plan_id


def test_created_at_excluded_from_plan_id():
    """Rule 2: created_at must not affect deterministic IDs."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=365)
    plan_now = _minimal_valid_plan(_now=now)
    plan_later = _minimal_valid_plan(_now=later)
    assert plan_now.created_at != plan_later.created_at
    assert plan_now.plan_id == plan_later.plan_id


def test_valid_plan_has_no_errors():
    plan = _minimal_valid_plan()
    assert plan.validate() == []


def test_validation_fails_on_empty_risks():
    plan = _minimal_valid_plan(risks=[])
    errors = plan.validate()
    assert any("risks" in e for e in errors)


def test_validation_fails_on_empty_limitations():
    plan = _minimal_valid_plan(limitations=[])
    errors = plan.validate()
    assert any("limitations" in e for e in errors)


def test_validation_fails_on_missing_provenance():
    plan = _minimal_valid_plan(provenance="")
    errors = plan.validate()
    assert any("provenance" in e for e in errors)


def test_validate_or_raise_raises_on_invalid_plan():
    plan = _minimal_valid_plan(provenance="")
    try:
        plan.validate_or_raise()
        assert False, "expected DatasetAcquisitionValidationError"
    except DatasetAcquisitionValidationError:
        pass


def test_execute_download_blocked_by_default():
    """execute_download with no safety flags must carry blocked_reasons and
    dry_run stays True -- a plan constructed this way must still validate
    cleanly (it documents *why* it's blocked, matching rule 9's 'unblocked
    plan' framing) rather than raising."""
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        dry_run=True,
        blocked_reasons=["allow_network=False blocks execute_download", "allow_raw_data=False blocks execute_download"],
    )
    assert plan.validate() == []
    assert plan.dry_run is True


def test_unblocked_execute_download_requires_flags():
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        estimated_size_bytes=1000,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        blocked_reasons=[],
        metadata={"explicit_execute_confirmed": True},
    )
    assert plan.validate() == []


def test_unknown_license_blocks_execute_download():
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        estimated_size_bytes=1000,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        license_risk="unknown_high",
        blocked_reasons=[],  # claims unblocked despite disqualifying license -- must fail
        metadata={"explicit_execute_confirmed": True},
    )
    errors = plan.validate()
    assert any("rule 10" in e for e in errors)


def test_restricted_access_blocks_execute_download():
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        estimated_size_bytes=1000,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        access_status="restricted",
        blocked_reasons=[],
        metadata={"explicit_execute_confirmed": True},
    )
    errors = plan.validate()
    assert any("rule 10" in e for e in errors)


def test_over_disk_limit_blocks_execute_download():
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=100,
        estimated_size_bytes=100_000,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        blocked_reasons=[],
        metadata={"explicit_execute_confirmed": True},
    )
    errors = plan.validate()
    assert any("rule 11" in e for e in errors)


def test_unknown_size_blocks_execute_download_unless_override():
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        estimated_size_bytes=None,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        blocked_reasons=[],
        metadata={"explicit_execute_confirmed": True},
    )
    errors = plan.validate()
    assert any("rule 12" in e for e in errors)

    plan_override = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="local_bids_scan",
        disk_limit_bytes=500_000_000,
        estimated_size_bytes=None,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        blocked_reasons=[],
        metadata={"explicit_execute_confirmed": True, "force_unknown_size": True},
    )
    assert plan_override.validate() == []


def test_dry_run_false_only_allowed_for_execute_download():
    plan = _minimal_valid_plan(requested_action="metadata_only", dry_run=False)
    errors = plan.validate()
    assert any("rule 6" in e for e in errors)


def test_target_root_outside_allowed_directories_fails():
    plan = _minimal_valid_plan(target_root="/etc/passwd")
    errors = plan.validate()
    assert any("target_root" in e for e in errors)

    plan2 = _minimal_valid_plan(target_root="adapters/evil")
    errors2 = plan2.validate()
    assert any("target_root" in e for e in errors2)


def test_target_root_traversal_fails():
    plan = _minimal_valid_plan(target_root="outputs/../secrets")
    errors = plan.validate()
    assert any("target_root" in e for e in errors)


def test_metadata_cannot_claim_evidence():
    plan = _minimal_valid_plan(metadata={"evidence": True})
    errors = plan.validate()
    assert any("rule 15" in e for e in errors)


def test_banned_phrase_in_free_text_fails():
    plan = _minimal_valid_plan(provenance="this acquisition proves consciousness beyond doubt")
    errors = plan.validate()
    assert any("banned phrase" in e for e in errors)


def test_unimplemented_remote_mode_blocks_clean_execute_download():
    plan = _minimal_valid_plan(
        requested_action="execute_download",
        acquisition_mode="eegdash_metadata_query",
        disk_limit_bytes=500_000_000,
        estimated_size_bytes=1000,
        dry_run=False,
        allow_network=True,
        allow_raw_data=True,
        blocked_reasons=[],
        metadata={"explicit_execute_confirmed": True},
    )
    errors = plan.validate()
    assert any("no implemented remote-fetch execution path" in e for e in errors)
