"""AdapterContractV1: roundtrip, provenance/limitations requirements,
output-target validation, default claim ceiling, and forbidden-outputs
enforcement. Synthetic fixtures only.
"""
from __future__ import annotations

from external_tools.adapter_contract import AdapterContractV1, compute_adapter_id
from external_tools.validation import ExternalToolValidationError


def _base_contract(**overrides) -> AdapterContractV1:
    kwargs = dict(
        tool_id="mne-python",
        adapter_name="mne_adapter_v1",
        integration_mode="dependency",
        input_artifact_kinds=["raw_eeg_meg_files"],
        output_artifact_kinds=["preprocessed_signal_blocks"],
        output_targets=["ArtifactRecordV1"],
        feature_namespaces=["mne.signal"],
        limitations=["Not yet implemented."],
    )
    kwargs.update(overrides)
    return AdapterContractV1.make(**kwargs)


def test_base_contract_is_valid():
    contract = _base_contract()
    assert contract.validate() == []


def test_dict_roundtrip():
    contract = _base_contract()
    restored = AdapterContractV1.from_dict(contract.to_dict())
    assert restored == contract


def test_json_roundtrip():
    contract = _base_contract()
    restored = AdapterContractV1.from_json(contract.to_json())
    assert restored == contract


def test_write_json_round_trips_through_disk(tmp_path):
    contract = _base_contract()
    path = contract.write_json(tmp_path / "sub" / "contract.json")
    restored = AdapterContractV1.from_json(path.read_text(encoding="utf-8"))
    assert restored == contract


def test_adapter_id_is_deterministic():
    a = _base_contract()
    b = _base_contract()
    assert a.adapter_id == b.adapter_id == compute_adapter_id(tool_id="mne-python", adapter_name="mne_adapter_v1")


def test_adapter_id_differs_for_different_tool_or_name():
    a = _base_contract(tool_id="mne-python")
    b = _base_contract(tool_id="mne-bids")
    c = _base_contract(adapter_name="a_different_adapter")
    assert a.adapter_id != b.adapter_id
    assert a.adapter_id != c.adapter_id


def test_recompute_id_matches_for_untampered_contract():
    contract = _base_contract()
    assert contract.recompute_id() == contract.adapter_id


def test_defaults_include_fixed_forbidden_outputs_and_validation_requirements():
    contract = _base_contract()
    assert "clinical_claim" in contract.forbidden_outputs
    assert "diagnostic_claim" in contract.forbidden_outputs
    assert "mechanistic_causal_claim" in contract.forbidden_outputs
    assert "fail_closed_if_required_metadata_missing" in contract.validation_requirements
    assert "source_tool_version" in contract.provenance_requirements


def test_default_claim_scope_ceiling_is_exploratory_metric():
    contract = _base_contract()
    assert contract.allowed_claim_scope_ceiling == "exploratory_metric"


def test_default_evidence_level_ceiling_is_computational_artifact():
    contract = _base_contract()
    assert contract.evidence_level_ceiling == "L0_computational_artifact"


def test_default_implementation_status_is_planned():
    contract = _base_contract()
    assert contract.implementation_status == "planned"


def test_validation_requires_non_empty_provenance_requirements():
    contract = _base_contract(provenance_requirements=[])
    errors = contract.validate()
    assert any("provenance_requirements" in e for e in errors)


def test_validation_requires_source_tool_version_in_provenance_requirements():
    contract = _base_contract(provenance_requirements=["some_other_field"])
    errors = contract.validate()
    assert any("provenance_requirements is missing required entries" in e for e in errors)


def test_validation_requires_non_empty_limitations():
    contract = _base_contract(limitations=[])
    errors = contract.validate()
    assert any("limitations must be a non-empty list" in e for e in errors)


def test_validation_requires_non_empty_validation_requirements():
    contract = _base_contract(validation_requirements=[])
    errors = contract.validate()
    assert any("validation_requirements" in e for e in errors)


def test_validation_requires_fail_closed_entry_in_validation_requirements():
    contract = _base_contract(validation_requirements=["some_other_check"])
    errors = contract.validate()
    assert any("validation_requirements is missing required entries" in e for e in errors)


def test_output_targets_must_be_non_empty():
    contract = _base_contract(output_targets=[])
    errors = contract.validate()
    assert any("output_targets must be a non-empty list" in e for e in errors)


def test_output_targets_validate_against_allowed_values():
    contract = _base_contract(output_targets=["NotARealTarget"])
    errors = contract.validate()
    assert any("output_targets contains unknown target" in e for e in errors)


def test_all_canonical_output_targets_are_individually_valid():
    for target in (
        "DatasetRecordV1", "ArtifactRecordV1", "TransitionRecordV1",
        "PhaseSpaceCoordinateV1", "EvidenceBundleV1", "EvidenceReportV1",
        "external_metadata_only",
    ):
        contract = _base_contract(output_targets=[target])
        assert contract.validate() == [], f"target={target}"


def test_feature_namespaces_must_be_non_empty():
    contract = _base_contract(feature_namespaces=[])
    errors = contract.validate()
    assert any("feature_namespaces must be a non-empty list" in e for e in errors)


def test_forbidden_outputs_cannot_drop_required_categories():
    contract = _base_contract(forbidden_outputs=["clinical_claim"])
    errors = contract.validate()
    assert any("forbidden_outputs is missing required entries" in e for e in errors)


def test_forbidden_outputs_cannot_be_emptied():
    contract = _base_contract(forbidden_outputs=[])
    errors = contract.validate()
    assert any("forbidden_outputs must be a non-empty list" in e for e in errors)


def test_claim_scope_ceiling_rejects_blocked_scope_values():
    for blocked in ("clinical", "diagnostic", "treatment", "mechanistic_causal"):
        contract = _base_contract(allowed_claim_scope_ceiling=blocked)
        errors = contract.validate()
        assert any("allowed_claim_scope_ceiling" in e for e in errors), f"scope={blocked}"


def test_claim_scope_ceiling_accepts_cross_subject_dataset_specific():
    contract = _base_contract(allowed_claim_scope_ceiling="cross_subject_dataset_specific")
    assert contract.validate() == []


def test_implementation_status_implemented_requires_verified_metadata_flag():
    contract = _base_contract(implementation_status="implemented")
    errors = contract.validate()
    assert any("implementation_verified" in e for e in errors)


def test_implementation_status_implemented_with_verified_flag_validates():
    contract = _base_contract(implementation_status="implemented", metadata={"implementation_verified": True})
    assert contract.validate() == []


def test_no_seed_style_contract_may_claim_implemented_by_default():
    # This milestone implements no adapters -- the schema default must
    # never silently claim readiness.
    contract = _base_contract()
    assert contract.implementation_status != "implemented"


def test_banned_phrase_in_limitations_fails():
    contract = _base_contract(limitations=["this proves consciousness beyond doubt"])
    errors = contract.validate()
    assert any("banned phrase" in e for e in errors)


def test_validate_or_raise_raises_on_invalid_contract():
    contract = _base_contract(output_targets=[])
    try:
        contract.validate_or_raise()
        assert False, "expected ExternalToolValidationError"
    except ExternalToolValidationError:
        pass
