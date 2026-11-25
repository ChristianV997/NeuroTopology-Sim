"""Round-trip RunRecord / TransitionRecord artifact pointers (no TransitionStore write required)."""

from __future__ import annotations

import json
from pathlib import Path

from runs.run_record import RunRecordV1
from shared.phenomenology_perturbation import (
    RUN_ARTIFACT_KEY,
    SCHEMA,
    assert_parent_run_id_matches,
    merge_run_artifact_pointer,
    validate_record_dict,
)
from shared.phenomenology_perturbation.run_link import (
    TRANSITION_ARTIFACT_KEY,
    pointer_for_transition_artifact_paths,
)
from transitions.record import TransitionRecordV1


def _minimal_domain(parent_run_id: str) -> dict:
    return {
        "schema": SCHEMA,
        "record_id": "ppr-roundtrip-001",
        "parent_run_id": parent_run_id,
        "data_status": "synthetic",
        "causal_claim_type": "none",
        "evidence_status": "exploratory_synthetic",
        "practice": {
            "instruction_id": "instr-synth",
            "instruction_text": "Attend to sounds.",
            "practice_dose": {"duration_s": 60.0, "session_count": 1},
        },
        "perturbation": {
            "event_id": "pert-1",
            "randomized": True,
            "onset_s": 10.0,
            "offset_s": 10.2,
            "modality": "sensory_probe",
            "target": "tone",
            "amplitude": 0.1,
            "units": "normalized_intensity",
            "observation_origin": "synthetic",
        },
        "behavior": {
            "missing": False,
            "response": {"key": "present"},
            "missingness_reason": None,
            "observation_origin": "synthetic",
            "rt_s": 0.4,
        },
        "delayed_report": {
            "prompt_exact": "Rate clarity during the tone window.",
            "target_interval_start_s": 10.0,
            "target_interval_end_s": 10.2,
            "response_time_s": 20.2,
            "report_delay_s": 10.0,
            "confidence": 0.5,
            "report_text": "Clear brief tone.",
            "language": "en",
            "observation_origin": "synthetic",
        },
        "signal_quality": {
            "eeg_ok": False,
            "sync_ok": True,
            "time_reference": "session_t0",
            "units": {"time": "s"},
        },
        "privacy": {
            "consent_status": "synthetic_no_human_subjects",
            "access_status": "public_synthetic",
            "pseudonym_token": None,
            "redaction_complete": None,
        },
    }


def test_run_and_transition_pointer_json_roundtrip(tmp_path: Path):
    run_id = "abcd1234abcd1234"
    rel = "artifacts/ppr-roundtrip-001.json"
    domain = validate_record_dict(_minimal_domain(run_id))

    run = RunRecordV1.make(
        run_id=run_id,
        run_kind="hypothesis",
        data_mode="synthetic",
        dataset_id="synthetic_ppr",
        artifacts=merge_run_artifact_pointer({}, rel),
        source="tests.phenomenology_perturbation",
        metrics={"contemplative_effect_established": False},
    )
    assert_parent_run_id_matches(domain, run.to_dict())
    assert run.artifacts[RUN_ARTIFACT_KEY] == rel

    run_path = tmp_path / "RunRecord.json"
    run.write_json(run_path)
    loaded_run = RunRecordV1.from_dict(json.loads(run_path.read_text(encoding="utf-8")))
    assert loaded_run.artifacts[RUN_ARTIFACT_KEY] == rel
    assert_parent_run_id_matches(domain, loaded_run.to_dict())

    tr = TransitionRecordV1.make(
        dataset_id="synthetic_ppr",
        subject_id="synth-anon-0001",
        session_id="sess-1",
        modality="eeg",
        feature_names=["spectral.alpha_power"],
        limitations=[
            "Synthetic pointer round-trip only.",
            "Physiology feature is not a consciousness or attainment label.",
        ],
        claim_scope="computational_artifact",
        evidence_level="L0_computational_artifact",
        artifact_paths=pointer_for_transition_artifact_paths(rel),
        metadata={"parent_run_id": run_id},
    )
    assert tr.validate() == []
    tr_path = tmp_path / "TransitionRecord.json"
    tr.write_json(tr_path)
    loaded_tr = TransitionRecordV1.from_json(tr_path.read_text(encoding="utf-8"))
    assert loaded_tr.artifact_paths[TRANSITION_ARTIFACT_KEY] == rel
    assert loaded_tr.recompute_id() == loaded_tr.transition_id
