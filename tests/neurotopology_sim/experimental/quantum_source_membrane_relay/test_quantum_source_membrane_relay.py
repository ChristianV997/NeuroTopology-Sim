"""Unit tests for the synthetic quantum → membrane relay (unittest, NumPy only)."""

from __future__ import annotations

import unittest

import numpy as np

from neurotopology_sim.experimental.quantum_source_membrane_relay import (
    BenchmarkConfig,
    FixedFHNCalibration,
    QuantumSourceConfig,
    RelayConfig,
    evolve_sink_source,
    integrate_fhn_fixed_calibration,
    run_benchmark,
)
from neurotopology_sim.experimental.quantum_source_membrane_relay.relay import (
    classical_matched_flux,
    event_rate_to_current_offset,
)


class TestQuantumSource(unittest.TestCase):
    def test_trace_and_positivity(self) -> None:
        result = evolve_sink_source(
            QuantumSourceConfig(n_steps=80, duration_s=4e-10, gamma_s=1e10)
        )
        self.assertTrue(np.isfinite(result.yield_dimensionless))
        self.assertGreaterEqual(result.yield_dimensionless, 0.0)
        self.assertLess(result.diagnostics["trace_max_abs_err"], 1e-8)
        self.assertGreaterEqual(result.diagnostics["min_eigenvalue_final"], -1e-8)
        self.assertLess(result.diagnostics["hermiticity_residual"], 1e-10)

    def test_reproducibility(self) -> None:
        cfg = QuantumSourceConfig(n_steps=60, duration_s=3e-10)
        a = evolve_sink_source(cfg)
        b = evolve_sink_source(cfg)
        self.assertEqual(a.yield_dimensionless, b.yield_dimensionless)
        np.testing.assert_allclose(a.event_flux_s, b.event_flux_s)

    def test_max_steps_bound(self) -> None:
        with self.assertRaises(ValueError):
            evolve_sink_source(QuantumSourceConfig(n_steps=100, max_steps=50))


class TestFixedFHNCalibration(unittest.TestCase):
    def test_fixed_affine_not_minmax(self) -> None:
        cal = FixedFHNCalibration(duration_s=0.005, dt_s=1e-5)
        zero = integrate_fhn_fixed_calibration(cal, current_offset=None)
        # Strong constant offset should change mean voltage under fixed affine map
        off = np.full(zero["times_s"].shape, 0.5)
        driven = integrate_fhn_fixed_calibration(cal, current_offset=off)
        self.assertTrue(zero["finite"] and driven["finite"])
        self.assertFalse(
            np.isclose(zero["voltage_mean_V"] if False else np.mean(zero["voltage_V"]),
                       np.mean(driven["voltage_V"]))
        )
        # Calibration dict identical object values
        self.assertEqual(
            zero["calibration"]["volts_per_dimensionless_v"],
            driven["calibration"]["volts_per_dimensionless_v"],
        )

    def test_timestep_sensitivity(self) -> None:
        coarse = FixedFHNCalibration(duration_s=0.01, dt_s=2e-5)
        fine = FixedFHNCalibration(duration_s=0.01, dt_s=1e-5)
        a = integrate_fhn_fixed_calibration(coarse)
        b = integrate_fhn_fixed_calibration(fine)
        # Same fixed calibration constants; crossing fractions should be close
        self.assertLess(
            abs(a["threshold_crossing_fraction"] - b["threshold_crossing_fraction"]),
            0.15,
        )


class TestRelayAndBenchmark(unittest.TestCase):
    def test_classical_yield_match(self) -> None:
        y = 0.4
        support = 5e-10
        ft = np.linspace(0.0, 0.02, 2001)
        flux = classical_matched_flux(y, support, ft)
        rate = y / support
        self.assertTrue(np.all(flux[ft <= support] == rate))
        self.assertTrue(np.all(flux[ft > support] == 0.0))

    def test_gain_units_and_clip(self) -> None:
        t = np.linspace(0.0, 1e-9, 50)
        phi = np.full_like(t, 1e15)
        ft = np.linspace(0.0, 0.01, 100)
        off = event_rate_to_current_offset(t, phi, ft, RelayConfig(gain_s=1.0, max_abs_offset=2.0))
        self.assertTrue(np.all(np.abs(off) <= 2.0 + 1e-15))

    def test_benchmark_controls(self) -> None:
        cfg = BenchmarkConfig(
            source=QuantumSourceConfig(n_steps=40, duration_s=2e-10, gamma_s=2e10),
            membrane=FixedFHNCalibration(duration_s=0.005, dt_s=2e-5),
            relay=RelayConfig(gain_s=1e-12),
        )
        result = run_benchmark(cfg)
        self.assertIn("quantum_coupled", result.arms)
        self.assertTrue(result.summary["no_coupling_matches_no_source_crossing"])
        self.assertEqual(result.summary["classical_yield_match_abs_err"], 0.0)
        self.assertFalse(result.summary["scientific_claim"])
        self.assertEqual(result.summary["data_policy"], "SYNTHETIC_MODEL_ONLY")
        for arm in result.arms.values():
            self.assertTrue(arm["finite"])
            self.assertGreaterEqual(arm["threshold_crossing_fraction"], 0.0)
            self.assertLessEqual(arm["threshold_crossing_fraction"], 1.0)

    def test_source_timestep_sensitivity_yield(self) -> None:
        coarse = evolve_sink_source(QuantumSourceConfig(n_steps=40, duration_s=4e-10))
        fine = evolve_sink_source(QuantumSourceConfig(n_steps=80, duration_s=4e-10))
        # Yields should agree relatively for refined RK4
        denom = max(abs(fine.yield_dimensionless), 1e-15)
        rel = abs(coarse.yield_dimensionless - fine.yield_dimensionless) / denom
        self.assertLess(rel, 0.05)


if __name__ == "__main__":
    unittest.main()
