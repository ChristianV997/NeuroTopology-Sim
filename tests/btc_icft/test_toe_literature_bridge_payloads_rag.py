from __future__ import annotations

import json
import subprocess
import sys

from tools.toe_research.literature_bridge.falsifier_registry import FALSIFIERS


def _write_registries(root):
    (root / "equation_candidate_registry.json").write_text(
        json.dumps([{"equation_id": f"EQ-{i:03d}"} for i in range(1, 11)]),
        encoding="utf-8",
    )
    (root / "toe_falsifier_watchlist.json").write_text(
        json.dumps(FALSIFIERS), encoding="utf-8"
    )
    (root / "cosmology_constraint_matrix.json").write_text(
        json.dumps([{"constraint_id": "C1"}]), encoding="utf-8"
    )
    (root / "gravitational_wave_constraint_matrix.json").write_text(
        json.dumps([{"constraint_id": "G1"}]), encoding="utf-8"
    )
    (root / "consciousness_theory_adversarial_matrix.json").write_text(
        json.dumps([{"theory": "Global Workspace Theory"}]), encoding="utf-8"
    )


def test_command_center_payloads_disable_every_unsafe_action(tmp_path):
    root = tmp_path / "bridge"
    root.mkdir()
    _write_registries(root)
    output = tmp_path / "payloads"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.toe_research.literature_bridge.command_center_payloads",
            "--root",
            str(root),
            "--out",
            str(output),
        ],
        check=True,
    )

    payload = json.loads(
        (output / "toe_literature_bridge_status.json").read_text(encoding="utf-8")
    )
    for flag in (
        "toe_validation_claims_allowed",
        "final_theory_claims_allowed",
        "consciousness_proof_claims_allowed",
        "clinical_claims_allowed",
        "ontology_promotion_allowed",
        "q_qabs_fdress_proof_claims_allowed",
        "real_data_auto_execution_allowed",
        "live_api_calls_allowed",
        "api_key_exposure_allowed",
    ):
        assert payload[flag] is False
    assert payload["registry_summary"]["falsifiers"] == [f"F{i}" for i in range(1, 11)]


def test_rag_pack_contains_registry_summaries_and_blocked_answers(tmp_path):
    root = tmp_path / "bridge"
    root.mkdir()
    _write_registries(root)
    output = tmp_path / "rag"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.toe_research.literature_bridge.rag_pack",
            "--root",
            str(root),
            "--out",
            str(output),
        ],
        check=True,
    )

    safe = json.loads((output / "rag_safe_documents.json").read_text(encoding="utf-8"))
    blocked = json.loads(
        (output / "rag_forbidden_answer_patterns.json").read_text(encoding="utf-8")
    )
    assert safe["registry_summary"]["equation_ids"] == [f"EQ-{i:03d}" for i in range(1, 11)]
    assert safe["registry_summary"]["falsifier_ids"] == [f"F{i}" for i in range(1, 11)]
    assert {"TOE validated", "clinical treatment", "ontology promotion"} <= set(blocked)


def test_obsidian_sync_writes_expected_p40_notes(tmp_path):
    output = tmp_path / "sync.json"
    vault = tmp_path / "vault"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.toe_research.literature_bridge.obsidian_sync",
            "--root",
            str(tmp_path / "bridge"),
            "--vault",
            str(vault),
            "--out",
            str(output),
        ],
        check=True,
    )
    note_dir = vault / "13_TOE_Literature_Bridge"
    expected = {
        "TOE_Literature_Priority_Matrix.md",
        "Topology_Telemetry_Upgrade.md",
        "Active_Inference_Allostasis_Digest.md",
        "Computational_Psychiatry_Digest.md",
        "Bioelectric_Basal_Cognition_Digest.md",
        "Cosmology_Constraint_Matrix.md",
        "Gravitational_Wave_Constraint_Matrix.md",
        "Consciousness_Theory_Adversarial_Matrix.md",
        "Equation_Candidate_Registry.md",
        "TOE_Falsifier_Watchlist.md",
        "TOE_Theory_Integration_Digest.md",
    }
    assert {path.name for path in note_dir.glob("*.md")} == expected
