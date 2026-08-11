"""Structural tests for reports.evidence_report.EvidenceReportV1.

Uses small synthetic fixtures (a fake EvidenceBundle.json written under
tmp_path, validated with an explicit repo_root override) -- no real
datasets, no network.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from reports.evidence_report import (
    EvidenceReportV1,
    ReportValidationError,
    compute_report_id,
)


def _write_fake_bundle_file(tmp_path):
    path = tmp_path / "EvidenceBundle.json"
    path.write_text(json.dumps({"bundle_id": "fake0000000000ab", "dataset_id": "ds_test"}), encoding="utf-8")
    return "EvidenceBundle.json"


def _base_report(tmp_path, **overrides):
    bundle_path = _write_fake_bundle_file(tmp_path)
    kwargs = dict(
        bundle_id="fake0000000000ab",
        dataset_id="ds_test",
        report_title="Test Report",
        requested_use="transition_export",
        source_artifacts={
            "bundle_path": bundle_path,
            "artifact_ids": ["art1"],
            "artifact_paths": {},
            "transition_record_paths": [],
            "phase_space_coordinate_paths": [],
            "phase_space_trajectory_paths": [],
        },
        registry_summary={"registry_path": "benchmarks/registry_seed.json", "decisions": []},
        contamination_summary={"updates": [], "n_updates": 0, "any_applied": False},
        transition_summary={"count": 0, "record_ids": []},
        phase_space_summary={"count": 0, "status_counts": {}, "confidence_counts": {}},
        null_control_summary={"status": "not_provided"},
        claim_scope_summary={"claim_scope_ceiling": "exploratory_metric", "generated_claim_scope": "exploratory_metric"},
        evidence_level_summary={"evidence_level_ceiling": "L4_cross_subject_dataset_specific", "generated_evidence_levels": []},
        validation_summary={"bundle_valid": True, "bundle_validation_errors": []},
        limitations=["synthetic test fixture only"],
        blocked_claims=["This report does not support a clinical claim."],
        reproducibility_commands=["python -m evidence.export_bundle --dataset ds_test"],
    )
    kwargs.update(overrides)
    return EvidenceReportV1.make(**kwargs)


# ── serialization / determinism ─────────────────────────────────────────────

def test_dict_roundtrip(tmp_path):
    report = _base_report(tmp_path)
    round_tripped = EvidenceReportV1.from_dict(report.to_dict())
    assert round_tripped.to_dict() == report.to_dict()


def test_json_roundtrip(tmp_path):
    report = _base_report(tmp_path)
    round_tripped = EvidenceReportV1.from_json(report.to_json())
    assert round_tripped.to_dict() == report.to_dict()


def test_report_id_deterministic():
    id1 = compute_report_id(bundle_id="b1")
    id2 = compute_report_id(bundle_id="b1")
    assert id1 == id2
    id3 = compute_report_id(bundle_id="b2")
    assert id1 != id3


def test_created_at_does_not_affect_report_id():
    r1 = EvidenceReportV1.make(
        bundle_id="b1", dataset_id="ds_test", limitations=["x"],
        _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    r2 = EvidenceReportV1.make(
        bundle_id="b1", dataset_id="ds_test", limitations=["x"],
        _now=datetime(2027, 6, 15, tzinfo=timezone.utc),
    )
    assert r1.report_id == r2.report_id
    assert r1.created_at != r2.created_at


def test_report_id_differs_by_report_type_or_template_version():
    default_id = compute_report_id(bundle_id="b1")
    other_type = compute_report_id(bundle_id="b1", report_type="other_report")
    other_template = compute_report_id(bundle_id="b1", template_version="2")
    assert default_id != other_type
    assert default_id != other_template


# ── validation ───────────────────────────────────────────────────────────────

def test_valid_report_passes(tmp_path):
    report = _base_report(tmp_path)
    assert report.validate(repo_root=tmp_path) == []


def test_validation_fails_on_empty_limitations(tmp_path):
    report = _base_report(tmp_path, limitations=[])
    errors = report.validate(repo_root=tmp_path)
    assert any("limitations" in e for e in errors)


def test_validation_fails_on_missing_blocked_claims(tmp_path):
    report = _base_report(tmp_path, blocked_claims=[])
    errors = report.validate(repo_root=tmp_path)
    assert any("blocked_claims" in e for e in errors)


def test_validation_fails_on_missing_bundle_path(tmp_path):
    report = _base_report(tmp_path)
    report.source_artifacts["bundle_path"] = "does_not_exist/EvidenceBundle.json"
    errors = report.validate(repo_root=tmp_path)
    assert any("bundle_path does not exist" in e for e in errors)


def test_validation_fails_on_missing_transition_record_path(tmp_path):
    report = _base_report(tmp_path)
    report.source_artifacts["transition_record_paths"] = ["transitions/missing/TransitionRecord.json"]
    errors = report.validate(repo_root=tmp_path)
    assert any("transition record path does not exist" in e for e in errors)


def test_validation_fails_on_missing_phase_space_coordinate_path(tmp_path):
    report = _base_report(tmp_path)
    report.source_artifacts["phase_space_coordinate_paths"] = ["phase_space/missing/PhaseSpaceCoordinates.json"]
    errors = report.validate(repo_root=tmp_path)
    assert any("phase-space coordinate path does not exist" in e for e in errors)


def test_validation_fails_without_bundle_path_at_all(tmp_path):
    report = _base_report(tmp_path)
    report.source_artifacts.pop("bundle_path")
    errors = report.validate(repo_root=tmp_path)
    assert any("bundle_path is required" in e for e in errors)


def test_validate_or_raise_raises(tmp_path):
    report = _base_report(tmp_path, limitations=[])
    with pytest.raises(ReportValidationError):
        report.validate_or_raise(repo_root=tmp_path)


def test_report_id_tamper_detected(tmp_path):
    report = _base_report(tmp_path)
    report.report_id = "0000000000000000"
    errors = report.validate(repo_root=tmp_path)
    assert any("does not match the deterministic ID" in e for e in errors)


def test_missing_reproducibility_commands_fails(tmp_path):
    report = _base_report(tmp_path, reproducibility_commands=[])
    errors = report.validate(repo_root=tmp_path)
    assert any("reproducibility_commands" in e for e in errors)


def test_missing_claim_scope_summary_fields_fails(tmp_path):
    report = _base_report(tmp_path, claim_scope_summary={})
    errors = report.validate(repo_root=tmp_path)
    assert any("claim_scope_summary" in e for e in errors)


def test_missing_evidence_level_summary_fields_fails(tmp_path):
    report = _base_report(tmp_path, evidence_level_summary={})
    errors = report.validate(repo_root=tmp_path)
    assert any("evidence_level_summary" in e for e in errors)


# ── governance: blocks forbidden language ───────────────────────────────────

def test_banned_phrase_in_limitations_fails(tmp_path):
    report = _base_report(tmp_path, limitations=["this proves consciousness beyond doubt"])
    errors = report.validate(repo_root=tmp_path)
    assert any("banned phrase detected" in e for e in errors)


def test_banned_phrase_in_blocked_claims_fails(tmp_path):
    report = _base_report(tmp_path, blocked_claims=["nirvana confirmed for this subject"])
    errors = report.validate(repo_root=tmp_path)
    assert any("banned phrase detected" in e for e in errors)


def test_banned_phrase_in_report_title_fails(tmp_path):
    report = _base_report(tmp_path, report_title="This proves consciousness in humans")
    errors = report.validate(repo_root=tmp_path)
    assert any("banned phrase detected" in e for e in errors)


def test_no_banned_overclaim_text_in_default_fixture(tmp_path):
    report = _base_report(tmp_path)
    assert report.validate(repo_root=tmp_path) == []
