import json
from pathlib import Path
from tools.tol_digest.mental_health_bridge.generator import generate
from tools.tol_digest.mental_health_bridge.validator import validate


def valid_root(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out); return out


def assert_invalid_with(tmp_path, filename, phrase):
    out = valid_root(tmp_path)
    (out / filename).write_text((out / filename).read_text() + f"\n{phrase}\n")
    res = validate(out)
    assert not res["ok"], res


def test_validator_passes_valid_generated_outputs(tmp_path):
    assert validate(valid_root(tmp_path))["ok"]


def test_validator_fails_on_diagnosis_claim(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "The system diagnoses depression.")


def test_validator_fails_on_treatment_cure_claim(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "The system cures depression.")


def test_validator_fails_on_ai_therapist(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "This is an AI therapist.")


def test_validator_fails_on_replaces_clinician(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "It replaces clinician judgment.")


def test_validator_fails_on_trauma_deletion(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "Use trauma deletion now.")


def test_validator_fails_on_instant_arhat(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "instant arhat protocol")


def test_validator_fails_on_qabs_proves_liberation(tmp_path):
    assert_invalid_with(tmp_path, "mental_flexibility_master_model.md", "Qabs proves liberation.")


def test_validator_fails_on_missing_privacy_risk(tmp_path):
    out = valid_root(tmp_path)
    data = json.loads((out / "ml_feature_schema.json").read_text())
    data[0].pop("privacy_risk")
    (out / "ml_feature_schema.json").write_text(json.dumps(data))
    assert not validate(out)["ok"]


def test_validator_fails_if_emergency_boundary_missing(tmp_path):
    out = valid_root(tmp_path)
    (out / "intervention_safety_ladder.md").write_text("# Intervention Safety Ladder\nLevel 0\n")
    assert not validate(out)["ok"]


def test_validator_fails_if_clinical_modes_not_separated(tmp_path):
    out = valid_root(tmp_path)
    (out / "clinical_translation_map.md").write_text("# Clinical Translation Map\n")
    assert not validate(out)["ok"]


def test_validator_fails_if_falsifiers_missing(tmp_path):
    out = valid_root(tmp_path)
    (out / "validation_protocols.md").write_text("# Validation Protocols\n")
    assert not validate(out)["ok"]
