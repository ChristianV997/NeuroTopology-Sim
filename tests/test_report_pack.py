"""ReportPackV1: dict roundtrip, deterministic ID, and structural
validation. Synthetic fixtures only.
"""
from __future__ import annotations

from workflows.report_pack import ReportPackV1, ReportPackValidationError, compute_report_pack_id


def _minimal_pack(**overrides) -> ReportPackV1:
    kwargs = dict(
        dataset_id="demo_ds", input_mode="mne_bids_derived_features",
        evidence_bundle_ids=["bundle-1"], evidence_report_ids=["report-1"],
        modality="EEG", pipeline_run_id="pipeline-1",
        limitations=["test"],
    )
    kwargs.update(overrides)
    return ReportPackV1.make(**kwargs)


def test_pack_dict_roundtrip():
    pack = _minimal_pack()
    d = pack.to_dict()
    pack2 = ReportPackV1.from_dict(d)
    assert pack2.to_dict() == d


def test_pack_json_roundtrip():
    pack = _minimal_pack()
    text = pack.to_json()
    pack2 = ReportPackV1.from_json(text)
    assert pack2.to_dict() == pack.to_dict()


def test_pack_write_json_roundtrip(tmp_path):
    pack = _minimal_pack()
    path = pack.write_json(tmp_path / "ReportPack.json")
    pack2 = ReportPackV1.from_json(path.read_text(encoding="utf-8"))
    assert pack2.report_pack_id == pack.report_pack_id


def test_report_pack_id_deterministic():
    pack_a = _minimal_pack()
    pack_b = _minimal_pack(summary={"note": "a totally different summary"})
    assert pack_a.report_pack_id == pack_b.report_pack_id
    assert pack_a.report_pack_id == compute_report_pack_id(
        dataset_id="demo_ds", input_mode="mne_bids_derived_features",
        evidence_bundle_ids=["bundle-1"], evidence_report_ids=["report-1"],
    )


def test_report_pack_id_differs_across_identity_fields():
    base = _minimal_pack()
    other_bundle = _minimal_pack(evidence_bundle_ids=["bundle-2"])
    other_mode = _minimal_pack(input_mode="fmri_derived_features")
    assert base.report_pack_id != other_bundle.report_pack_id
    assert base.report_pack_id != other_mode.report_pack_id


def test_created_at_excluded_from_report_pack_id():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=365)
    pack_now = _minimal_pack(_now=now)
    pack_later = _minimal_pack(_now=later)
    assert pack_now.created_at != pack_later.created_at
    assert pack_now.report_pack_id == pack_later.report_pack_id


def test_pack_includes_evidence_bundle_and_report_ids():
    pack = _minimal_pack()
    assert pack.evidence_bundle_ids == ["bundle-1"]
    assert pack.evidence_report_ids == ["report-1"]


def test_pack_includes_artifact_manifest():
    pack = _minimal_pack(artifact_manifest={"transition_record_paths": ["outputs/x/t1/TransitionRecord.json"]})
    assert "transition_record_paths" in pack.artifact_manifest


def test_pack_default_blocked_interpretations_non_empty():
    pack = _minimal_pack()
    assert pack.blocked_interpretations
    assert any("clinical" in b.lower() for b in pack.blocked_interpretations)


def test_validate_or_raise_raises():
    pack = _minimal_pack(limitations=[])
    try:
        pack.validate_or_raise()
        assert False, "expected ReportPackValidationError"
    except ReportPackValidationError:
        pass


def test_validation_requires_limitations():
    pack = _minimal_pack(limitations=[])
    assert any("limitations" in e for e in pack.validate())


def test_validation_requires_blocked_interpretations():
    pack = _minimal_pack(blocked_interpretations=[])
    assert any("blocked_interpretations" in e for e in pack.validate())


def test_report_pack_id_mismatch_is_a_validation_error():
    pack = _minimal_pack()
    pack.report_pack_id = "not-the-real-id"
    errors = pack.validate()
    assert any("does not match deterministic id" in e for e in errors)


def test_pack_never_carries_claim_scope_or_evidence_level_field():
    pack = _minimal_pack()
    assert not hasattr(pack, "claim_scope")
    assert not hasattr(pack, "evidence_level")


def test_pack_does_not_promote_claims_banned_phrase_scan():
    pack = _minimal_pack(summary={"note": "this confirms diagnosis beyond doubt"})
    assert any("banned phrase" in e for e in pack.validate())


def test_valid_pack_has_no_errors():
    assert _minimal_pack().validate() == []
