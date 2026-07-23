from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools.toe_research.literature_bridge.falsifier_registry import FALSIFIERS


def _run(module: str, output):
    subprocess.run(
        [sys.executable, "-m", f"tools.toe_research.literature_bridge.{module}", "--out", str(output)],
        check=True,
    )


def test_topology_and_bridge_digests_cover_required_clusters(tmp_path):
    files = {
        "topology_telemetry_digest": "topology.md",
        "active_inference_digest": "active.md",
        "computational_psychiatry_digest": "psych.md",
        "bioelectric_digest": "bio.md",
    }
    for module, name in files.items():
        _run(module, tmp_path / name)

    combined = "\n".join(
        (tmp_path / name).read_text(encoding="utf-8").lower() for name in files.values()
    )
    for term in (
        "hodge", "persistent local laplacian", "sheaf", "precision weighting",
        "allostatic cost", "latent parameters", "recovery latency",
        "adaptive boundary regulation", "substrate-independent regulation",
    ):
        assert term in combined


@pytest.mark.parametrize(
    ("module", "required_terms"),
    [
        ("cosmology_constraints", ["desi", "cmb", "sne", "euclid", "hubble tension"]),
        ("gravitational_wave_constraints", ["kerr ringdown", "black-hole spectroscopy", "area theorem", "gr reduction limit"]),
        ("adversarial_consciousness_matrix", ["global workspace theory", "integrated information theory", "recurrent processing theory", "active inference", "orch-or", "higher-order theories"]),
    ],
)
def test_constraint_and_adversarial_matrices(module, required_terms, tmp_path):
    output = tmp_path / f"{module}.json"
    _run(module, output)
    text = output.read_text(encoding="utf-8").lower()
    assert all(term in text for term in required_terms)
    assert '"x"' not in text


def test_equation_registry_contains_eq_001_through_eq_010(tmp_path):
    output = tmp_path / "equations.json"
    _run("equation_registry", output)
    rows = json.loads(output.read_text(encoding="utf-8"))
    assert {row["equation_id"] for row in rows} == {f"EQ-{i:03d}" for i in range(1, 11)}


def test_falsifier_registry_contains_semantic_f1_through_f10():
    required_fields = {
        "id", "claim_affected", "affected_subsystems", "observable_required",
        "failure_condition", "claim_demotion_action",
        "next_experiment_or_simulation", "priority",
    }
    assert {row["id"] for row in FALSIFIERS} == {f"F{i}" for i in range(1, 11)}
    assert all(required_fields <= row.keys() for row in FALSIFIERS)
    assert all("x" not in row.values() for row in FALSIFIERS)
    assert "DESI" in next(row for row in FALSIFIERS if row["id"] == "F7")["observable_required"]
