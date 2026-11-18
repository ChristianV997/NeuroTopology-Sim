"""SU(2)/Skyrme experiment runner, provenance, and result contracts.

This package owns reproducible experiment orchestration only. It does not
implement Skyrme energy, relaxation, Lorentzian evolution, or visualization.
Solver mathematics live in ``field_theory.su2`` (when present). When the
solver package is absent, the adapter records ``unavailable`` diagnostics
instead of inventing numerical values.
"""

from .schema import ExperimentConfig, load_config, validate_config
from .runner import run_experiment, run_grid, run_single

__all__ = [
    "ExperimentConfig",
    "load_config",
    "validate_config",
    "run_experiment",
    "run_single",
    "run_grid",
]

SCHEMA_VERSION = "su2_skyrme.experiment.config.v1"
RESULT_SCHEMA_VERSION = "su2_skyrme.experiment.result.v1"
ALGORITHM_ID = "su2-skyrme-experiment-runner-v1"
