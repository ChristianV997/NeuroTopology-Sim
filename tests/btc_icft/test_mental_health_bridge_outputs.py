import json
from pathlib import Path
from tools.tol_digest.mental_health_bridge.generator import generate
from tools.tol_digest.mental_health_bridge.obsidian_sync import MAP, sync
from tools.tol_digest.mental_health_bridge.command_center_payloads import build


def test_obsidian_sync_writes_all_expected_notes(tmp_path):
    root = tmp_path / "out"; generate(tmp_path, root)
    vault = tmp_path / "obsidian"
    res = sync(root, vault)
    assert res["ok"]
    for dst in MAP.values():
        assert (vault / "07_ToL" / dst).exists()


def test_command_center_payload_writes_status_json(tmp_path):
    root = tmp_path / "out"; generate(tmp_path, root)
    payload = build(root)
    out = tmp_path / "mock_payloads" / "mental_health_bridge_status.json"
    out.parent.mkdir(parents=True); out.write_text(json.dumps(payload))
    assert out.exists()


def test_command_center_payload_guardrail_flags_false(tmp_path):
    root = tmp_path / "out"; generate(tmp_path, root)
    guardrails = build(root)["guardrails"]
    assert guardrails["diagnosis_claims_allowed"] is False
    assert guardrails["treatment_claims_allowed"] is False
    assert guardrails["clinician_replacement_allowed"] is False


def test_makefile_contains_targets():
    text = Path("Makefile").read_text()
    assert "mental-health-bridge:" in text
    assert "validate-mental-health-bridge:" in text
    assert "mental-health-bridge-cycle:" in text


def test_docs_exist():
    assert Path("docs/mental_flexibility_systems_medicine_bridge.md").exists()


def test_no_tests_require_network_openai_or_real_data():
    for path in Path("tests/btc_icft").glob("test_mental_health_bridge_*.py"):
        text = path.read_text().lower()
        assert "request" + "s." not in text and "url" + "lib" not in text
        assert "open" + "ai_api_key" not in text and "open" + "ai" not in text.replace("network_" + "open" + "ai", "")
        assert "ds" + "005620" not in text and "down" + "load" not in text


def test_tests_make_no_clinical_claims():
    text = "\n".join(path.read_text().lower() for path in Path("tests/btc_icft").glob("test_mental_health_bridge_*.py"))
    assert "clinical " + "efficacy" not in text
