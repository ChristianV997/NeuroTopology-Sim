"""ExternalToolRecordV1: dict/JSON roundtrip, stable tool_id, and the
baseline rule-1/rule-2/rule-3 structural checks. Synthetic fixtures only --
no network access, no external package installation.
"""
from __future__ import annotations

from external_tools.tool_record import ExternalToolRecordV1, compute_tool_id


def _base_record(**overrides) -> ExternalToolRecordV1:
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
    return ExternalToolRecordV1.make(**kwargs)


def test_base_record_is_valid():
    record = _base_record()
    assert record.validate() == []


def test_dict_roundtrip():
    record = _base_record()
    restored = ExternalToolRecordV1.from_dict(record.to_dict())
    assert restored == record


def test_json_roundtrip():
    record = _base_record()
    restored = ExternalToolRecordV1.from_json(record.to_json())
    assert restored == record
    assert restored.to_dict() == record.to_dict()


def test_write_json_round_trips_through_disk(tmp_path):
    record = _base_record()
    path = record.write_json(tmp_path / "sub" / "tool.json")
    assert path.exists()
    restored = ExternalToolRecordV1.from_json(path.read_text(encoding="utf-8"))
    assert restored == record


def test_tool_id_is_deterministic_slug_of_name():
    record = _base_record(name="My Test Tool 2.0!")
    assert record.tool_id == "my-test-tool-2-0"
    assert record.tool_id == compute_tool_id("My Test Tool 2.0!")


def test_tool_id_stable_across_two_builds_with_same_name():
    a = _base_record(name="Repeatable Tool")
    b = _base_record(name="Repeatable Tool")
    assert a.tool_id == b.tool_id


def test_recompute_id_matches_tool_id_for_valid_record():
    record = _base_record()
    assert record.recompute_id() == record.tool_id


def test_validation_fails_on_tampered_tool_id():
    record = _base_record()
    record.tool_id = "not-the-real-slug"
    errors = record.validate()
    assert any("rule 3" in e for e in errors)


def test_validation_fails_on_empty_limitations():
    record = _base_record(limitations=[])
    errors = record.validate()
    assert any("limitations" in e and "rule 1" in e for e in errors)


def test_validation_fails_on_empty_risks():
    record = _base_record(risks=[])
    errors = record.validate()
    assert any("risks" in e and "rule 1" in e for e in errors)


def test_validation_fails_on_missing_provenance():
    record = _base_record(provenance="")
    errors = record.validate()
    assert any("provenance" in e and "rule 2" in e for e in errors)


def test_validate_or_raise_raises_on_invalid_record():
    from external_tools.validation import ExternalToolValidationError

    record = _base_record(risks=[])
    try:
        record.validate_or_raise()
        assert False, "expected ExternalToolValidationError"
    except ExternalToolValidationError:
        pass


def test_validate_or_raise_does_not_raise_on_valid_record():
    _base_record().validate_or_raise()
