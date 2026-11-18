"""Smoke tests for the SU(2)/Skyrme experiment runner."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from experiments.su2_skyrme.adapter import probe_solver_capabilities
from experiments.su2_skyrme.provenance import config_hash
from experiments.su2_skyrme.result_contract import RESULT_SCHEMA_VERSION, validate_result_dict
from experiments.su2_skyrme.runner import run_experiment
from experiments.su2_skyrme.schema import load_config

_REPO = Path(__file__).resolve().parents[2]
_CONFIGS = _REPO / "experiments" / "su2_skyrme" / "configs"
_OUT = _REPO / "outputs" / "experiments" / "su2_skyrme"


@pytest.fixture(autouse=True)
def _clean_outputs():
    yield
    if _OUT.exists():
        shutil.rmtree(_OUT, ignore_errors=True)


def test_smoke_single_writes_contract_artifacts(tmp_path):
    config = load_config(_CONFIGS / "smoke_single.json")
    # Redirect outputs into tmp to keep repo tree clean during collection quirks.
    from experiments.su2_skyrme.schema import ExperimentConfig

    redirected = ExperimentConfig(
        experiment_id=config.experiment_id,
        mode=config.mode,
        seed=config.seed,
        discretization=config.discretization,
        boundary_conditions=config.boundary_conditions,
        initial_condition=config.initial_condition,
        model=config.model,
        solver=config.solver,
        grid=config.grid,
        output_root=str(tmp_path / "runs"),
        notes=config.notes,
    )
    result = run_experiment(redirected, repo_root=_REPO)
    payload = result.to_dict()
    validate_result_dict(payload)

    run_dir = Path(result.artifacts["run_dir"])
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "provenance.json").is_file()
    assert (run_dir / "config.canonical.json").is_file()
    assert (run_dir / "viz_handoff.json").is_file()

    disk = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert disk["schema_version"] == RESULT_SCHEMA_VERSION
    assert disk["consciousness_implication"] == "none"
    assert disk["consciousness_score"] is None
    assert disk["provenance"]["seed"] == 42
    assert disk["provenance"]["config_hash"] == config_hash(redirected)
    assert "discretization" in disk["provenance"]
    assert "boundary_conditions" in disk["provenance"]
    assert "initial_condition" in disk["provenance"]
    assert isinstance(disk["diagnostics"], dict)
    assert disk["viz_handoff"]["owner"] == "visualization_contributor"

    caps = probe_solver_capabilities()
    if not caps.package_available:
        assert result.status == "completed_with_unavailable_solver"
        assert result.solver_available is False
        assert "energy_total" in result.missing_data
        assert disk["diagnostics"]["energy_total"]["availability"] == "unavailable"
    else:
        assert result.solver_backend_resolved in {
            "nearest_neighbor",
            "constrained_pair",
            "lorentzian",
            "unavailable_stub",
        }


def test_smoke_grid_expands_points(tmp_path):
    config = load_config(_CONFIGS / "smoke_grid.yaml")
    from experiments.su2_skyrme.schema import ExperimentConfig

    redirected = ExperimentConfig(
        experiment_id=config.experiment_id,
        mode=config.mode,
        seed=config.seed,
        discretization=config.discretization,
        boundary_conditions=config.boundary_conditions,
        initial_condition=config.initial_condition,
        model=config.model,
        solver=config.solver,
        grid=config.grid,
        output_root=str(tmp_path / "runs"),
        notes=config.notes,
    )
    result = run_experiment(redirected, repo_root=_REPO)
    assert len(result.points) == 4  # 2 f_pi × 2 e
    parent = Path(result.artifacts["run_dir"])
    assert (parent / "points_manifest.json").is_file()
    assert (parent / "points").is_dir()
    manifest = json.loads((parent / "points_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["points"]) == 4
