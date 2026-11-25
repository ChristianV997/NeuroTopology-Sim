"""Smallest safe integration: plan → RunRecord → domain artifact → transition → report."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from shared.phenomenology_perturbation import (
    RUN_ARTIFACT_KEY,
    SCHEMA,
    PhenomenologyValidationError,
    run_integration_path,
    validate_record_dict,
    write_bundle_with_byte_check,
)
from shared.phenomenology_perturbation.run_link import TRANSITION_ARTIFACT_KEY
from transitions.record import TransitionRecordV1


EXAMPLE = Path(
    "shared/phenomenology_perturbation/examples/synthetic_selective_release_trial.json"
)


def _load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_synthetic_example_marked_and_claim_limited():
    d = _load_example()
    assert d["data_status"] == "synthetic"
    assert d["evidence_status"] == "exploratory_synthetic"
    out = validate_record_dict(d)
    assert out["claim_limits"]["eeg_feature_equals_consciousness_or_attainment"] is False
    assert out["claim_limits"]["digest_equals_authenticity_or_scientific_validity"] is False
    assert out["privacy"]["schema_is_complete_privacy_pipeline"] is False
    assert out["privacy"]["consent_status"] == "synthetic_no_human_subjects"
    # No contemplative-effect language in portable report text.
    assert "jhana" not in out["delayed_report"]["report_text"].casefold()
    assert "liberation" not in out["delayed_report"]["report_text"].casefold()


def test_integration_path_plan_run_domain_transition():
    d = _load_example()
    report = run_integration_path(d, include_transition=True)
    assert report["ok"] is True
    assert report["plan"]["is_synthetic"] is True
    assert report["plan"]["schema_version"] == "ExperimentPlan.v1"
    assert report["run_record"]["run_id"] == d["parent_run_id"]
    assert report["run_record"]["artifacts"][RUN_ARTIFACT_KEY]
    assert report["run_record"]["metrics"]["contemplative_effect_established"] is False
    assert report["domain_record"]["schema"] == SCHEMA
    assert report["transition_record"] is not None
    assert report["transition_validation_errors"] == []
    assert (
        report["transition_record"]["artifact_paths"][TRANSITION_ARTIFACT_KEY]
        == report["links"]["transition_artifact_path"]
    )
    # Transition identity recomputes cleanly via from_dict.
    tr = TransitionRecordV1.from_dict(report["transition_record"])
    assert tr.validate() == []
    assert tr.recompute_id() == tr.transition_id
    # Digest layers remain distinct.
    assert report["integrity_layers"]["byte_verified"] is False
    assert report["integrity_layers"]["authenticity_established"] is False
    assert report["integrity_layers"]["scientific_validity_established"] is False
    assert report["c5_lineage"]["status"] == "unavailable_on_this_host"
    assert report["c5_lineage"]["recreated_from_chat"] is False


def test_null_confidence_not_coerced_to_zero():
    d = _load_example()
    d["delayed_report"]["confidence"] = None
    out = validate_record_dict(d)
    assert out["delayed_report"]["confidence"] is None
    assert out["delayed_report"]["confidence"] is not 0
    report = run_integration_path(d, include_transition=False)
    assert report["domain_record"]["delayed_report"]["confidence"] is None
    assert report["null_preservation"]["delayed_report_confidence_stayed_null"] is True


def test_null_sync_offset_not_coerced_to_zero():
    d = _load_example()
    d["signal_quality"]["sync_offset_ms"] = None
    out = validate_record_dict(d)
    assert out["signal_quality"]["sync_offset_ms"] is None


def test_missing_rt_stays_absent_not_zero():
    d = _load_example()
    del d["behavior"]["rt_s"]
    out = validate_record_dict(d)
    assert "rt_s" not in out["behavior"]


def test_unavailable_privacy_redaction_stays_null():
    d = _load_example()
    d["privacy"]["redaction_complete"] = None
    out = validate_record_dict(d)
    assert out["privacy"]["redaction_complete"] is None
    assert out["privacy"]["schema_is_complete_privacy_pipeline"] is False


def test_amplitude_zero_is_valid_and_distinct_from_missing():
    d = _load_example()
    d["perturbation"]["amplitude"] = 0.0
    out = validate_record_dict(d)
    assert out["perturbation"]["amplitude"] == 0.0
    d2 = _load_example()
    del d2["perturbation"]["amplitude"]
    with pytest.raises(PhenomenologyValidationError, match="amplitude"):
        validate_record_dict(d2)


def test_write_bundle_byte_verification(tmp_path):
    d = _load_example()
    report = write_bundle_with_byte_check(d, tmp_path, eeg_bytes=b"synthetic-eeg-stub-bytes")
    assert report["ok"] is True
    assert report["integrity_layers"]["byte_verified"] is True
    assert report["integrity_layers"]["authenticity_established"] is False
    assert report["integrity_layers"]["reproducibility_established"] is False
    eeg = Path(report["bundle_paths"]["eeg"])
    assert eeg.is_file()
    assert eeg.read_bytes() == b"synthetic-eeg-stub-bytes"
    # Parent link still recorded equality only.
    assert report["links"]["parent_run_id_matches"] is True


def test_separations_present_on_normalized_record():
    out = validate_record_dict(_load_example())
    assert out["practice"]["practice_control_skill"]["not_practice_dose"] is True
    assert out["practice"]["slow_transition_params"]["is_attainment_claim"] is False
    assert out["delayed_report"]["not_latent_state"] is True
    assert out["physiology_neural"]["not_participant_report"] is True
    assert out["physiology_neural"]["not_latent_state"] is True
    assert out["latent_profile"]["label"] == "model_inferred"
    assert out["latent_profile"]["directly_observed"] is False


def test_unsafe_path_rejected_in_integration_payload():
    d = copy.deepcopy(_load_example())
    d["artifact_paths"]["eeg_path"] = "../escape.npy"
    with pytest.raises(PhenomenologyValidationError, match="unsafe relative path"):
        run_integration_path(d)
