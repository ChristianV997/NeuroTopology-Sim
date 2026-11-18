"""Replay / determinism tests for the SU(2)/Skyrme experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.su2_skyrme.provenance import config_hash, run_id_for
from experiments.su2_skyrme.runner import run_experiment
from experiments.su2_skyrme.schema import ExperimentConfig, load_config

_REPO = Path(__file__).resolve().parents[2]
_CONFIGS = _REPO / "experiments" / "su2_skyrme" / "configs"


def _redirect(config, output_root: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=config.experiment_id,
        mode=config.mode,
        seed=config.seed,
        discretization=config.discretization,
        boundary_conditions=config.boundary_conditions,
        initial_condition=config.initial_condition,
        model=config.model,
        solver=config.solver,
        grid=config.grid,
        output_root=output_root,
        notes=config.notes,
    )


def test_identical_configs_share_config_hash_and_run_id(tmp_path):
    base = load_config(_CONFIGS / "smoke_single.json")
    a = _redirect(base, str(tmp_path / "a"))
    b = _redirect(base, str(tmp_path / "b"))
    # output_root differs, but canonical hash excludes only notes — wait:
    # canonical_dict currently includes output_root. For replay identity across
    # redirected temp dirs we compare hashes of configs that share output_root.
    shared_root = str(tmp_path / "shared")
    a = _redirect(base, shared_root)
    b = _redirect(base, shared_root)
    assert config_hash(a) == config_hash(b)
    assert run_id_for(a) == run_id_for(b)


def test_replay_produces_identical_status_and_missing_data(tmp_path):
    base = load_config(_CONFIGS / "smoke_single.json")
    first = run_experiment(_redirect(base, str(tmp_path / "r1")), repo_root=_REPO)
    second = run_experiment(_redirect(base, str(tmp_path / "r2")), repo_root=_REPO)

    assert first.status == second.status
    assert first.solver_backend_resolved == second.solver_backend_resolved
    assert first.missing_data == second.missing_data
    assert first.diagnostics.keys() == second.diagnostics.keys()

    # Config hashes match when output roots match.
    shared = str(tmp_path / "shared")
    c1 = _redirect(base, shared)
    c2 = _redirect(base, shared)
    assert config_hash(c1) == config_hash(c2)

    p1 = json.loads(Path(first.artifacts["result_json"]).read_text(encoding="utf-8"))
    p2 = json.loads(Path(second.artifacts["result_json"]).read_text(encoding="utf-8"))
    assert p1["diagnostics"]["energy_total"]["availability"] == p2["diagnostics"]["energy_total"]["availability"]
    assert p1["consciousness_implication"] == p2["consciousness_implication"] == "none"


def test_seed_change_changes_run_id(tmp_path):
    base = load_config(_CONFIGS / "smoke_single.json")
    a = _redirect(base, str(tmp_path / "shared"))
    b = ExperimentConfig(
        experiment_id=a.experiment_id,
        mode=a.mode,
        seed=a.seed + 1,
        discretization=a.discretization,
        boundary_conditions=a.boundary_conditions,
        initial_condition=a.initial_condition,
        model=a.model,
        solver=a.solver,
        grid=a.grid,
        output_root=a.output_root,
        notes=a.notes,
    )
    assert run_id_for(a) != run_id_for(b)
