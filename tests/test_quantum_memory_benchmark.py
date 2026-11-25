import inspect
import math
import unittest

import numpy as np

from physics.quantum_memory_benchmark import (
    ClassicalOUConfig,
    PseudomodeConfig,
    bb84_state,
    binary_classical_write_score,
    classical_ou_expected_score,
    classical_ou_trial_scores,
    classical_receiver,
    classical_bound_one_bit,
    quantum_receiver_probabilities,
    quantum_write_wait_read,
    thermal_occupation,
    _assert_density_physical,
)


class QuantumMemoryBenchmarkTests(unittest.TestCase):
    def test_identity_quantum_channel_is_unconditional_and_perfect(self):
        result = quantum_write_wait_read(
            PseudomodeConfig(
                coupling_rad_s=0.0,
                qubit_dephasing_rate_s=0.0,
                qubit_relaxation_rate_s=0.0,
                wait_s=0.0,
                fock_cutoff=8,
            )
        )
        self.assertEqual(result.input_count, 4)
        self.assertEqual(result.postselected_count, 0)
        self.assertAlmostEqual(result.mean_success, 1.0, places=12)
        self.assertTrue(all(abs(x - 1.0) < 1e-12 for x in result.success_by_input.values()))

    def test_quantum_zero_coupling_control_isolated_from_driven_bath(self):
        cfg = PseudomodeConfig(
            coupling_rad_s=0.0,
            mode_drive_rad_s=2.0e12,
            wait_s=2.0e-13,
            max_step_s=5.0e-15,
            fock_cutoff=8,
        )
        result = quantum_write_wait_read(cfg)
        self.assertAlmostEqual(result.mean_success, 1.0, delta=2e-7)
        self.assertEqual(result.postselected_count, 0)
        self.assertLess(result.max_trace_error, 1e-9)
        self.assertLess(result.max_hermiticity_error, 1e-9)
        self.assertGreaterEqual(result.minimum_eigenvalue, -1e-8)

    def test_optional_zero_temperature_relaxation_has_expected_population_decay(self):
        cfg = PseudomodeConfig(
            coupling_rad_s=0.0,
            qubit_relaxation_rate_s=1.0e12,
            wait_s=4.0e-13,
            max_step_s=5.0e-15,
            fock_cutoff=6,
        )
        result = quantum_write_wait_read(cfg)
        self.assertAlmostEqual(result.success_by_input["Z0"], math.exp(-0.4), delta=2e-6)
        self.assertAlmostEqual(result.success_by_input["Z1"], 1.0, delta=2e-6)

    def test_pure_dephasing_score_matches_declared_rate_convention(self):
        gamma_phi = 3.0e12
        wait_s = 2.0e-13
        result = quantum_write_wait_read(
            PseudomodeConfig(
                coupling_rad_s=0.0,
                mode_damping_rate_s=0.0,
                qubit_dephasing_rate_s=gamma_phi,
                wait_s=wait_s,
                max_step_s=5.0e-15,
                fock_cutoff=4,
            )
        )
        expected = (3.0 + math.exp(-gamma_phi * wait_s)) / 4.0
        self.assertAlmostEqual(result.mean_success, expected, delta=2e-7)

    def test_quantum_density_calculation_is_deterministic(self):
        cfg = PseudomodeConfig(
            coupling_rad_s=5.0e11,
            mode_damping_rate_s=2.0e12,
            wait_s=1.0e-13,
            max_step_s=5.0e-15,
            fock_cutoff=8,
        )
        self.assertEqual(quantum_write_wait_read(cfg), quantum_write_wait_read(cfg))

    def test_rk4_readout_converges_under_time_step_refinement(self):
        common = dict(
            coupling_rad_s=5.0e11,
            mode_damping_rate_s=2.0e12,
            qubit_dephasing_rate_s=3.0e12,
            wait_s=2.0e-13,
            fock_cutoff=8,
        )
        coarse = quantum_write_wait_read(PseudomodeConfig(max_step_s=1.0e-14, **common))
        fine = quantum_write_wait_read(PseudomodeConfig(max_step_s=5.0e-15, **common))
        finer = quantum_write_wait_read(PseudomodeConfig(max_step_s=2.5e-15, **common))
        self.assertLess(abs(coarse.mean_success - fine.mean_success), 1e-6)
        self.assertLess(abs(fine.mean_success - finer.mean_success), 1e-6)

    def test_classical_one_bit_breidbart_baseline_reaches_exact_bound_at_zero_wait(self):
        cfg = ClassicalOUConfig(wait_s=0.0, tau_s=1.0e-12, stationary_std=0.0)
        result = classical_ou_expected_score(cfg)
        bound = 0.5 + math.sqrt(2.0) / 4.0
        self.assertAlmostEqual(result.mean_success, bound, places=12)
        self.assertEqual(result.memory_bits, 1)
        self.assertEqual(result.trial_count, 0)
        self.assertEqual(classical_bound_one_bit, bound)
        self.assertEqual(result.postselected_count, 0)

    def test_binary_povm_bound_covers_biased_and_unsharp_effects(self):
        bound = 0.5 + math.sqrt(2.0) / 4.0
        for alpha in (0.2, 0.7, 1.0, 1.6, 1.9):
            radius = min(alpha, 2.0 - alpha)
            for direction in (
                np.array([1.0, 0.0, 0.0]),
                np.array([0.0, 0.0, 1.0]),
                np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0),
            ):
                score = binary_classical_write_score(alpha, radius * direction)
                self.assertLessEqual(score, bound + 1e-12)
        self.assertAlmostEqual(
            binary_classical_write_score(
                1.0, np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0)
            ),
            bound,
            places=12,
        )
        with self.assertRaises(ValueError):
            binary_classical_write_score(0.2, np.array([0.3, 0.0, 0.0]))

    def test_receiver_does_not_receive_label_or_random_seed(self):
        signature = inspect.signature(classical_receiver)
        self.assertEqual(tuple(signature.parameters), ("memory_value", "announced_basis"))
        self.assertEqual(tuple(inspect.signature(quantum_receiver_probabilities).parameters), ("qubit_density", "announced_basis"))
        self.assertEqual(classical_receiver(0.75, "Z"), 0)
        self.assertEqual(classical_receiver(-0.75, "X"), 1)

    def test_classical_ou_trials_are_seeded_and_all_trials_are_scored(self):
        cfg = ClassicalOUConfig(wait_s=2.0e-12, tau_s=1.0e-12, stationary_std=0.2)
        a = classical_ou_trial_scores(cfg, n_trials=20000, seed=17)
        b = classical_ou_trial_scores(cfg, n_trials=20000, seed=17)
        self.assertEqual(a, b)
        self.assertEqual(a.trial_count, 20000)
        self.assertEqual(a.input_count, 4)
        self.assertEqual(a.postselected_count, 0)
        self.assertTrue(0.5 <= a.mean_success <= 1.0)
        self.assertGreater(a.standard_error, 0.0)
        exact = classical_ou_expected_score(cfg)
        self.assertLessEqual(abs(a.mean_success - exact.mean_success), 5.0 * a.standard_error)

    def test_thermal_occupation_matches_bose_factor(self):
        omega = math.log(1.5) * 1.380649e-23 * 310.0 / 1.054571817e-34
        self.assertAlmostEqual(thermal_occupation(omega, 310.0), 2.0, places=10)

    def test_pseudomode_open_channel_preserves_density_invariants(self):
        cfg = PseudomodeConfig(
            coupling_rad_s=1.0e12,
            mode_damping_rate_s=2.0e12,
            wait_s=2.0e-13,
            max_step_s=4.0e-15,
            fock_cutoff=8,
        )
        result = quantum_write_wait_read(cfg)
        self.assertEqual(result.input_count, 4)
        self.assertEqual(result.postselected_count, 0)
        self.assertLess(result.max_trace_error, 1e-8)
        self.assertLess(result.max_hermiticity_error, 1e-8)
        self.assertGreaterEqual(result.minimum_eigenvalue, -1e-7)
        self.assertTrue(np.isfinite(result.mean_success))
        self.assertGreaterEqual(result.mean_success, 0.5)
        self.assertLessEqual(result.mean_success, 1.0)

    def test_open_quantum_memory_exceeds_one_bit_classical_bound_in_selected_regime(self):
        cfg = PseudomodeConfig(
            coupling_rad_s=5.0e11,
            mode_damping_rate_s=2.0e12,
            qubit_dephasing_rate_s=3.0e12,
            wait_s=2.0e-13,
            max_step_s=5.0e-15,
            fock_cutoff=10,
        )
        result = quantum_write_wait_read(cfg)
        self.assertGreater(result.mean_success, classical_bound_one_bit + 0.02)
        self.assertEqual(result.postselected_count, 0)

    def test_fock_cutoff_converges_with_populated_thermal_levels(self):
        common = dict(
            coupling_rad_s=5.0e11,
            mode_damping_rate_s=2.0e12,
            wait_s=1.0e-13,
            max_step_s=5.0e-15,
            mode_drive_rad_s=0.0,
        )
        low = quantum_write_wait_read(PseudomodeConfig(fock_cutoff=10, **common))
        high = quantum_write_wait_read(PseudomodeConfig(fock_cutoff=16, **common))
        self.assertGreater(low.thermal_occupation, 1.0)
        self.assertGreater(low.mode_population_n_ge_4, 0.1)
        self.assertGreater(high.mode_population_n_ge_4, 0.1)
        self.assertLess(abs(low.mode_population_n_ge_4 - high.mode_population_n_ge_4), 0.03)
        self.assertLess(abs(low.mean_success - high.mean_success), 0.02)
        self.assertLess(high.mode_edge_population, 0.02)

    def test_driven_fock_cutoff_converges_and_populates_upper_levels(self):
        common = dict(
            coupling_rad_s=3.0e11,
            mode_damping_rate_s=2.0e12,
            wait_s=2.0e-13,
            max_step_s=5.0e-15,
            mode_drive_rad_s=6.0e11,
        )
        low = quantum_write_wait_read(PseudomodeConfig(fock_cutoff=10, **common))
        high = quantum_write_wait_read(PseudomodeConfig(fock_cutoff=16, **common))
        self.assertGreater(high.mode_population_n_ge_4, 0.1)
        self.assertLess(abs(low.mode_population_n_ge_4 - high.mode_population_n_ge_4), 0.03)
        self.assertLess(abs(low.mean_success - high.mean_success), 0.02)
        self.assertLess(high.mode_edge_population, 0.02)

    def test_integration_resources_have_hard_bounds(self):
        with self.assertRaises(ValueError):
            PseudomodeConfig(fock_cutoff=33)
        with self.assertRaises(ValueError):
            PseudomodeConfig(max_steps=20_001)
        with self.assertRaises(ValueError):
            PseudomodeConfig(
                fock_cutoff=32,
                wait_s=1.0e-7,
                max_step_s=1.0e-9,
            )

    def test_nonphysical_density_is_rejected_without_clipping(self):
        invalid = np.array([[1.1, 0.0], [0.0, -0.1]], dtype=complex)
        with self.assertRaises(ArithmeticError):
            _assert_density_physical(invalid)

    def test_bb84_input_states_are_normalized_and_nonorthogonal_across_bases(self):
        states = [bb84_state(label) for label in ("Z0", "Z1", "X+", "X-")]
        for rho in states:
            self.assertAlmostEqual(float(np.trace(rho).real), 1.0, places=12)
            self.assertLess(np.max(np.abs(rho - rho.conj().T)), 1e-12)
        self.assertAlmostEqual(float(np.trace(states[0] @ states[2]).real), 0.5, places=12)


if __name__ == "__main__":
    unittest.main()
