from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools.toe_research.literature_bridge.validator import validate


MODULE_OUTPUTS = [
    ("topology_telemetry_digest", "topology_telemetry_upgrade_digest.md"),
    ("active_inference_digest", "active_inference_allostasis_digest.md"),
    ("computational_psychiatry_digest", "computational_psychiatry_digest.md"),
    ("bioelectric_digest", "bioelectric_basal_cognition_digest.md"),
    ("cosmology_constraints", "cosmology_constraint_matrix.json"),
    ("gravitational_wave_constraints", "gravitational_wave_constraint_matrix.json"),
    ("adversarial_consciousness_matrix", "consciousness_theory_adversarial_matrix.json"),
    ("equation_registry", "equation_candidate_registry.json"),
    ("falsifier_registry", "toe_falsifier_watchlist.json"),
]


def _generate(output):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.toe_research.literature_bridge.generator",
            "--roots",
            str(output / "missing_upstream"),
            "--out",
            str(output),
        ],
        check=True,
    )
    for module, name in MODULE_OUTPUTS:
        subprocess.run(
            [
                sys.executable,
                "-m",
                f"tools.toe_research.literature_bridge.{module}",
                "--out",
                str(output / name),
            ],
            check=True,
        )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.toe_research.literature_bridge.reporting",
            "--root",
            str(output),
            "--out",
            str(output / "toe_literature_bridge_report.md"),
        ],
        check=True,
    )


@pytest.fixture
def generated(tmp_path):
    output = tmp_path / "bridge"
    output.mkdir()
    _generate(output)
    return output


def test_validator_accepts_complete_bridge(generated):
    result = validate(generated)
    assert result["ok"] is True, result["violations"]
    assert set(result["checked_files"])


def test_validator_fails_when_required_output_is_missing(generated):
    (generated / "cosmology_constraint_matrix.json").unlink()
    result = validate(generated)
    assert "missing:cosmology_constraint_matrix.json" in result["violations"]


def test_validator_fails_when_required_cluster_content_is_missing(generated):
    (generated / "topology_telemetry_upgrade_digest.md").write_text(
        "topology only", encoding="utf-8"
    )
    result = validate(generated)
    assert any(
        item.startswith("missing_content:topology_telemetry_upgrade_digest.md")
        for item in result["violations"]
    )


def test_validator_fails_when_falsifier_is_missing(generated):
    path = generated / "toe_falsifier_watchlist.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(rows[:-1]), encoding="utf-8")
    result = validate(generated)
    assert "missing_falsifier:F10" in result["violations"]


def test_validator_fails_when_equation_registry_is_empty(generated):
    (generated / "equation_candidate_registry.json").write_text("[]", encoding="utf-8")
    result = validate(generated)
    assert "missing_equation:EQ-001" in result["violations"]


@pytest.mark.parametrize(
    "unsafe_claim",
    [
        "TOE validated.",
        "Qabs proves consciousness.",
        "This system diagnoses patients.",
        "This system provides clinical treatment.",
        "This is an afterlife proof.",
        "This is a Nibbāna proof.",
        "Ontology promotion is allowed.",
    ],
)
def test_validator_rejects_unsafe_claim_language(generated, unsafe_claim):
    report = generated / "toe_literature_bridge_report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "\n" + unsafe_claim,
        encoding="utf-8",
    )
    result = validate(generated)
    assert any(item.startswith("forbidden_claim:") for item in result["violations"])


def test_validator_rejects_enabled_runtime_flag(generated):
    path = generated / "generation_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["guardrails"]["live_api_calls_allowed"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = validate(generated)
    assert any("live_api_calls_allowed=True" in item for item in result["violations"])


def test_validator_rejects_missing_guardrail(generated):
    path = generated / "generation_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["guardrails"]["dataset_downloads_allowed"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = validate(generated)
    assert any(
        item.endswith(":dataset_downloads_allowed")
        for item in result["violations"]
    )


def test_validator_rejects_key_like_secret(generated):
    report = generated / "toe_literature_bridge_report.md"
    report.write_text("credential sk-proj-abcdefghijklmnop", encoding="utf-8")
    result = validate(generated)
    assert "api_key_exposure:openai_key_pattern" in result["violations"]


def test_validator_cli_writes_structured_failure(generated):
    (generated / "toe_falsifier_watchlist.json").write_text("[]", encoding="utf-8")
    json_out = generated / "validation.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.toe_research.literature_bridge.validator",
            "--root",
            str(generated),
            "--json-out",
            str(json_out),
        ]
    )
    result = json.loads(json_out.read_text(encoding="utf-8"))
    assert completed.returncode == 1
    assert result["ok"] is False
    assert result["violations"]
