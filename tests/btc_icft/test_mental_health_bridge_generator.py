import json
from pathlib import Path
from tools.tol_digest.mental_health_bridge.generator import CENTRAL_THESIS, REQUIRED_OUTPUTS, generate

DOMAINS = ["depression","anxiety","trauma/PTSD","addiction","OCD","rumination","burnout","dissociation","psychosis-risk"]
GROUPS = ["self_report_features","physiology_features","neuro_features","behavior_features","language_features","context_features"]

def test_generator_writes_all_required_files(tmp_path):
    out = tmp_path / "out"
    generate(tmp_path / "missing_root", out)
    for name in REQUIRED_OUTPUTS:
        assert (out / name).exists()

def test_generator_handles_missing_tol_outputs_with_not_available_status(tmp_path):
    out = tmp_path / "out"
    manifest = generate(tmp_path / "root", out)
    assert manifest["not_available_inputs"]
    assert any(i["status"] == "not_available" for i in manifest["input_status"]["inputs"])

def test_master_model_contains_central_thesis(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    assert CENTRAL_THESIS in (out / "mental_flexibility_master_model.md").read_text()

def test_disorder_matrix_contains_required_domains(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    data = json.loads((out / "disorder_to_dynamics_matrix.json").read_text())
    for domain in DOMAINS:
        assert domain in data
        assert data[domain]["claim_scope"] == "research_hypothesis"


def test_ml_feature_schema_contains_required_groups(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    data = json.loads((out / "ml_feature_schema.json").read_text())
    present = {row["feature_group"] for row in data}
    assert set(GROUPS).issubset(present)
    assert all("privacy_risk" in row and "allowed_mode" in row for row in data)


def test_intervention_safety_ladder_contains_all_six_levels(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    text = (out / "intervention_safety_ladder.md").read_text()
    for i in range(6):
        assert f"Level {i}" in text


def test_clinical_translation_map_separates_modes(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    text = (out / "clinical_translation_map.md").read_text().lower()
    for term in ["research mode", "wellness mode", "clinician-support candidate mode", "medical device / samd candidate mode", "regulatory boundary"]:
        assert term in text


def test_observable_matrix_contains_layers(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    data = json.loads((out / "body_brain_mind_observable_matrix.json").read_text())
    assert {"body","brain","mind","behavior","environment"}.issubset({row["layer"] for row in data})


def test_funding_map_contains_mvp_sequence(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    text = (out / "funding_and_product_opportunity_map.md").read_text()
    assert "MVP sequence" in text and "Research artifact dashboard" in text


def test_validation_protocols_contains_falsifiers(tmp_path):
    out = tmp_path / "out"; generate(tmp_path, out)
    assert "Falsifiers" in (out / "validation_protocols.md").read_text()
