"""Positive and negative tests for PhenomenologyPerturbationRecord."""

from __future__ import annotations

import hashlib
import math

import pytest

from shared.phenomenology_perturbation import (
    RUN_ARTIFACT_KEY,
    SCHEMA,
    PhenomenologyPerturbationRecord,
    PhenomenologyValidationError,
    assert_parent_run_id_matches,
    dumps_record,
    loads_record,
    merge_run_artifact_pointer,
    provenance_layer_map,
    validate_record_dict,
)


def _valid_base(**overrides):
    base = {
        "schema": SCHEMA,
        "record_id": "ppr-demo-001",
        "parent_run_id": "0123456789abcdef",
        "data_status": "empirical_measured",
        "causal_claim_type": "randomized_intervention_intent",
        "evidence_status": "recorded_observation",
        "practice": {
            "instruction_id": "instr-breath-01",
            "instruction_text": "Attend to breath sensations.",
            "practice_dose": {"duration_s": 600.0, "session_count": 1},
            "practice_control_skill": {
                "label": "self_reported_stability",
                "self_report_level": 0.4,
                "notes": "Skill label only; distinct from practice dose.",
            },
            "slow_transition_params": {
                "parameters": {"theta_w_proxy": 0.1},
            },
        },
        "perturbation": {
            "event_id": "pert-001",
            "randomized": True,
            "onset_s": 120.0,
            "offset_s": 120.5,
            "modality": "sensory_probe",
            "target": "auditory_probe_left",
            "amplitude": 0.3,
            "units": "normalized_intensity",
            "observation_origin": "measured",
            "parameters": {"carrier_hz": 1000.0},
        },
        "behavior": {
            "missing": False,
            "response": {"key": "j"},
            "missingness_reason": None,
            "observation_origin": "measured",
            "rt_s": 0.42,
        },
        "delayed_report": {
            "prompt_exact": "What was present during the beep window?",
            "target_interval_start_s": 120.0,
            "target_interval_end_s": 120.5,
            "response_time_s": 150.5,
            "report_delay_s": 30.0,
            "confidence": 0.7,
            "report_text": "Brief clarity then dullness.",
            "language": "en",
            "observation_origin": "measured",
        },
        "signal_quality": {
            "eeg_ok": True,
            "sync_ok": True,
            "time_reference": "session_t0",
            "sync_offset_ms": 2.0,
            "sync_uncertainty_ms": 1.0,
            "sample_rate_hz": 256.0,
            "units": {"eeg": "uV", "time": "s"},
            "notes": "",
        },
        "physiology_neural": {
            "observation_origin": "measured",
            "reference": "Cz",
            "features": {
                "alpha_band_power_proxy": {"value": 1.2, "units": "a.u."},
            },
        },
        "latent_profile": {
            "label": "model_inferred",
            "directly_observed": False,
            "variables": {"x_hat": {"point": 0.2, "uncertainty": 0.15}},
            "model_provenance": {
                "model_id": "toy-state-estimator-v0",
                "code_path": "shared/phenomenology_perturbation/record.py",
            },
            "notes": "Inferred profile with uncertainty; latent not directly observed.",
        },
        "artifact_paths": {
            "eeg_path": "artifacts/demo/eeg.npy",
            "parent_run_record_path": "artifacts/demo/RunRecord.json",
        },
    }
    base.update(overrides)
    return base


def test_valid_round_trip_deterministic():
    rec = PhenomenologyPerturbationRecord.from_dict(_valid_base())
    text = dumps_record(rec)
    again = loads_record(text)
    assert dumps_record(again) == text
    assert again.parent_run_id == "0123456789abcdef"
    assert again.data["delayed_report"]["not_latent_state"] is True
    assert again.data["practice"]["practice_control_skill"]["not_practice_dose"] is True
    assert again.data["practice"]["slow_transition_params"]["is_attainment_claim"] is False
    assert again.data["latent_profile"]["label"] == "model_inferred"
    assert again.data["physiology_neural"]["is_consciousness_or_attainment_label"] is False
    assert again.data["claim_limits"]["eeg_feature_equals_consciousness_or_attainment"] is False
    assert again.data["evidence_status"] == "recorded_observation"


def test_malformed_timing_offset_before_onset():
    d = _valid_base()
    d["perturbation"]["offset_s"] = 10.0
    with pytest.raises(PhenomenologyValidationError, match="offset_s"):
        validate_record_dict(d)


def test_malformed_timing_delay_mismatch():
    d = _valid_base()
    d["delayed_report"]["report_delay_s"] = 1.0
    with pytest.raises(PhenomenologyValidationError, match="report_delay_s"):
        validate_record_dict(d)


def test_malformed_timing_interval_inverted():
    d = _valid_base()
    d["delayed_report"]["target_interval_start_s"] = 200.0
    d["delayed_report"]["target_interval_end_s"] = 100.0
    d["delayed_report"]["response_time_s"] = 250.0
    d["delayed_report"]["report_delay_s"] = 150.0
    with pytest.raises(PhenomenologyValidationError, match="target_interval"):
        validate_record_dict(d)


def test_non_finite_values_rejected():
    d = _valid_base()
    d["perturbation"]["amplitude"] = math.nan
    with pytest.raises(PhenomenologyValidationError, match="non-finite|finite"):
        validate_record_dict(d)


def test_non_finite_in_loads_path():
    with pytest.raises(PhenomenologyValidationError):
        loads_record('{"schema": "x", "a": NaN}')


def test_inconsistent_missingness_response_present():
    d = _valid_base()
    d["behavior"]["missing"] = True
    d["behavior"]["response"] = {"key": "j"}
    d["behavior"]["missingness_reason"] = "timeout"
    with pytest.raises(PhenomenologyValidationError, match="inconsistent missingness"):
        validate_record_dict(d)


def test_inconsistent_missingness_null_response():
    d = _valid_base()
    d["behavior"]["missing"] = False
    d["behavior"]["response"] = None
    with pytest.raises(PhenomenologyValidationError, match="inconsistent missingness"):
        validate_record_dict(d)


def test_missing_requires_reason():
    d = _valid_base()
    d["behavior"]["missing"] = True
    d["behavior"]["response"] = None
    d["behavior"]["missingness_reason"] = ""
    with pytest.raises(PhenomenologyValidationError, match="missingness_reason"):
        validate_record_dict(d)


def test_invalid_source_status_vocab():
    d = _valid_base()
    d["data_status"] = "real_world_truth"
    with pytest.raises(PhenomenologyValidationError, match="data_status"):
        validate_record_dict(d)


def test_synthetic_mislabeled_as_measured():
    d = _valid_base()
    d["data_status"] = "empirical_measured"
    d["behavior"]["observation_origin"] = "synthetic"
    with pytest.raises(PhenomenologyValidationError, match="mislabeled as measured"):
        validate_record_dict(d)


def test_measured_under_synthetic_status_rejected():
    d = _valid_base()
    d["data_status"] = "synthetic"
    with pytest.raises(PhenomenologyValidationError, match="invalid source status"):
        validate_record_dict(d)


def test_mixed_declared_allows_mix():
    d = _valid_base()
    d["data_status"] = "mixed_declared"
    d["evidence_status"] = "exploratory_synthetic"
    d["behavior"]["observation_origin"] = "synthetic"
    validate_record_dict(d)


def test_latent_must_be_model_inferred():
    d = _valid_base()
    d["latent_profile"]["label"] = "observed"
    with pytest.raises(PhenomenologyValidationError, match="model_inferred"):
        validate_record_dict(d)


def test_latent_directly_observed_forbidden():
    d = _valid_base()
    d["latent_profile"]["directly_observed"] = True
    with pytest.raises(PhenomenologyValidationError, match="directly_observed"):
        validate_record_dict(d)


def test_prohibited_classifier_language():
    d = _valid_base()
    d["delayed_report"]["report_text"] = "Subject reached second jhana."
    with pytest.raises(PhenomenologyValidationError, match="prohibited"):
        validate_record_dict(d)


def test_prohibited_key():
    d = _valid_base()
    d["jhana_level"] = 2
    with pytest.raises(PhenomenologyValidationError, match="prohibited key"):
        validate_record_dict(d)


def test_unsafe_artifact_path():
    d = _valid_base()
    d["artifact_paths"]["eeg_path"] = "../secret.npy"
    with pytest.raises(PhenomenologyValidationError, match="unsafe relative path"):
        validate_record_dict(d)


def test_bool_not_accepted_as_number_for_onset():
    d = _valid_base()
    d["perturbation"]["onset_s"] = True
    with pytest.raises(PhenomenologyValidationError, match="finite number"):
        validate_record_dict(d)


def test_schema_mismatch():
    d = _valid_base()
    d["schema"] = "other"
    with pytest.raises(PhenomenologyValidationError, match="schema"):
        validate_record_dict(d)


def test_invalid_enum_causal_claim():
    d = _valid_base()
    d["causal_claim_type"] = "proves_causation"
    with pytest.raises(PhenomenologyValidationError, match="causal_claim_type"):
        validate_record_dict(d)


def test_invalid_enum_modality():
    d = _valid_base()
    d["perturbation"]["modality"] = "magic"
    with pytest.raises(PhenomenologyValidationError, match="modality"):
        validate_record_dict(d)


def test_privacy_rejects_identifier_key():
    d = _valid_base()
    d["email"] = "someone@example.com"
    with pytest.raises(PhenomenologyValidationError, match="direct-identifier|privacy"):
        validate_record_dict(d)


def test_privacy_rejects_email_in_report_text():
    d = _valid_base()
    d["delayed_report"]["report_text"] = "Contact me at someone@example.com later."
    with pytest.raises(PhenomenologyValidationError, match="email-like|privacy"):
        validate_record_dict(d)


def test_privacy_rejects_overlong_report_text():
    from shared.phenomenology_perturbation.schema import MAX_REPORT_TEXT_CHARS

    d = _valid_base()
    d["delayed_report"]["report_text"] = "x" * (MAX_REPORT_TEXT_CHARS + 1)
    with pytest.raises(PhenomenologyValidationError, match="portable max"):
        validate_record_dict(d)


def test_latent_requires_model_provenance():
    d = _valid_base()
    del d["latent_profile"]["model_provenance"]
    with pytest.raises(PhenomenologyValidationError, match="model_provenance"):
        validate_record_dict(d)


def test_integrity_record_only_accepts_digest():
    d = _valid_base()
    d["integrity"] = {
        "mode": "record_only",
        "path_sha256": {
            "eeg_path": "a" * 64,
        },
    }
    out = validate_record_dict(d)
    assert out["integrity"]["verified"] is False
    assert "authenticity" in out["integrity"]["disclaimer"]
    assert out["claim_limits"]["digest_equals_authenticity_or_scientific_validity"] is False


def test_integrity_verify_paths_mismatch(tmp_path):
    payload = b"eeg-bytes"
    rel = "artifacts/demo/eeg.npy"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    d = _valid_base()
    d["artifact_paths"] = {"eeg_path": rel}
    d["integrity"] = {
        "mode": "verify_paths",
        "path_sha256": {"eeg_path": "b" * 64},
    }
    with pytest.raises(PhenomenologyValidationError, match="sha256 mismatch"):
        validate_record_dict(d, verify_root=tmp_path)


def test_integrity_verify_paths_ok(tmp_path):
    payload = b"eeg-bytes"
    rel = "artifacts/demo/eeg.npy"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    d = _valid_base()
    d["artifact_paths"] = {"eeg_path": rel}
    d["integrity"] = {
        "mode": "verify_paths",
        "path_sha256": {"eeg_path": digest},
    }
    out = validate_record_dict(d, verify_root=tmp_path)
    assert out["integrity"]["verified"] is True
    # Byte match ≠ authenticity / authorship / scientific validity.
    assert "authenticity" in out["integrity"]["disclaimer"]
    assert out["claim_limits"]["digest_equals_authenticity_or_scientific_validity"] is False


def test_integrity_verify_requires_root():
    d = _valid_base()
    d["integrity"] = {
        "mode": "verify_paths",
        "path_sha256": {"eeg_path": "a" * 64},
    }
    with pytest.raises(PhenomenologyValidationError, match="verify_root"):
        validate_record_dict(d)


def test_invalid_hash_format():
    d = _valid_base()
    d["integrity"] = {
        "mode": "record_only",
        "path_sha256": {"eeg_path": "not-a-hash"},
    }
    with pytest.raises(PhenomenologyValidationError, match="64 hex"):
        validate_record_dict(d)


def test_perturbation_requires_target_amplitude_units():
    d = _valid_base()
    del d["perturbation"]["target"]
    with pytest.raises(PhenomenologyValidationError, match="target"):
        validate_record_dict(d)


def test_invalid_evidence_status():
    d = _valid_base()
    d["evidence_status"] = "proven_contemplative_effect"
    with pytest.raises(PhenomenologyValidationError, match="evidence_status"):
        validate_record_dict(d)


def test_physiology_cannot_claim_consciousness_label():
    d = _valid_base()
    d["physiology_neural"]["is_consciousness_or_attainment_label"] = True
    with pytest.raises(PhenomenologyValidationError, match="consciousness_or_attainment"):
        validate_record_dict(d)


def test_run_link_parent_match_and_pointer():
    d = validate_record_dict(_valid_base())
    run = {
        "schema_version": "0.1",
        "run_id": "0123456789abcdef",
        "run_kind": "hypothesis",
        "artifacts": {},
    }
    assert_parent_run_id_matches(d, run)
    merged = merge_run_artifact_pointer(run["artifacts"], "artifacts/demo/ppr.json")
    assert RUN_ARTIFACT_KEY in merged
    assert merged[RUN_ARTIFACT_KEY] == "artifacts/demo/ppr.json"


def test_run_link_parent_mismatch():
    d = validate_record_dict(_valid_base())
    with pytest.raises(PhenomenologyValidationError, match="parent_run_id"):
        assert_parent_run_id_matches(d, {"run_id": "deadbeefdeadbeef"})


def test_provenance_layer_map_keeps_spine():
    layers = provenance_layer_map()
    assert "generic_run_provenance" in layers
    assert SCHEMA in layers["domain_trial_payload"]
    assert "not authenticity" in layers["byte_verification"]
