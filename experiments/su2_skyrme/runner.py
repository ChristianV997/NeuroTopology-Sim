"""Experiment runner: single-run and parameter-grid orchestration.

Writes provenance + result contracts under ``output_root/<run_id>/``.
Does not implement solver mathematics or visualization.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from .adapter import run_adapter
from .provenance import build_provenance, canonical_json, config_hash
from .result_contract import (
    ALGORITHM_ID,
    RESULT_SCHEMA_VERSION,
    ExperimentResult,
    build_convergence_block,
    default_limitations,
    default_viz_handoff,
)
from .schema import ExperimentConfig, expand_grid_points, load_config, validate_config

PathLike = Union[str, Path]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(payload) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _run_dir(config: ExperimentConfig, run_id: str) -> Path:
    return Path(config.output_root) / run_id


def run_single(
    config: ExperimentConfig,
    *,
    repo_root: Optional[Path] = None,
) -> ExperimentResult:
    """Run one concrete experiment point and persist artifacts."""
    provenance = build_provenance(config, repo_root=repo_root)
    run_dir = _run_dir(config, provenance.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "config.canonical.json", config.canonical_dict())
    _write_json(run_dir / "provenance.json", provenance.to_dict())

    adapter_output = run_adapter(config)
    convergence = build_convergence_block(
        status=adapter_output.status,
        termination=adapter_output.termination,
        iterations=adapter_output.iterations,
        reason="adapter-reported convergence metadata",
    )
    result = ExperimentResult(
        schema_version=RESULT_SCHEMA_VERSION,
        algorithm_id=ALGORITHM_ID,
        run_id=provenance.run_id,
        experiment_id=config.experiment_id,
        status=adapter_output.status,
        provenance=provenance.to_dict(),
        config=config.to_dict(),
        solver_backend_requested=config.solver.backend,
        solver_backend_resolved=adapter_output.backend_resolved,
        solver_available=adapter_output.solver_available,
        convergence=convergence,
        diagnostics=adapter_output.diagnostics_dict(),
        missing_data=list(adapter_output.missing_data),
        failures=list(adapter_output.failures),
        points=[],
        artifacts={
            "result_json": str(run_dir / "result.json"),
            "provenance_json": str(run_dir / "provenance.json"),
            "config_canonical_json": str(run_dir / "config.canonical.json"),
            "run_dir": str(run_dir),
        },
        viz_handoff=default_viz_handoff(str(run_dir), status=adapter_output.status),
        limitations=default_limitations(solver_available=adapter_output.solver_available),
    )
    result_payload = result.to_dict()
    _write_json(run_dir / "result.json", result_payload)
    _write_json(run_dir / "viz_handoff.json", result.viz_handoff)
    _write_json(
        run_dir / "adapter_raw.json",
        {
            "backend_resolved": adapter_output.backend_resolved,
            "solver_available": adapter_output.solver_available,
            "status": adapter_output.status,
            "raw": adapter_output.raw,
            "epistemic_tag": "computed",
        },
    )
    return result


def run_grid(
    config: ExperimentConfig,
    *,
    repo_root: Optional[Path] = None,
) -> ExperimentResult:
    """Expand a parameter grid, run each point, and write a parent summary."""
    if config.mode != "grid":
        raise ValueError("run_grid requires config.mode == 'grid'")

    parent_provenance = build_provenance(config, repo_root=repo_root)
    parent_dir = _run_dir(config, parent_provenance.run_id)
    parent_dir.mkdir(parents=True, exist_ok=True)
    _write_json(parent_dir / "config.canonical.json", config.canonical_dict())
    _write_json(parent_dir / "provenance.json", parent_provenance.to_dict())

    point_configs = expand_grid_points(config)
    point_summaries: list[dict[str, Any]] = []
    failures: list[str] = []
    missing: list[str] = []

    for point_config in point_configs:
        # Nest point outputs under the parent run directory for discoverability.
        nested = ExperimentConfig(
            experiment_id=point_config.experiment_id,
            mode="single",
            seed=point_config.seed,
            discretization=point_config.discretization,
            boundary_conditions=point_config.boundary_conditions,
            initial_condition=point_config.initial_condition,
            model=point_config.model,
            solver=point_config.solver,
            grid=point_config.grid,
            output_root=str(parent_dir / "points"),
            notes=point_config.notes,
            schema_version=point_config.schema_version,
            claim_scope=point_config.claim_scope,
        )
        point_result = run_single(nested, repo_root=repo_root)
        point_summaries.append(
            {
                "experiment_id": point_result.experiment_id,
                "run_id": point_result.run_id,
                "status": point_result.status,
                "config_hash": config_hash(nested),
                "solver_backend_resolved": point_result.solver_backend_resolved,
                "artifacts": point_result.artifacts,
                "model": nested.model.to_dict(),
                "solver": nested.solver.to_dict(),
            }
        )
        failures.extend(point_result.failures)
        for item in point_result.missing_data:
            if item not in missing:
                missing.append(item)

    any_solver = any(
        summary.get("status") not in {"completed_with_unavailable_solver"}
        and "unavailable" not in str(summary.get("solver_backend_resolved", ""))
        for summary in point_summaries
    )
    # Prefer honest parent status: if every point used the unavailable stub,
    # mirror that; otherwise mark completed with per-point statuses retained.
    if point_summaries and all(
        s["status"] == "completed_with_unavailable_solver" for s in point_summaries
    ):
        status = "completed_with_unavailable_solver"
        solver_available = False
        backend_resolved = "unavailable_stub"
    else:
        status = "completed"
        solver_available = any_solver
        backend_resolved = "grid"

    result = ExperimentResult(
        schema_version=RESULT_SCHEMA_VERSION,
        algorithm_id=ALGORITHM_ID,
        run_id=parent_provenance.run_id,
        experiment_id=config.experiment_id,
        status=status,
        provenance=parent_provenance.to_dict(),
        config=config.to_dict(),
        solver_backend_requested=config.solver.backend,
        solver_backend_resolved=backend_resolved,
        solver_available=solver_available,
        convergence=build_convergence_block(
            status=status,
            termination=None,
            iterations=None,
            reason="grid parent aggregates per-point convergence only",
        ),
        diagnostics={
            "grid_point_count": {
                "value": len(point_summaries),
                "availability": "available",
                "epistemic_tag": "computed",
                "units": "count",
                "note": "number of expanded grid points executed",
            },
            "energy_total": {
                "value": None,
                "availability": "unavailable",
                "epistemic_tag": "assumed",
                "units": "dimensionless_model_energy",
                "note": "parent grid result does not aggregate energies; see points/",
            },
        },
        missing_data=missing,
        failures=failures,
        points=point_summaries,
        artifacts={
            "result_json": str(parent_dir / "result.json"),
            "provenance_json": str(parent_dir / "provenance.json"),
            "config_canonical_json": str(parent_dir / "config.canonical.json"),
            "points_manifest_json": str(parent_dir / "points_manifest.json"),
            "run_dir": str(parent_dir),
        },
        viz_handoff=default_viz_handoff(str(parent_dir), status=status),
        limitations=default_limitations(solver_available=solver_available),
    )
    payload = result.to_dict()
    _write_json(parent_dir / "result.json", payload)
    _write_json(parent_dir / "points_manifest.json", {"points": point_summaries})
    _write_json(parent_dir / "viz_handoff.json", result.viz_handoff)
    return result


def run_experiment(
    config_or_path: ExperimentConfig | PathLike | dict[str, Any],
    *,
    repo_root: Optional[Path] = None,
) -> ExperimentResult:
    """Dispatch to single or grid runner from config object, dict, or path."""
    if isinstance(config_or_path, ExperimentConfig):
        config = config_or_path
    elif isinstance(config_or_path, dict):
        config = validate_config(config_or_path)
    else:
        config = load_config(config_or_path)

    if config.mode == "grid":
        return run_grid(config, repo_root=repo_root)
    return run_single(config, repo_root=repo_root)
