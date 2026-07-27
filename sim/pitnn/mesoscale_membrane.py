"""Statistical bridge from finite open-quantum decay metrics to FHN membrane noise.

This is a deliberately phenomenological mesoscale mapping.  It produces a
dimensionless current-variance term for sensitivity experiments; it does not
derive neuronal voltage noise from a microscopic quantum theory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import numpy as np

from .hodgkin_huxley_ciss import FHNConfig, simulate_fhn


@dataclass(frozen=True)
class MesoscaleConfig:
    """Mapping parameters; ``coupling`` converts s^-1 fluctuation rate to FHN current SD."""

    coupling: float = 1e-7
    seed: int = 20260726
    threshold_V: float = -0.020

    def __post_init__(self) -> None:
        if self.coupling < 0 or not np.isfinite(self.coupling) or not np.isfinite(self.threshold_V):
            raise ValueError("coupling and threshold_V must be finite; coupling must be non-negative")


def membrane_current_variance(
    decoherence_time_s: float,
    *,
    occupancy: float = 0.5,
    coupling: float = 1e-7,
) -> float:
    """Return an FHN-current variance proxy from a finite correlation time.

    ``decoherence_time_s`` is in seconds. The model uses a bounded Bernoulli
    occupancy factor and rate ``1/tau``; the returned value has FHN current
    units and is only meaningful relative to the selected FHN configuration.
    """
    if not np.isfinite(decoherence_time_s) or decoherence_time_s <= 0:
        raise ValueError("decoherence_time_s must be finite and positive")
    if not 0 <= occupancy <= 1 or coupling < 0 or not np.isfinite(coupling):
        raise ValueError("occupancy must be in [0,1] and coupling non-negative")
    return float((coupling ** 2) * occupancy * (1.0 - occupancy) / decoherence_time_s)


def quantum_metrics_to_variance(metrics: Mapping[str, float], config: MesoscaleConfig = MesoscaleConfig()) -> float:
    """Extract a conservative variance proxy from a gap-result-like mapping."""
    tau = metrics.get("tau_subradiant_s", metrics.get("decoherence_time_s"))
    if tau is None: raise ValueError("metrics must contain tau_subradiant_s or decoherence_time_s")
    return membrane_current_variance(float(tau), coupling=config.coupling)


def simulate_fluctuation_biased_fhn(
    variance: float,
    config: MesoscaleConfig = MesoscaleConfig(),
    fhn_config: FHNConfig = FHNConfig(),
) -> dict[str, np.ndarray | float]:
    """Inject zero-mean Gaussian current fluctuations into FHN integration.

    The returned ``threshold_crossing_fraction`` measures samples above the
    chosen voltage threshold and is a local simulation statistic, not a firing
    probability calibrated to biological neurons.
    """
    if variance < 0 or not np.isfinite(variance): raise ValueError("variance must be finite and non-negative")
    times, baseline_voltage, recovery = simulate_fhn(fhn_config)
    rng = np.random.default_rng(config.seed)
    # Linear response proxy: small current perturbations map to voltage scale.
    current_offset = rng.normal(0.0, np.sqrt(variance), size=baseline_voltage.size)
    _, voltage, perturbed_recovery = simulate_fhn(fhn_config, input_current_offset=current_offset)
    return {"times_s": times, "baseline_voltage_V": baseline_voltage, "voltage_V": voltage,
            "recovery": perturbed_recovery, "current_variance": float(variance), "current_offset": current_offset,
            "threshold_crossing_fraction": float(np.mean(voltage >= config.threshold_V))}
