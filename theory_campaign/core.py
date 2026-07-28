"""Dimensionless, matched-null evaluation for collective lattice modes."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

from physics.open_quantum import (
    LatticeConfig,
    LindbladLattice,
    MultiLatticeConfig,
    ThermalBathConfig,
    coupled_lattice,
    solve_gap,
)


@dataclass(frozen=True)
class CampaignConfig:
    """Physical parameters for one matched disorder family."""

    spacing_nm: float = 6.0
    correlation_length_nm: float = 8.0
    disorder_sigma_nm: float = 0.15
    collective_rate_s: float = 1e8
    local_radiative_rate_s: float = 1e8
    dephasing_rate_s: float = 1e8
    thermal_relaxation_s: float = 1e9
    temperature_K: float = 310.0
    transition_energy_eV: float = 4.43
    dielectric_constant: float = 7.0
    cutoff_nm: float = 30.0
    n_layers: int = 1
    disorder_seed: int = 0
    dense_max_dimension: int = 32
    krylov_k: int = 6
    maxiter: int = 2000

    def validate(self) -> None:
        positive = {
            "spacing_nm": self.spacing_nm,
            "correlation_length_nm": self.correlation_length_nm,
            "local_radiative_rate_s": self.local_radiative_rate_s,
            "temperature_K": self.temperature_K,
            "transition_energy_eV": self.transition_energy_eV,
            "dielectric_constant": self.dielectric_constant,
            "cutoff_nm": self.cutoff_nm,
        }
        if any(not np.isfinite(value) or value <= 0 for value in positive.values()):
            raise ValueError("positive campaign parameters must be finite")
        if any(not np.isfinite(value) or value < 0 for value in (self.disorder_sigma_nm, self.collective_rate_s, self.dephasing_rate_s, self.thermal_relaxation_s)):
            raise ValueError("rates and disorder must be finite and non-negative")
        if self.n_layers < 1 or self.dense_max_dimension < 2 or self.krylov_k < 2 or self.maxiter < 1:
            raise ValueError("solver dimensions must be positive")


def dimensionless_groups(config: CampaignConfig, coherent_coupling_s: float = 0.0) -> dict[str, float]:
    """Return the ratios used to compare regimes across dimensional scales."""
    config.validate()
    gamma = config.local_radiative_rate_s + config.dephasing_rate_s + config.thermal_relaxation_s
    return {
        "kappa_collective_to_local": config.collective_rate_s / config.local_radiative_rate_s,
        "rho_spacing_to_correlation": config.spacing_nm / config.correlation_length_nm,
        "delta_disorder_to_spacing": config.disorder_sigma_nm / config.spacing_nm,
        "chi_coherent_to_total_decay": coherent_coupling_s / max(gamma, np.finfo(float).tiny),
        "theta_transition_to_thermal": config.transition_energy_eV * 1.602176634e-19 / (1.380649e-23 * config.temperature_K),
    }


def _model(config: CampaignConfig, collective_rate_s: float | None = None, correlation_length_nm: float | None = None) -> LindbladLattice:
    bath = ThermalBathConfig.from_temperature(
        config.temperature_K,
        config.transition_energy_eV,
        thermal_relaxation_s=config.thermal_relaxation_s,
        dephasing_rate_s=config.dephasing_rate_s,
        radiative_rate_s=config.local_radiative_rate_s,
    )
    bath = replace(
        bath,
        collective_radiative_rate_s=config.collective_rate_s if collective_rate_s is None else collective_rate_s,
        collective_correlation_length_m=(config.correlation_length_nm if correlation_length_nm is None else correlation_length_nm) * 1e-9,
    )
    lattice = LatticeConfig(
        n_layers=config.n_layers,
        interaction_cutoff_m=config.cutoff_nm * 1e-9,
        dielectric_constant=config.dielectric_constant,
        transition_energy_eV=config.transition_energy_eV,
        bath=bath,
    )
    pristine = coupled_lattice(lattice, MultiLatticeConfig(config.spacing_nm * 1e-9))
    rng = np.random.default_rng(config.disorder_seed)
    positions = pristine.positions + rng.normal(0.0, config.disorder_sigma_nm * 1e-9, pristine.positions.shape)
    return LindbladLattice(positions, pristine.dipoles, lattice)


def _record(config: CampaignConfig, model: LindbladLattice, result: Any, null_name: str) -> dict[str, Any]:
    coherent = float(np.max(np.abs(model.hamiltonian[1:, 1:]))) / 1.054571817e-34
    groups = dimensionless_groups(config, coherent)
    return {
        "null": null_name,
        "configuration": {key: getattr(config, key) for key in config.__dataclass_fields__},
        "dimensionless": groups,
        "dimension": model.dimension,
        "solver": {
            "method": result.method,
            "converged": bool(result.converged),
            "iteration_count": int(result.iteration_count),
        },
        "observables": {
            "liouvillian_gap_s": float(result.gap_s),
            "subradiant_lifetime_s": None if not np.isfinite(result.tau_subradiant_s) else float(result.tau_subradiant_s),
            "superradiant_lifetime_s": None if not np.isfinite(result.tau_superradiant_s) else float(result.tau_superradiant_s),
            "trace_preservation_residual_s": float(result.trace_preservation_residual_s),
            "hermiticity_residual": float(result.hermiticity_residual),
        },
    }


def evaluate_lattice_point(config: CampaignConfig) -> dict[str, Any]:
    """Evaluate candidate plus matched independent/correlation nulls."""
    config.validate()
    records: list[dict[str, Any]] = []
    nulls = (
        ("candidate", config.collective_rate_s, config.correlation_length_nm),
        ("independent_bath", 0.0, config.correlation_length_nm),
        ("short_correlation_null", config.collective_rate_s, min(config.spacing_nm / 100.0, config.correlation_length_nm)),
    )
    for name, rate, correlation in nulls:
        model = _model(config, rate, correlation)
        result = solve_gap(model, dense_max_dimension=config.dense_max_dimension, k=config.krylov_k, maxiter=config.maxiter)
        records.append(_record(config, model, result, name))
    by_name = {record["null"]: record for record in records}
    candidate_tau = by_name["candidate"]["observables"]["subradiant_lifetime_s"]
    null_tau = by_name["independent_bath"]["observables"]["subradiant_lifetime_s"]
    contrast = None if candidate_tau is None or null_tau is None or candidate_tau <= 0 or null_tau <= 0 else float(np.log(candidate_tau / null_tau))
    return {
        "schema": "NeuroTopologySim.TheoryLatticePoint.v1",
        "records": records,
        "primary_contrast": {"definition": "log(candidate_subradiant_lifetime / independent_bath_lifetime)", "value": contrast},
    }


def exact_sign_flip_pvalue(values: np.ndarray) -> float:
    """Two-sided exact paired sign-flip p-value for small disorder cohorts."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or values.size < 2 or not np.all(np.isfinite(values)):
        raise ValueError("values must be a finite one-dimensional vector with at least two entries")
    observed = abs(float(np.mean(values)))
    null = [abs(float(np.mean(values * signs))) for signs in itertools.product((-1.0, 1.0), repeat=values.size) for signs in [np.asarray(signs)]]
    return float(np.mean(np.asarray(null) >= observed - 1e-15))


def stable_json(payload: dict[str, Any]) -> str:
    """Serialize campaign payloads without NaN/Infinity values."""
    def encode(value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            result = float(value)
            if not np.isfinite(result):
                raise ValueError("campaign payload contains a non-finite float")
            return result
        raise TypeError(f"unsupported campaign value: {type(value).__name__}")

    return json.dumps(payload, sort_keys=True, indent=2, allow_nan=False, default=encode) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
