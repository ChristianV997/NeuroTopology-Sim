"""CLI and result-contract regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.su2_skyrme.cli import main
from experiments.su2_skyrme.result_contract import (
    ExperimentResultV1,
    quantity,
    unavailable_quantity,
    validate_result_dict,
)


CONFIG_DIR = Path(__file__).resolve().parents[3] / "experiments" / "su2_skyrme" / "configs"


def test_cli_validate_config(capsys):
    code = main(["validate-config", "--config", str(CONFIG_DIR / "smoke_relax.json")])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["experiment_id"] == "su2-skyrme-smoke-relax-001"


def test_cli_validate_config_invalid(tmp_path: Path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"experiment_id": "x", "mode": "nope"}), encoding="utf-8")
    code = main(["validate-config", "--config", str(bad)])
    assert code == 1
    assert "invalid config" in capsys.readouterr().err


def test_cli_probe_solver(capsys):
    code = main(["probe-solver", "--json"])
    assert code in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["module_path"] == "field_theory.su2"


def test_cli_run_allow_stub(tmp_path: Path, capsys):
    out = tmp_path / "result.json"
    code = main(
        [
            "run",
            "--config",
            str(CONFIG_DIR / "smoke_sweep.json"),
            "--output",
            str(out),
            "--allow-stub",
        ]
    )
    assert code == 0
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "nearest_neighbor_sweep"
    assert len(payload["points"]) == 4
    assert "wrote" in capsys.readouterr().out


def test_cli_validate_result(tmp_path: Path):
    result_path = tmp_path / "r.json"
    code = main(
        [
            "run",
            "--config",
            str(CONFIG_DIR / "smoke_relax.json"),
            "--output",
            str(result_path),
            "--allow-stub",
        ]
    )
    assert code == 0
    assert main(["validate-result", "--result", str(result_path)]) == 0


def test_validate_result_rejects_consciousness_claim():
    result = ExperimentResultV1(
        result_id="abc",
        experiment_id="e",
        mode="nearest_neighbor_relax",
        status="completed",
        config={},
        provenance={},
        discretization={},
        boundary_conditions={},
        initial_condition={},
        model_settings={},
        solver_settings={},
        diagnostics=[quantity("x", 1.0, evidence="computed")],
        claim_tags={
            "scientific_status": "NOT_ASSESSED",
            "convergence_claim": "NOT_ESTABLISHED",
            "evidence_class": "engineering_numerical_output",
            "consciousness_interpretation": "allowed",  # forbidden
            "clinical_interpretation": "forbidden",
        },
    )
    problems = validate_result_dict(result.to_dict())
    assert any("consciousness_interpretation" in p for p in problems)


def test_unavailable_quantity_semantics():
    q = unavailable_quantity("physical_energy_si", "not assessed")
    assert q.value is None
    assert q.availability == "unavailable"
    assert q.evidence == "unavailable"
