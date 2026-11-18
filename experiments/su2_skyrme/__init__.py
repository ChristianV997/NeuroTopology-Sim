"""Reproducible experiment and parameter-sweep layer for SU(2)/Skyrme solvers.

This package owns configuration, provenance, deterministic run/sweep orchestration,
and a compact result contract for visualization consumers. It does **not** implement
solver mathematics or visualization UI.

The live solver package ``field_theory.su2`` currently lives on draft PRs #466 / #468
and is not present on every base branch. Call sites go through
``experiments.su2_skyrme.adapter`` so missing solver APIs surface as explicit
``solver_unavailable`` status rather than duplicated math.
"""

from .adapter import SolverAvailability, probe_solver_availability
from .provenance import build_provenance, config_sha256
from .result_contract import ExperimentResultV1, QuantityRecord
from .runner import run_experiment, run_parameter_sweep
from .schema import ExperimentConfig, load_experiment_config, validate_experiment_config

__all__ = [
    "ExperimentConfig",
    "ExperimentResultV1",
    "QuantityRecord",
    "SolverAvailability",
    "build_provenance",
    "config_sha256",
    "load_experiment_config",
    "probe_solver_availability",
    "run_experiment",
    "run_parameter_sweep",
    "validate_experiment_config",
]

__version__ = "0.1.0"
