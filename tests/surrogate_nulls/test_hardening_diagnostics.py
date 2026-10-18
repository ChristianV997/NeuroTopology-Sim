"""Hardening checks: common-phase control, relative-phase diagnostics, zero-lag realisation
property, degrees of freedom, eigenvalue reporting, conjugate symmetry, and RNG streams.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.
These are engineering checks on the surrogate constructions, not evidence about any brain signal.
"""
from __future__ import annotations

import cmath
import math
import random
import unittest

from tools.surrogate_nulls import csd as C
from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp

TWO_PI = 2.0 * math.pi


def _independent(n, d, seed):
    rng = random.Random(seed)
    return [[rng.gauss(0.0, 1.0) for _ in range(n)] for _ in range(d)]


def _wrap(angle):
    return (angle + math.pi) % TWO_PI - math.pi


class CommonPhaseControlTests(unittest.TestCase):
    """Common phase is a control: it multiplies every channel at a bin by the same phasor."""

    def setUp(self):
        self.n = 32
        self.x = _independent(self.n, 3, 5)
        self.original = [sp.rfft(c) for c in self.x]

    def test_same_frequency_phase_differences_are_unchanged_for_every_bin_and_seed(self):
        for seed in range(6):
            signals, _ = N.common_phase_prichard_theiler(self.x, seed)
            measured = [sp.rfft(s) for s in signals]
            for k in sp.randomized_bins(self.n):
                for i in range(3):
                    for j in range(i + 1, 3):
                        before = self.original[i][k] * self.original[j][k].conjugate()
                        after = measured[i][k] * measured[j][k].conjugate()
                        self.assertLess(abs(before - after), 1e-9 * max(1.0, abs(before)),
                                        msg=f"seed {seed} bin {k} pair {(i, j)}")

    def test_every_channel_is_rotated_by_the_same_phase_at_each_bin(self):
        signals, _ = N.common_phase_prichard_theiler(self.x, 2)
        measured = [sp.rfft(s) for s in signals]
        for k in sp.randomized_bins(self.n):
            shifts = [cmath.phase(measured[c][k] / self.original[c][k]) for c in range(3)]
            for c in range(1, 3):
                self.assertLess(abs(_wrap(shifts[c] - shifts[0])), 1e-9, msg=f"bin {k} channel {c}")

    def test_control_is_labelled_and_not_a_winding_null(self):
        contract = N.CONTRACTS["common_phase_prichard_theiler"]
        self.assertIn("CONTROL_DIAGNOSTIC_ONLY", contract["role"])
        self.assertIn("NOT a null for narrowband spatial winding", contract["intended_use"])
        _, report = N.common_phase_prichard_theiler(self.x, 0)
        self.assertEqual(report.status["role"], "CONTROL_DIAGNOSTIC_ONLY")

    def test_common_phase_leaves_the_relative_phase_spread_at_zero(self):
        result = C.relative_phase_spread(self.x, N.common_phase_prichard_theiler, range(20), 3)
        self.assertFalse(result["varies"])
        self.assertLess(result["max_spread"], C.VARIATION_TOL)
        for pair, stats in result["pairs"].items():
            self.assertLess(stats["max_deviation_from_original"], 1e-9, msg=str(pair))


class RelativePhaseDiagnosticTests(unittest.TestCase):
    def test_cholesky_null_varies_relative_phases_on_independent_channels(self):
        x = _independent(32, 3, 5)
        result = C.relative_phase_spread(x, N.cholesky_gaussian_csd, range(20), 3)
        self.assertTrue(result["varies"])
        self.assertGreater(result["max_spread"], 0.1)

    def test_spread_report_covers_every_pair(self):
        x = _independent(32, 3, 5)
        result = C.relative_phase_spread(x, N.cholesky_gaussian_csd, range(4), 3)
        self.assertEqual(set(result["pairs"]), {(0, 1), (0, 2), (1, 2)})

    def test_empty_seed_set_is_rejected(self):
        with self.assertRaises(sp.SurrogateInputError):
            C.relative_phase_spread(_independent(16, 2, 1), N.cholesky_gaussian_csd, [], 1)


class ZeroLagRealisationTests(unittest.TestCase):
    def test_every_zero_lag_realisation_has_relative_phases_at_zero_or_pi(self):
        x = _independent(32, 3, 8)
        for seed in range(6):
            signals, _ = N.zero_lag_real_part_gaussian(x, seed, estimator="multitaper", n_tapers=5)
            self.assertLess(C.zero_or_pi_distance(signals), 1e-12, msg=f"seed {seed}")

    def test_cholesky_realisations_are_not_constrained_to_zero_or_pi(self):
        x = _independent(32, 3, 8)
        signals, _ = N.cholesky_gaussian_csd(x, 1)
        self.assertGreater(C.zero_or_pi_distance(signals), 0.1)

    def test_report_states_the_realisation_property_and_the_limits(self):
        x = _independent(32, 3, 8)
        _, report = N.zero_lag_real_part_gaussian(x, 0)
        self.assertEqual(report.status["realization_relative_phase"], "EXACT_0_OR_PI_EACH_REALISATION_BY_CONSTRUCTION")
        self.assertLess(report.max_relative_phase_distance_from_zero_or_pi, 1e-12)
        contract = N.CONTRACTS["zero_lag_real_part_gaussian"]
        self.assertIn("EVERY realisation", contract["preserved"])
        self.assertIn("not a volume-conduction detector", contract["assumptions"])


class DegreesOfFreedomTests(unittest.TestCase):
    def setUp(self):
        self.x = _independent(32, 2, 3)
        self.bins = sp.n_freq(32)

    def test_multitaper_dof_is_two_per_taper_at_every_bin(self):
        _, info = C.estimate_csd(self.x, "multitaper", n_tapers=4)
        self.assertEqual(info["dof_per_bin"], tuple(8 for _ in range(self.bins)))

    def test_boxcar_dof_counts_the_averaged_bins_with_edge_truncation(self):
        _, info = C.estimate_csd(self.x, "periodogram_boxcar", smoothing_halfwidth=1)
        dof = info["dof_per_bin"]
        self.assertEqual(dof[0], 4)          # bins {0, 1}
        self.assertEqual(dof[5], 6)          # bins {4, 5, 6}
        self.assertEqual(dof[-1], 4)         # bins {last-1, last}

    def test_single_periodogram_dof_is_two(self):
        _, info = C.estimate_csd(self.x, "single_periodogram")
        self.assertEqual(set(info["dof_per_bin"]), {2})

    def test_null_report_carries_the_dof_and_does_not_claim_full_rank(self):
        _, report = N.cholesky_gaussian_csd(self.x, 0, estimator="multitaper", n_tapers=4)
        self.assertEqual(report.estimator_dof_per_bin[0], 8)
        self.assertEqual(report.rank_status, N.RANK_STATUS)
        self.assertIn("NOT_ASSUMED_FULL", report.rank_status)
        self.assertEqual(report.status["rank"], N.RANK_STATUS)


class EigenvalueReportingTests(unittest.TestCase):
    def test_absolute_minimum_eigenvalue_is_reported_and_not_materially_negative(self):
        x = _independent(32, 3, 9)
        _, report = N.cholesky_gaussian_csd(x, 2)
        self.assertEqual(len(report.min_eig_abs_per_bin), sp.n_freq(32))
        scale = max(report.min_eig_abs_per_bin) or 1.0
        for value in report.min_eig_abs_per_bin:
            self.assertGreaterEqual(value, -1e-9 * scale)

    def test_single_periodogram_minimum_eigenvalue_is_numerically_zero(self):
        x = _independent(32, 2, 9)
        _, report = N.cholesky_gaussian_csd(x, 2, estimator="single_periodogram")
        self.assertTrue(all(abs(v) < 1e-9 * max(report.min_eig_abs_per_bin + (1.0,))
                            for v in report.min_eig_abs_per_bin))


class ConjugateSymmetryTests(unittest.TestCase):
    """irfft must equal the inverse DFT of the explicitly Hermitian-extended spectrum."""

    def test_irfft_matches_the_full_hermitian_inverse_dft(self):
        rng = random.Random(4)
        for n in (6, 7, 8, 9):
            bins = sp.n_freq(n)
            half = [complex(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(bins)]
            half[0] = complex(half[0].real, 0.0)
            if n % 2 == 0:
                half[n // 2] = complex(half[n // 2].real, 0.0)
            full = [0j] * n
            for k in range(bins):
                full[k] = half[k]
            for k in range(1, n):
                if k >= bins:
                    full[k] = half[n - k].conjugate()
            expected = []
            for t in range(n):
                acc = sum(full[k] * cmath.exp(2j * math.pi * k * t / n) for k in range(n))
                expected.append(acc.real / n)
            got, _ = sp.irfft(half, n)
            self.assertLess(max(abs(a - b) for a, b in zip(got, expected)), 1e-12, msg=f"n={n}")


class RngStreamTests(unittest.TestCase):
    def test_same_seed_and_label_give_the_same_stream(self):
        a = [sp.rng_for(7, "cholesky|bin:3").random() for _ in range(5)]
        b = [sp.rng_for(7, "cholesky|bin:3").random() for _ in range(5)]
        self.assertEqual(a, b)

    def test_different_labels_give_independent_streams(self):
        a = [sp.rng_for(7, "cholesky|bin:3").random() for _ in range(5)]
        b = [sp.rng_for(7, "cholesky|bin:4").random() for _ in range(5)]
        self.assertNotEqual(a, b)

    def test_changing_one_bin_matrix_does_not_change_any_other_bins_draws(self):
        n = 16
        target = [[[complex(2.0, 0.0), complex(0.3, 0.1)], [complex(0.3, -0.1), complex(1.0, 0.0)]]
                  for _ in range(sp.n_freq(n))]
        base, _ = N.draw_from_csd(target, n, 5)
        alt = [[row[:] for row in m] for m in target]
        alt[5] = [[complex(3.0, 0.0), complex(0.2, 0.0)], [complex(0.2, 0.0), complex(1.0, 0.0)]]
        changed, _ = N.draw_from_csd(alt, n, 5)
        for c in range(2):
            for k in range(sp.n_freq(n)):
                if k != 5:
                    self.assertEqual(base[c][k], changed[c][k], msg=f"channel {c} bin {k}")
        self.assertNotEqual(base[0][5], changed[0][5])


if __name__ == "__main__":
    unittest.main()
