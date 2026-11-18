"""Deterministic replay, sweep, and provenance tests (stub backend)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.su2_skyrme.adapter import StubSolverBackend, probe_solver_availability
from experiments.su2_skyrme.provenance import config_sha256, detect_git_revision
from experiments.su2_skyrme.result_contract import validate_result_dict
from experiments.su2_skyrme.runner import iter_sweep_points, run_experiment, run_parameter_sweep
from experiments.su2_skyrme.schema import load_experiment_config, validate_experiment_config


CONFIG_DIR = Path(__file__).resolve().parents[3] / "experiments" / "su2_skyrme" / "configs"


def test_probe_solver_reports_status():
    availability = probe_solver_availability()
    assert availability.import_status in {"available", "unavailable"}
    assert availability.module_path == "field_theory.su2"
    payload = availability.to_dict()
    assert "dependency_blocker" in payload


def test_smoke_relax_deterministic_replay():
    from datetime import datetime, timezone

    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    backend = StubSolverBackend()
    fixed_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = run_experiment(
        config, backend=backend, allow_stub=True, created_at=fixed_ts
    )
    second = run_experiment(
        config, backend=backend, allow_stub=True, created_at=fixed_ts
    )
    assert first.status == second.status
    assert first.result_id == second.result_id
    assert first.to_json() == second.to_json()
    assert first.provenance["config_sha256"] == config_sha256(config)
    assert first.provenance["seed"] == 0
    problems = validate_result_dict(first.to_dict())
    assert problems == []


def test_smoke_sweep_point_count_and_order():
    config = load_experiment_config(CONFIG_DIR / "smoke_sweep.json")
    points = list(iter_sweep_points(config))
    assert len(points) == 4
    # Stable Cartesian order: max_iterations varies fastest among e × max_iterations
    assert points[0]["e"] == 1.0 and points[0]["max_iterations"] == 1
    assert points[1]["e"] == 1.0 and points[1]["max_iterations"] == 2
    result = run_parameter_sweep(config, backend=StubSolverBackend(), allow_stub=True)
    assert len(result.points) == 4
    assert [p["point_id"] for p in result.points] == [
        "point-0000",
        "point-0001",
        "point-0002",
        "point-0003",
    ]
    # Distinct stub energies across max_iterations axis
    energies = [
        p["diagnostics"]["final_energy_total"]["value"] for p in result.points
    ]
    assert energies[0] != energies[1]
    assert result.claim_tags["consciousness_interpretation"] == "forbidden"


def test_filter_supported_kwargs_drops_unknown():
    from experiments.su2_skyrme.adapter import filter_supported_kwargs

    def foundation_relax(*, f_pi: float, e: float, max_iterations: int = 2) -> None:
        return None

    kept = filter_supported_kwargs(
        foundation_relax,
        {
            "f_pi": 1.0,
            "e": 1.5,
            "max_iterations": 2,
            "stationarity_metric": "euclidean",
            "descent_metric": "euclidean",
        },
    )
    assert kept == {"f_pi": 1.0, "e": 1.5, "max_iterations": 2}


def test_relax_diagnostics_omit_missing_enriched_fields():
    from types import SimpleNamespace

    from experiments.su2_skyrme.adapter import _relax_diagnostics_from_result

    foundation = SimpleNamespace(
        energy_history=(1.0, 0.9),
        topological_charge_history=(0.1, 0.2),
        iterations=2,
        stationarity_status="not_established",
        minimum_certified=False,
    )
    diagnostics = _relax_diagnostics_from_result(foundation)
    assert diagnostics["final_energy_total"] == 0.9
    assert diagnostics["iterations"] == 2
    assert "raw_gradient_norm" not in diagnostics
    assert "cell_volume" not in diagnostics

    enriched = SimpleNamespace(
        **foundation.__dict__,
        raw_gradient_norm=1.0,
        continuum_l2_residual=0.5,
        active_l2_measure=8.0,
        active_l2_rms_residual=0.25,
        cell_volume=1.0,
        active_site_count=8,
    )
    rich = _relax_diagnostics_from_result(enriched)
    assert rich["raw_gradient_norm"] == 1.0
    assert rich["active_site_count"] == 8


def test_solver_unavailable_without_stub():
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    availability = probe_solver_availability()
    if availability.import_status == "available":
        pytest.skip("live solver present; unavailable path not exercised")
    result = run_experiment(config, allow_stub=False)
    assert result.status == "solver_unavailable"
    assert result.failure_message
    assert any(d.name == "solver_output" for d in result.diagnostics)


def test_lorentzian_stub_smoke():
    config = load_experiment_config(CONFIG_DIR / "smoke_lorentzian.json")
    result = run_experiment(config, backend=StubSolverBackend(), allow_stub=True)
    assert result.status == "completed"
    names = {d.name for d in result.diagnostics}
    assert "final_total_energy" in names
    assert "hyperbolicity_status" in names
    hyper = next(d for d in result.diagnostics if d.name == "hyperbolicity_status")
    assert hyper.value == "not_certified"
    assert hyper.evidence == "assumed"  # stub backend


def test_diagnostics_never_imply_consciousness():
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    result = run_experiment(config, backend=StubSolverBackend(), allow_stub=True)
    consciousness = next(d for d in result.diagnostics if d.name == "consciousness_metric")
    assert consciousness.value is None
    assert consciousness.availability == "unavailable"
    charge = next(
        d for d in result.diagnostics if d.name == "final_approximate_topological_charge"
    )
    assert "consciousness" in charge.notes.lower() or "not a consciousness" in charge.notes.lower()


def test_write_json_roundtrip(tmp_path: Path):
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    result = run_experiment(config, backend=StubSolverBackend(), allow_stub=True)
    path = result.write_json(tmp_path / "out.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert validate_result_dict(loaded) == []
    assert loaded["schema_version"] == "0.1.0"


def test_config_hash_changes_with_seed():
    raw = json.loads((CONFIG_DIR / "smoke_relax.json").read_text(encoding="utf-8"))
    a = validate_experiment_config(raw)
    raw["seed"] = 7
    b = validate_experiment_config(raw)
    assert config_sha256(a) != config_sha256(b)


def test_untracked_files_mark_git_dirty(tmp_path: Path):
    """git status --porcelain must treat untracked files as dirty."""
    import os
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"], cwd=repo
    )
    subprocess.check_call(["git", "config", "user.name", "test"], cwd=repo)
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "tracked.txt"], cwd=repo)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    subprocess.check_call(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        env=env,
    )
    clean = detect_git_revision(str(repo))
    assert clean["git_status"] == "ok"
    assert clean["git_dirty"] is False

    (repo / "untracked_only.txt").write_text("new\n", encoding="utf-8")
    dirty = detect_git_revision(str(repo))
    assert dirty["git_dirty"] is True


def test_result_emits_speculative_quantity():
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    result = run_experiment(config, backend=StubSolverBackend(), allow_stub=True)
    speculative = [d for d in result.diagnostics if d.evidence == "speculative"]
    assert speculative, "expected at least one speculative diagnostic"
    assert speculative[0].name == "continuum_energy_extrapolation"
    assert speculative[0].availability == "null"
