"""License/commercial-use policy rules (external_tools.validation rules
4-12). Synthetic minimal records only -- each test flips exactly one field
away from a known-valid baseline to exercise exactly one rule.
"""
from __future__ import annotations

from external_tools.tool_record import ExternalToolRecordV1


def _base_kwargs(**overrides):
    kwargs = dict(
        name="Test Tool",
        category="topology_tda",
        public_url="https://example.org/test-tool",
        repository_url="https://github.com/example/test-tool",
        documentation_url="https://example.org/test-tool/docs",
        license="MIT",
        license_risk="permissive_low",
        commercial_use_status="allowed_with_notice",
        integration_mode="dependency",
        priority="P0",
        current_status="ready_for_adapter",
        supported_modalities=["EEG"],
        artifact_inputs=["raw_eeg"],
        artifact_outputs=["features"],
        feature_namespaces=["test.features"],
        planned_adapter="test_adapter_v1 (not yet implemented)",
        allowed_uses=["documentation"],
        forbidden_uses=["clinical_claim"],
        risks=["Some risk."],
        limitations=["Some limitation."],
        provenance="Verified via test fixture.",
        metadata={},
    )
    kwargs.update(overrides)
    return kwargs


def _base_record(**overrides) -> ExternalToolRecordV1:
    return ExternalToolRecordV1.make(**_base_kwargs(**overrides))


def test_permissive_p0_dependency_validates():
    record = _base_record(priority="P0", license_risk="permissive_low", integration_mode="dependency")
    assert record.validate() == []


def test_permissive_optional_backend_validates():
    record = _base_record(priority="P1", license_risk="permissive_low", integration_mode="optional_backend")
    assert record.validate() == []


def test_agpl_cannot_be_dependency_in_commercial_core():
    record = _base_record(
        priority="P3", license_risk="agpl_high", integration_mode="dependency",
        commercial_use_status="avoid_core",
    )
    errors = record.validate()
    assert any("rule 4" in e for e in errors)


def test_copyleft_medium_cannot_be_dependency():
    record = _base_record(
        priority="P3", license_risk="copyleft_medium", integration_mode="dependency",
        commercial_use_status="avoid_core",
    )
    errors = record.validate()
    assert any("rule 4" in e for e in errors)


def test_proprietary_cannot_be_dependency():
    record = _base_record(
        priority="P3", license_risk="proprietary_high", integration_mode="dependency",
        commercial_use_status="paid_contract_required",
    )
    errors = record.validate()
    assert any("rule 4" in e or "rule 5" in e for e in errors)


def test_unknown_license_becomes_unknown_high_and_cannot_be_dependency():
    record = _base_record(
        license="unknown", license_risk="unknown_high", integration_mode="dependency",
        metadata={"review_needed": True},
    )
    errors = record.validate()
    assert any("rule 4" in e or "rule 12" in e for e in errors)


def test_unknown_license_with_wrong_risk_tier_fails_rule_12():
    record = _base_record(license="unknown", license_risk="permissive_low", metadata={"review_needed": True})
    errors = record.validate()
    assert any("rule 12" in e for e in errors)


def test_unknown_license_without_review_needed_flag_fails_rule_12():
    record = _base_record(license="unknown", license_risk="unknown_high", integration_mode="reference_only", priority="reference", metadata={})
    errors = record.validate()
    assert any("rule 12" in e for e in errors)


def test_paid_hardware_cannot_be_dependency_or_optional_backend():
    for mode in ("dependency", "optional_backend"):
        record = _base_record(
            priority="P3", license_risk="unknown_high", integration_mode=mode,
            commercial_use_status="paid_contract_required", license="unknown",
            metadata={"review_needed": True},
        )
        errors = record.validate()
        assert any("rule 5" in e for e in errors), f"integration_mode={mode}"


def test_paid_hardware_as_paid_hardware_mode_validates():
    record = _base_record(
        priority="P3", license_risk="unknown_high", integration_mode="paid_hardware",
        commercial_use_status="paid_contract_required", license="unknown",
        metadata={"review_needed": True},
    )
    assert record.validate() == []


def test_reference_only_cannot_be_recommended_for_automatic_integration():
    record = _base_record(
        priority="P0", integration_mode="reference_only", commercial_use_status="reference_only",
    )
    errors = record.validate()
    assert any("rule 6" in e for e in errors)


def test_reference_only_with_reference_priority_validates():
    record = _base_record(
        priority="reference", integration_mode="reference_only", commercial_use_status="reference_only",
        license_risk="copyleft_medium",
    )
    assert record.validate() == []


def test_avoid_core_requires_avoid_priority():
    record = _base_record(
        priority="P2", integration_mode="avoid_core", commercial_use_status="avoid_core",
        license_risk="agpl_high",
    )
    errors = record.validate()
    assert any("rule 7" in e for e in errors)


def test_p0_requires_permissive_or_adapter_only_metadata_import():
    record = _base_record(priority="P0", license_risk="copyleft_medium", integration_mode="optional_backend")
    errors = record.validate()
    assert any("rule 8" in e for e in errors)


def test_p0_with_adapter_only_and_non_permissive_license_fails_rule_8_unless_declared():
    # adapter_only alone satisfies rule 8 even with a non-permissive license.
    record = _base_record(priority="P0", license_risk="copyleft_medium", integration_mode="adapter_only")
    # NOTE: rule 8 allows license_risk=permissive_low OR integration_mode in
    # (adapter_only, metadata_import) -- adapter_only alone should satisfy it.
    errors = [e for e in record.validate() if "rule 8" in e]
    assert errors == []


def test_clinical_qeeg_competitor_must_be_reference_only_by_default():
    record = _base_record(
        category="clinical_qeeg", priority="P2", integration_mode="dependency",
        license_risk="proprietary_high", commercial_use_status="avoid_core",
    )
    errors = record.validate()
    assert any("rule 9" in e for e in errors)


def test_clinical_qeeg_competitor_reference_only_validates():
    record = _base_record(
        category="clinical_qeeg", priority="reference", integration_mode="reference_only",
        commercial_use_status="reference_only", license_risk="proprietary_high",
    )
    assert record.validate() == []


def test_commercial_neurofeedback_competitor_must_default_to_reference_only():
    record = _base_record(
        category="commercial_neurofeedback", priority="P1", integration_mode="optional_backend",
        license_risk="proprietary_high", commercial_use_status="avoid_core",
    )
    errors = record.validate()
    assert any("rule 9" in e for e in errors)


def test_forbidden_overclaim_language_in_provenance_is_rejected():
    record = _base_record(provenance="This tool proves consciousness beyond doubt.")
    errors = record.validate()
    assert any("banned phrase" in e for e in errors)


def test_scraping_language_in_risks_is_rejected():
    record = _base_record(risks=["We should scrape proprietary dashboards from the vendor site."])
    errors = record.validate()
    assert any("banned phrase" in e and "scrape proprietary" in e for e in errors)


def test_reverse_engineer_proprietary_language_is_rejected():
    record = _base_record(limitations=["Plan: reverse engineer proprietary SDK internals."])
    errors = record.validate()
    assert any("banned phrase" in e for e in errors)
