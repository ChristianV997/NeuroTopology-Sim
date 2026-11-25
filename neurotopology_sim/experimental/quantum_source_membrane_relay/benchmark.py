"""Four-arm synthetic benchmark: quantum / classical / no-source / no-coupling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional

import numpy as np

from .membrane import FixedFHNCalibration, integrate_fhn_fixed_calibration
from .relay import RelayConfig, classical_matched_flux, event_rate_to_current_offset
from .source import QuantumSourceConfig, evolve_sink_source


class ArmName(str, Enum):
    QUANTUM_COUPLED = "quantum_coupled"
    CLASSICAL_MATCHED = "classical_matched"
    NO_SOURCE = "no_source"
    NO_COUPLING = "no_coupling"


@dataclass(frozen=True)
class BenchmarkConfig:
    source: QuantumSourceConfig = QuantumSourceConfig()
    relay: RelayConfig = RelayConfig()
    membrane: FixedFHNCalibration = FixedFHNCalibration()
    seed: int = 0  # reserved for future stochastic arms; deterministic RK4 today


@dataclass(frozen=True)
class BenchmarkResult:
    arms: Dict[str, Dict[str, Any]]
    summary: Dict[str, Any]


def _arm_payload(
    name: ArmName,
    membrane: Mapping[str, Any],
    *,
    yield_y: float,
    flux_mean: float,
    notes: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "arm": name.value,
        "yield_dimensionless": float(yield_y),
        "flux_mean_s": float(flux_mean),
        "threshold_crossing_fraction": float(membrane["threshold_crossing_fraction"]),
        "voltage_mean_V": float(np.mean(membrane["voltage_V"])),
        "voltage_max_V": float(np.max(membrane["voltage_V"])),
        "finite": bool(membrane["finite"]),
        "notes": dict(notes),
    }


def run_benchmark(config: Optional[BenchmarkConfig] = None) -> BenchmarkResult:
    """Run all arms with one shared FHN calibration and one shared relay gain."""
    cfg = config or BenchmarkConfig()
    src = evolve_sink_source(cfg.source)
    # Build FHN time base once from calibration
    base = integrate_fhn_fixed_calibration(cfg.membrane, current_offset=None)
    fhn_times = base["times_s"]

    # Quantum-coupled
    q_offset = event_rate_to_current_offset(
        src.times_s, src.event_flux_s, fhn_times, cfg.relay
    )
    q_mem = integrate_fhn_fixed_calibration(cfg.membrane, current_offset=q_offset)

    # Classical matched: same Y and same support duration as quantum source window
    support = float(cfg.source.duration_s)
    c_flux = classical_matched_flux(src.yield_dimensionless, support, fhn_times)
    c_offset = cfg.relay.gain_s * c_flux
    c_offset = np.clip(c_offset, -cfg.relay.max_abs_offset, cfg.relay.max_abs_offset)
    c_mem = integrate_fhn_fixed_calibration(cfg.membrane, current_offset=c_offset)

    # No source
    z_mem = integrate_fhn_fixed_calibration(
        cfg.membrane, current_offset=np.zeros_like(fhn_times)
    )

    # No coupling: quantum yield computed but gain forced to 0
    nc_relay = RelayConfig(gain_s=0.0, max_abs_offset=cfg.relay.max_abs_offset)
    nc_offset = event_rate_to_current_offset(
        src.times_s, src.event_flux_s, fhn_times, nc_relay
    )
    nc_mem = integrate_fhn_fixed_calibration(cfg.membrane, current_offset=nc_offset)

    arms = {
        ArmName.QUANTUM_COUPLED.value: _arm_payload(
            ArmName.QUANTUM_COUPLED,
            q_mem,
            yield_y=src.yield_dimensionless,
            flux_mean=float(np.mean(src.event_flux_s)),
            notes={"gain_s": cfg.relay.gain_s, "offset_l2": float(np.linalg.norm(q_offset))},
        ),
        ArmName.CLASSICAL_MATCHED.value: _arm_payload(
            ArmName.CLASSICAL_MATCHED,
            c_mem,
            yield_y=src.yield_dimensionless,
            flux_mean=float(np.mean(c_flux)),
            notes={
                "gain_s": cfg.relay.gain_s,
                "matched": ["integrated_yield", "support_duration_s"],
                "support_duration_s": support,
                "offset_l2": float(np.linalg.norm(c_offset)),
            },
        ),
        ArmName.NO_SOURCE.value: _arm_payload(
            ArmName.NO_SOURCE,
            z_mem,
            yield_y=0.0,
            flux_mean=0.0,
            notes={"gain_s": cfg.relay.gain_s},
        ),
        ArmName.NO_COUPLING.value: _arm_payload(
            ArmName.NO_COUPLING,
            nc_mem,
            yield_y=src.yield_dimensionless,
            flux_mean=float(np.mean(src.event_flux_s)),
            notes={"gain_s": 0.0, "quantum_source_computed": True},
        ),
    }

    summary = {
        "schema": "neurotopology_sim.quantum_source_membrane_relay.benchmark.v1",
        "data_policy": "SYNTHETIC_MODEL_ONLY",
        "scientific_claim": False,
        "consciousness_claim": False,
        "biological_quantum_claim": False,
        "source_diagnostics": src.diagnostics,
        "shared_calibration": base["calibration"],
        "relay_gain_s": float(cfg.relay.gain_s),
        "yield_dimensionless": float(src.yield_dimensionless),
        "classical_yield_match_abs_err": abs(
            arms[ArmName.CLASSICAL_MATCHED.value]["yield_dimensionless"]
            - arms[ArmName.QUANTUM_COUPLED.value]["yield_dimensionless"]
        ),
        "no_coupling_matches_no_source_crossing": bool(
            np.isclose(
                arms[ArmName.NO_COUPLING.value]["threshold_crossing_fraction"],
                arms[ArmName.NO_SOURCE.value]["threshold_crossing_fraction"],
                rtol=0.0,
                atol=1e-12,
            )
        ),
        "disclaimer": (
            "Synthetic/model-only interface test. Not evidence for biological "
            "quantum function, consciousness, Orch OR, or clinical effect."
        ),
    }
    return BenchmarkResult(arms=arms, summary=summary)
