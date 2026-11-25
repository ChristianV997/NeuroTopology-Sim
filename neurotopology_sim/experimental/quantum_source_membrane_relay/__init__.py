"""Synthetic quantum-source → membrane relay (HOLD / MODEL-ONLY).

This package wires a minimal open-quantum event-flux (sink) observable to a
FitzHugh–Nagumo (FHN) current offset through a **fixed**, unit-explicit gain.
It is an engineering interface test, not evidence of biological quantum
function, consciousness, Orch OR, or clinical effect.

FHN audit (important)
---------------------
``sim.pitnn.hodgkin_huxley_ciss.simulate_fhn`` maps the dimensionless state
``v`` to volts by **per-trajectory** min–max normalisation. That independently
rescales each run and must not be used for cross-condition amplitude
comparisons. This package integrates FHN itself and applies a **single fixed
affine calibration** shared by all arms.
"""

from .benchmark import (
    ArmName,
    BenchmarkConfig,
    BenchmarkResult,
    run_benchmark,
)
from .membrane import FixedFHNCalibration, integrate_fhn_fixed_calibration
from .relay import RelayConfig, event_rate_to_current_offset
from .source import QuantumSourceConfig, QuantumSourceResult, evolve_sink_source

__all__ = [
    "ArmName",
    "BenchmarkConfig",
    "BenchmarkResult",
    "FixedFHNCalibration",
    "QuantumSourceConfig",
    "QuantumSourceResult",
    "RelayConfig",
    "event_rate_to_current_offset",
    "evolve_sink_source",
    "integrate_fhn_fixed_calibration",
    "run_benchmark",
]
