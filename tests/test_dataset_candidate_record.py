"""DatasetCandidateRecordV1: dict/JSON roundtrip, deterministic ID, and
structural validation rules. Synthetic fixtures only.
"""
from __future__ import annotations

from dataset_importers.candidate_record import (
    DatasetCandidateRecordV1,
    compute_candidate_id,
    infer_benchmark_role_recommendation,
    infer_transition_readiness,
)
from dataset_importers.validation import DatasetImporterValidationError


def _minimal_valid_record(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id="ds-example-1",
        display_name="Example Dataset",
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        download_required="true",
        modalities=["EEG"],
        condition_labels=["rest", "task"],
        subject_count=10,
        transition_readiness="candidate_transition_possible",
        benchmark_role_recommendation="development_candidate",
        risks=["example risk"],
        limitations=["example limitation"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetCandidateRecordV1.make(**kwargs)


def test_dict_roundtrip():
    rec = _minimal_valid_record()
    d = rec.to_dict()
    rec2 = DatasetCandidateRecordV1.from_dict(d)
    assert rec2.to_dict() == d


def test_json_roundtrip():
    rec = _minimal_valid_record()
    text = rec.to_json()
    rec2 = DatasetCandidateRecordV1.from_json(text)
    assert rec2.to_dict() == rec.to_dict()


def test_write_json_roundtrip(tmp_path):
    rec = _minimal_valid_record()
    path = rec.write_json(tmp_path / "candidate.json")
    rec2 = DatasetCandidateRecordV1.from_json(path.read_text(encoding="utf-8"))
    assert rec2.candidate_id == rec.candidate_id


def test_candidate_id_deterministic():
    rec_a = _minimal_valid_record()
    rec_b = _minimal_valid_record(display_name="Different display name entirely")
    assert rec_a.candidate_id == rec_b.candidate_id
    assert rec_a.candidate_id == compute_candidate_id(
        source_catalog="synthetic_fixture", source_dataset_id="ds-example-1"
    )


def test_candidate_id_differs_across_source_dataset_id():
    rec_a = _minimal_valid_record(source_dataset_id="ds-a")
    rec_b = _minimal_valid_record(source_dataset_id="ds-b")
    assert rec_a.candidate_id != rec_b.candidate_id


def test_valid_record_has_no_errors():
    rec = _minimal_valid_record()
    assert rec.validate() == []


def test_validation_fails_on_empty_limitations():
    rec = _minimal_valid_record(limitations=[])
    errors = rec.validate()
    assert any("limitations" in e for e in errors)


def test_validation_fails_on_empty_risks():
    rec = _minimal_valid_record(risks=[])
    errors = rec.validate()
    assert any("risks" in e for e in errors)


def test_validation_fails_on_missing_provenance():
    rec = _minimal_valid_record(provenance="")
    errors = rec.validate()
    assert any("provenance" in e for e in errors)


def test_unknown_license_requires_unknown_high_risk():
    rec = _minimal_valid_record(license="unknown", license_risk="permissive_low")
    errors = rec.validate()
    assert any("license_risk" in e for e in errors)
    # Correcting to unknown_high resolves it.
    rec2 = _minimal_valid_record(license="unknown", license_risk="unknown_high")
    assert rec2.validate() == []


def test_validate_or_raise_raises_on_invalid_record():
    rec = _minimal_valid_record(provenance="")
    try:
        rec.validate_or_raise()
        assert False, "expected DatasetImporterValidationError"
    except DatasetImporterValidationError:
        pass


def test_candidate_id_mismatch_is_a_validation_error():
    rec = _minimal_valid_record()
    rec.candidate_id = "not-the-real-id"
    errors = rec.validate()
    assert any("candidate_id" in e for e in errors)


def test_restricted_or_unknown_access_cannot_be_development_candidate():
    rec = _minimal_valid_record(access_status="restricted", benchmark_role_recommendation="development_candidate")
    errors = rec.validate()
    assert any("development_candidate" in e for e in errors)

    rec2 = _minimal_valid_record(access_status="unknown", benchmark_role_recommendation="development_candidate")
    errors2 = rec2.validate()
    assert any("development_candidate" in e for e in errors2)


def test_blocked_license_or_access_must_forbid_export_uses():
    rec = _minimal_valid_record(
        transition_readiness="blocked_license_or_access",
        benchmark_role_recommendation="blocked",
        forbidden_uses=["clinical_claim"],  # missing transition_export/phase_space_export
    )
    errors = rec.validate()
    assert any("rule 7" in e for e in errors)


def test_allowed_uses_can_never_contain_evidence_authority_uses():
    rec = _minimal_valid_record(allowed_uses=["documentation", "transition_export"])
    errors = rec.validate()
    assert any("rule 8" in e for e in errors)


def test_forbidden_uses_must_always_include_evidence_authority_uses():
    rec = _minimal_valid_record(forbidden_uses=["clinical_claim", "diagnostic_claim"])
    errors = rec.validate()
    assert any("rule 8" in e for e in errors)


def test_no_candidate_can_allow_terminal_claim_uses():
    for use in ("final_claim_confirmation", "clinical_claim", "mechanistic_causal_claim", "prospective_prediction_claim"):
        rec = _minimal_valid_record(allowed_uses=["documentation", use])
        errors = rec.validate()
        assert any("rule 9" in e for e in errors), f"{use} should trigger rule 9"


def test_forbidden_uses_missing_required_floor_fails():
    rec = _minimal_valid_record(forbidden_uses=["transition_export", "phase_space_export"])
    errors = rec.validate()
    assert any("rule 9" in e for e in errors)


def test_source_catalog_required_and_explicit():
    rec = _minimal_valid_record(source_catalog="")
    errors = rec.validate()
    assert any("rule 11" in e for e in errors)

    rec2 = _minimal_valid_record(source_catalog="not_a_real_catalog")
    errors2 = rec2.validate()
    assert any("rule 11" in e for e in errors2)


def test_download_required_must_be_explicit_tristate():
    rec = _minimal_valid_record(download_required="")
    errors = rec.validate()
    assert any("rule 12" in e for e in errors)

    rec2 = _minimal_valid_record(download_required="maybe")
    errors2 = rec2.validate()
    assert any("rule 12" in e for e in errors2)


def test_banned_phrase_in_free_text_fails():
    rec = _minimal_valid_record(recommended_next_action="this metadata proves consciousness beyond doubt")
    errors = rec.validate()
    assert any("banned phrase" in e for e in errors)


def test_negative_subject_count_fails():
    rec = _minimal_valid_record(subject_count=-1)
    errors = rec.validate()
    assert any("subject_count" in e for e in errors)


def test_infer_transition_readiness_ladder():
    assert infer_transition_readiness(
        modality_supported=False, license_ok=True, access_ok=True, has_conditions=True, has_subject_count=True
    ) == "blocked_unsupported_modality"
    assert infer_transition_readiness(
        modality_supported=True, license_ok=False, access_ok=True, has_conditions=True, has_subject_count=True
    ) == "blocked_license_or_access"
    assert infer_transition_readiness(
        modality_supported=True, license_ok=True, access_ok=True, has_conditions=False, has_subject_count=False
    ) == "blocked_missing_metadata"
    assert infer_transition_readiness(
        modality_supported=True, license_ok=True, access_ok=True, has_conditions=True, has_subject_count=True
    ) == "candidate_transition_possible"
    assert infer_transition_readiness(
        modality_supported=True, license_ok=True, access_ok=True, has_conditions=True, has_subject_count=False
    ) == "derived_feature_extraction_needed"
    assert infer_transition_readiness(
        modality_supported=True, license_ok=True, access_ok=True, has_conditions=False, has_subject_count=True
    ) == "explicit_condition_mapping_needed"


def test_infer_benchmark_role_recommendation():
    assert infer_benchmark_role_recommendation(
        transition_readiness="blocked_missing_metadata", access_status="unknown"
    ) == "blocked"
    assert infer_benchmark_role_recommendation(
        transition_readiness="candidate_transition_possible", access_status="public"
    ) == "development_candidate"
    assert infer_benchmark_role_recommendation(
        transition_readiness="candidate_transition_possible", access_status="unknown"
    ) == "review_needed"
    assert infer_benchmark_role_recommendation(
        transition_readiness="explicit_condition_mapping_needed", access_status="public"
    ) == "exploration_candidate"
    assert infer_benchmark_role_recommendation(
        transition_readiness="metadata_only", access_status="public"
    ) == "documentation_only"
