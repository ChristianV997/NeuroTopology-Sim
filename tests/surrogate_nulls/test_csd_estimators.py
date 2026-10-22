"""CSD estimators, PSD diagnostics, the explicit-estimate path, and the zero-lag null.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.

Declared before measurement (not tuned to pass):
- ENSEMBLE_TOL = 0.15: relative Frobenius error, summed over bins, of the ensemble-mean raw
  periodogram against the estimate, over ENSEMBLE_SEEDS = 800 seeds, N = 32, d = 2.
- CONTROL_MIN = 0.5: an identity target must fail the same criterion.

The winding statistic is a toy for designed signals (``csd.phase_loop_winding``), not a
project metric. Whether a procedure varies it is reported, never assumed.
"""
from __future__ import annotations

import cmath
import math
import random
import unittest

from tools.surrogate_nulls import csd as C
from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp

ENSEMBLE_TOL = 0.15
ENSEMBLE_SEEDS = 800
CONTROL_MIN = 0.5


def _pair(n, seed=7):
    rng = random.Random(seed)
    x0 = [rng.gauss(0.0, 1.0) for _ in range(n)]
    x1 = [0.7 * a + 0.5 * rng.gauss(0.0, 1.0) for a in x0]
    return [x0, x1]


def _independent(n, d, seed):
    rng = random.Random(seed)
    return [[rng.gauss(0.0, 1.0) for _ in range(n)] for _ in range(d)]


def _designed_winding(n, k):
    thetas = (0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0)
    return [[math.cos(2.0 * math.pi * k * t / n + th) for t in range(n)] for th in thetas]


def _ensemble_mean(generator, x, n, seeds, **kwargs):
    d = len(x)
    bins = sp.n_freq(n)
    acc = [[[0j] * d for _ in range(d)] for _ in range(bins)]
    for seed in range(seeds):
        surrogate, _ = generator(x, seed, **kwargs)
        raw = sp.periodogram_csd([sp.rfft(s) for s in surrogate], n)
        for k in range(bins):
            for i in range(d):
                for j in range(d):
                    acc[k][i][j] += raw[k][i][j] / seeds
    return acc


class TaperAndEigenTests(unittest.TestCase):
    def test_sine_tapers_are_orthonormal(self):
        for n, k in ((8, 4), (32, 6), (7, 3), (1, 1)):
            taps = C.sine_tapers(n, k)
            err = max(abs(sum(taps[a][t] * taps[b][t] for t in range(n)) - (1.0 if a == b else 0.0))
                      for a in range(k) for b in range(k))
            self.assertLess(err, 1e-12, msg=f"n={n} k={k}")

    def test_taper_count_is_validated(self):
        with self.assertRaises(sp.SurrogateInputError):
            C.sine_tapers(8, 0)
        with self.assertRaises(sp.SurrogateInputError):
            C.sine_tapers(8, 9)

    def test_hermitian_eigenvalues_of_a_known_matrix(self):
        h = [[complex(2.0, 0.0), complex(1.0, 1.0)], [complex(1.0, -1.0), complex(2.0, 0.0)]]
        eigs = C.hermitian_eigenvalues(h)
        self.assertAlmostEqual(eigs[0], 2.0 + math.sqrt(2.0), places=12)
        self.assertAlmostEqual(eigs[1], 2.0 - math.sqrt(2.0), places=12)

    def test_hermitian_eigenvalues_preserve_the_trace(self):
        rng = random.Random(3)
        a = [[complex(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(3)] for _ in range(3)]
        h = [[sum(a[i][k] * a[j][k].conjugate() for k in range(3)) for j in range(3)] for i in range(3)]
        trace = sum(h[i][i].real for i in range(3))
        self.assertLess(abs(sum(C.hermitian_eigenvalues(h)) - trace), 1e-10)

    def test_participation_ratio_bounds(self):
        self.assertAlmostEqual(C.participation_ratio([1.0, 0.0, 0.0]), 1.0)
        self.assertAlmostEqual(C.participation_ratio([1.0, 1.0, 1.0]), 3.0)
        self.assertEqual(C.participation_ratio([]), 0.0)


class MatrixDiagnosticTests(unittest.TestCase):
    def test_materially_indefinite_matrix_is_rejected_with_a_clear_message(self):
        m = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(-0.5, 0.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError) as ctx:
            C.matrix_diagnostics(m)
        self.assertIn("materially indefinite", str(ctx.exception))

    def test_rounding_level_negative_eigenvalue_is_returned_not_raised(self):
        m = [[complex(1.0, 0.0), complex(1.0, 0.0)], [complex(1.0, 0.0), complex(1.0 - 1e-16, 0.0)]]
        rank, min_rel, cond, part = C.matrix_diagnostics(m)
        self.assertEqual(rank, 1)
        self.assertLess(-1e-10, min_rel)
        self.assertLessEqual(min_rel, 0.0 + 1e-15)

    def test_zero_trace_matrix_has_zero_rank(self):
        m = [[complex(0.0, 0.0)] * 2 for _ in range(2)]
        self.assertEqual(C.matrix_diagnostics(m), (0, 0.0, 1.0, 0.0))

    def test_rank_one_matrix_is_rank_one_at_every_scale(self):
        # Before the fix, the absolute floor in the Jacobi stop test reported rank 2 for s <= 1e-16.
        for s in (1.0, 1e-5, 1e-10, 1e-14, 1e-16, 1e-20, 1e-30, 1e10):
            m = [[complex(s), complex(s)], [complex(s), complex(s)]]
            rank, min_rel, cond, part = C.matrix_diagnostics(m)
            self.assertEqual(rank, 1, msg=f"scale {s}")
            self.assertLess(abs(min_rel), 1e-9, msg=f"scale {s}")
            self.assertEqual(cond, math.inf, msg=f"scale {s}")
            self.assertAlmostEqual(part, 1.0, places=9, msg=f"scale {s}")

    def test_eigenvalues_of_a_random_3x3_scale_exactly_with_the_matrix(self):
        # Scale-invariance check on a non-trivial matrix: eig(s M) = s eig(M) at tiny and huge scales.
        rng = random.Random(11)
        a = [[complex(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(3)] for _ in range(3)]
        base = [[sum(a[i][k] * a[j][k].conjugate() for k in range(3)) for j in range(3)] for i in range(3)]
        ref = C.hermitian_eigenvalues(base)
        for scale in (1e-20, 1e-8, 1e8):
            scaled = [[v * scale for v in row] for row in base]
            got = C.hermitian_eigenvalues(scaled)
            for g, r in zip(got, ref):
                self.assertLess(abs(g - r * scale), 1e-12 * scale * max(1.0, abs(ref[0])),
                                msg=f"scale {scale}")

    def test_full_rank_diagnostics_are_identical_across_scales(self):
        base = [[complex(2.0, 0.0), complex(1.0, 0.5)], [complex(1.0, -0.5), complex(2.0, 0.0)]]
        ref_rank, ref_min, ref_cond, ref_part = C.matrix_diagnostics(base)
        for scale in (1e-20, 1e-8, 1e8, 1e20):
            scaled = [[v * scale for v in row] for row in base]
            rank, min_rel, cond, part = C.matrix_diagnostics(scaled)
            self.assertEqual(rank, ref_rank, msg=f"scale {scale}")
            self.assertAlmostEqual(min_rel, ref_min, places=9, msg=f"scale {scale}")
            self.assertAlmostEqual(cond, ref_cond, places=6, msg=f"scale {scale}")
            self.assertAlmostEqual(part, ref_part, places=9, msg=f"scale {scale}")

    def test_near_rank_deficient_matrix_is_rank_one_at_every_scale(self):
        for s in (1.0, 1e-12, 1e-20):
            m = [[complex(s), complex(0.0)], [complex(0.0), complex(s * 1e-14)]]
            rank, _, cond, _ = C.matrix_diagnostics(m)
            self.assertEqual(rank, 1, msg=f"scale {s}")
            self.assertEqual(cond, math.inf, msg=f"scale {s}")

    def test_zero_trace_indefinite_matrix_is_rejected_by_diagnostics_and_draws(self):
        # Before the fix, diagnostics returned rank 0 here while the draw path rejected it.
        m = [[complex(1.0), complex(2.0)], [complex(2.0), complex(-1.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            C.matrix_diagnostics(m)
        with self.assertRaises(sp.NonPositiveDefiniteError):
            N.draw_from_csd([m], 1, 0)

    def test_negative_trace_matrix_is_rejected(self):
        m = [[complex(-1.0), complex(0.0)], [complex(0.0), complex(-2.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            C.matrix_diagnostics(m)

    def test_malformed_matrices_are_rejected_before_diagnosis(self):
        cases = {
            "empty": [],
            "non-square": [[complex(1.0), complex(0.0)]],
            "ragged": [[complex(1.0), complex(0.0)], [complex(0.0)]],
            "infinite entry": [[complex(float("inf")), complex(0.0)], [complex(0.0), complex(1.0)]],
            "nan entry": [[complex(float("nan")), complex(0.0)], [complex(0.0), complex(1.0)]],
            "non-Hermitian": [[complex(1.0), complex(0.5)], [complex(0.0), complex(1.0)]],
            "bool entry": [[True, 0.0], [0.0, 1.0]],
        }
        for name, m in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(sp.SurrogateInputError):
                    C.matrix_diagnostics(m)

    def test_non_hermitian_matrix_is_rejected_at_small_scale(self):
        # The asymmetry equals the entries themselves, so it is 100% relative. An absolute
        # floor in the Hermitian check used to accept this.
        s = 1e-20
        m = [[complex(s), complex(s, 0.5 * s)], [complex(s, 0.5 * s), complex(s)]]
        with self.assertRaises(sp.SurrogateInputError):
            C.matrix_diagnostics(m)
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([m], 1, 0)

    def test_all_zero_matrix_is_rank_zero_and_gives_zero_power(self):
        z = [[complex(0.0)] * 2 for _ in range(2)]
        self.assertEqual(C.matrix_diagnostics(z), (0, 0.0, 1.0, 0.0))
        spectra, info = N.draw_from_csd([z], 1, 0)
        self.assertEqual(info["zero_power"], [0])
        self.assertEqual(spectra[0][0], 0j)


class DrawScaleTests(unittest.TestCase):
    def test_real_coefficient_target_check_is_relative_at_small_scale(self):
        # n = 5 gives bins 0 (DC, fixed), 1 and 2 (randomised). DC imaginary parts are discarded
        # and reported by design, so the check that matters is on the randomised bins.
        s = 1e-20
        n = 5
        m = [[complex(s), complex(0.0, 0.5 * s)], [complex(0.0, -0.5 * s), complex(s)]]
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([m] * sp.n_freq(n), n, 0, real_coefficients=True)

    def test_real_coefficient_target_at_small_scale_is_accepted_when_real(self):
        s = 1e-20
        n = 5
        m = [[complex(s), complex(0.5 * s)], [complex(0.5 * s), complex(s)]]
        spectra, _ = N.draw_from_csd([m] * sp.n_freq(n), n, 0, real_coefficients=True)
        for k in sp.randomized_bins(n):
            self.assertEqual(spectra[0][k].imag, 0.0, msg=f"bin {k}")

    def test_rank_one_draw_reports_rank_one_at_small_scale(self):
        s = 1e-20
        m = [[complex(s), complex(s)], [complex(s), complex(s)]]
        _, info = N.draw_from_csd([m], 1, 0)
        self.assertEqual(info["effective_rank"], [1])
        self.assertEqual(info["rank_deficient"], [0])
        self.assertEqual(info["ridge_applied"], [0])

    def test_draws_scale_with_the_matrix_at_every_bin(self):
        # Same seed and same normalised target: scaling the CSD by s scales every draw by sqrt(s).
        n = 5  # three bins: DC (fixed), and two randomised complex bins
        base = [[complex(2.0), complex(1.0, 0.5)], [complex(1.0, -0.5), complex(2.0)]]
        ref, _ = N.draw_from_csd([base] * sp.n_freq(n), n, 3)
        for scale in (1e-20, 1e8):
            scaled = [[[v * scale for v in row] for row in base]] * sp.n_freq(n)
            got, _ = N.draw_from_csd(scaled, n, 3)
            root = math.sqrt(scale)
            for c in range(2):
                for k in range(sp.n_freq(n)):
                    self.assertLessEqual(abs(got[c][k] - ref[c][k] * root),
                                         1e-9 * root * max(1.0, abs(ref[c][k])),
                                         msg=f"scale {scale} channel {c} bin {k}")


class EstimatorTests(unittest.TestCase):
    def setUp(self):
        self.n = 32
        self.x = _pair(self.n)

    def test_single_periodogram_is_rank_one_and_the_null_reports_it(self):
        _, report = N.cholesky_gaussian_csd(self.x, 1, estimator="single_periodogram")
        self.assertTrue(all(r == 1 for r in report.effective_rank_per_bin))
        self.assertEqual(set(report.ridge_applied_bins), set(range(sp.n_freq(self.n))))

    def test_multitaper_default_has_full_rank_for_three_channels(self):
        x = _independent(self.n, 3, 4)
        _, report = N.cholesky_gaussian_csd(x, 2)
        self.assertEqual(report.n_tapers, 5)  # max(4, d + 2)
        self.assertTrue(all(r == 3 for r in report.effective_rank_per_bin))

    def test_single_taper_multitaper_is_rank_one(self):
        _, report = N.cholesky_gaussian_csd(self.x, 2, n_tapers=1)
        self.assertTrue(all(r == 1 for r in report.effective_rank_per_bin))

    def test_estimator_parameters_are_reported(self):
        _, report = N.cholesky_gaussian_csd(self.x, 0, estimator="periodogram_boxcar", smoothing_halfwidth=2)
        self.assertEqual(report.estimator, "periodogram_boxcar")
        self.assertEqual(report.estimator_source, "estimated_from_input")
        self.assertEqual(report.smoothing_halfwidth, 2)
        self.assertIsNone(report.n_tapers)

    def test_shrinkage_moves_the_target_to_scaled_identity_at_full_strength(self):
        target, info = C.estimate_csd(self.x, "multitaper", shrinkage=1.0)
        self.assertEqual(info["shrinkage"], 1.0)
        for mat in target:
            self.assertAlmostEqual(mat[0][1].real, 0.0, places=12)
            self.assertAlmostEqual(mat[0][0].real, mat[1][1].real, places=12)

    def test_shrinkage_outside_unit_interval_is_rejected(self):
        with self.assertRaises(sp.SurrogateInputError):
            C.estimate_csd(self.x, "multitaper", shrinkage=1.5)

    def test_unknown_estimator_is_rejected(self):
        with self.assertRaises(sp.SurrogateInputError):
            C.estimate_csd(self.x, "welch_magic")

    def test_designed_sinusoid_is_flagged_as_near_rank_one_at_its_bin(self):
        k = 3
        _, report = N.cholesky_gaussian_csd(_designed_winding(self.n, k), 0)
        self.assertLess(report.participation_ratio_per_bin[k], 1.01)

    def test_independent_channels_are_not_flagged_as_near_rank_one(self):
        k = 3
        _, report = N.cholesky_gaussian_csd(_independent(self.n, 3, 5), 0)
        self.assertGreater(report.participation_ratio_per_bin[k], 1.5)


class ExpectationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n = 32
        cls.x = _pair(cls.n)
        cls.target, _ = C.estimate_csd(cls.x, "multitaper", n_tapers=4)
        cls.mean = _ensemble_mean(N.cholesky_gaussian_csd, cls.x, cls.n, ENSEMBLE_SEEDS,
                                  estimator="multitaper", n_tapers=4)

    def test_multitaper_ensemble_mean_matches_the_estimate_within_tolerance(self):
        error = N._csd_rel_error(self.mean, self.target)
        self.assertLess(error, ENSEMBLE_TOL, msg=f"ensemble relative error {error:.4f}")

    def test_identity_control_fails_the_same_criterion(self):
        identity = [[[complex(1.0 if i == j else 0.0, 0.0) for j in range(2)] for i in range(2)]
                    for _ in range(sp.n_freq(self.n))]
        error = N._csd_rel_error(self.mean, identity)
        self.assertGreater(error, CONTROL_MIN, msg=f"control error {error:.4f}")


class ZeroLagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n = 32
        cls.x = _pair(cls.n)
        cls.target, _ = C.estimate_csd(cls.x, "multitaper", n_tapers=4)
        real_target = [[[complex(m[i][j].real, 0.0) for j in range(2)] for i in range(2)] for m in cls.target]
        cls.real_target = real_target
        cls.mean = _ensemble_mean(N.zero_lag_real_part_gaussian, cls.x, cls.n, ENSEMBLE_SEEDS,
                                  estimator="multitaper", n_tapers=4)

    def test_surrogate_cross_spectrum_has_no_imaginary_part(self):
        surrogate, _ = N.zero_lag_real_part_gaussian(self.x, 3, estimator="multitaper", n_tapers=4)
        raw = sp.periodogram_csd([sp.rfft(s) for s in surrogate], self.n)
        self.assertLess(max(abs(raw[k][0][1].imag) for k in range(len(raw))), 1e-12)

    def test_ensemble_mean_matches_the_real_part_within_tolerance(self):
        error = N._csd_rel_error(self.mean, self.real_target)
        self.assertLess(error, ENSEMBLE_TOL, msg=f"real-part relative error {error:.4f}")

    def test_zero_lag_null_is_separately_named_and_exploratory(self):
        self.assertNotIn("zero_lag_real_part_gaussian", N.NULL_IDS)
        self.assertIn("zero_lag_real_part_gaussian", N.EXPLORATORY_NULL_IDS)
        contract = N.CONTRACTS["zero_lag_real_part_gaussian"]
        self.assertIn("EXPLORATORY", contract["intended_use"])
        self.assertIn("volume conduction", contract["invalid_for"])

    def test_zero_lag_report_declares_volume_conduction_not_modelled(self):
        _, report = N.zero_lag_real_part_gaussian(self.x, 0, estimator="multitaper", n_tapers=4)
        self.assertEqual(report.status["volume_conduction"], "NOT_MODELLED")
        self.assertEqual(report.status["imaginary_part"], "SET_TO_ZERO_BY_CONSTRUCTION")


class ExplicitEstimateTests(unittest.TestCase):
    def setUp(self):
        self.n = 32
        self.x = _pair(self.n)
        self.target, _ = C.estimate_csd(self.x, "multitaper", n_tapers=4)

    def test_supplied_estimate_is_used_and_reported_as_supplied(self):
        _, report = N.cholesky_gaussian_csd(self.x, 1, spectral_estimate=self.target)
        self.assertEqual(report.estimator, "supplied")
        self.assertEqual(report.estimator_source, "explicitly_supplied")
        self.assertEqual(report.status["spectral_estimate_source"], "EXPLICITLY_SUPPLIED")

    def test_supplied_estimate_with_wrong_bin_count_is_rejected(self):
        with self.assertRaises(sp.SurrogateInputError):
            N.cholesky_gaussian_csd(self.x, 1, spectral_estimate=self.target[:-1])

    def test_supplied_non_hermitian_bin_is_rejected(self):
        bad = [[row[:] for row in m] for m in self.target]
        bad[2][0][1] = complex(0.0, 5.0)
        with self.assertRaises(sp.SurrogateInputError):
            N.cholesky_gaussian_csd(self.x, 1, spectral_estimate=bad)

    def test_materially_indefinite_supplied_bin_fails_closed(self):
        bad = [[row[:] for row in m] for m in self.target]
        bad[2] = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(-0.5, 0.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            N.cholesky_gaussian_csd(self.x, 1, spectral_estimate=bad)

    def test_real_coefficients_mode_rejects_a_complex_target(self):
        target = [[[complex(2.0, 0.0), complex(0.3, 0.2)], [complex(0.3, -0.2), complex(1.0, 0.0)]]
                  for _ in range(sp.n_freq(self.n))]
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd(target, self.n, 0, real_coefficients=True)

    def test_real_coefficients_mode_draws_real_coefficients(self):
        target = [[[complex(2.0, 0.0), complex(0.3, 0.0)], [complex(0.3, 0.0), complex(1.0, 0.0)]]
                  for _ in range(sp.n_freq(self.n))]
        spectra, _ = N.draw_from_csd(target, self.n, 0, real_coefficients=True)
        for channel in spectra:
            self.assertTrue(all(v.imag == 0.0 for v in channel))


class WindingVariationTests(unittest.TestCase):
    def test_designed_winding_is_not_varied_by_the_cholesky_null(self):
        n, k = 32, 3
        report = C.winding_variation(_designed_winding(n, k), N.cholesky_gaussian_csd, range(20), k)
        self.assertFalse(report["varies_from_original"])
        self.assertEqual(report["original_value"], report["distinct_values"][0])

    def test_independent_channels_have_the_winding_varied_by_the_cholesky_null(self):
        x = _independent(32, 3, 5)
        report = C.winding_variation(x, N.cholesky_gaussian_csd, range(40), 3)
        self.assertTrue(report["varies_across_ensemble"])

    def test_two_channel_loop_has_no_winding_even_at_an_exact_pi_relative_phase(self):
        # Before the fix, [[1], [-1]] returned -1: the two edges each wrap to -pi.
        self.assertEqual(C.phase_loop_winding([[1 + 0j], [1 + 0j]], 0), 0)
        self.assertEqual(C.phase_loop_winding([[1 + 0j], [-1 + 0j]], 0), 0)

    def test_exact_pi_step_has_no_defined_winding_for_three_or_more_channels(self):
        # The minimal-wrap sum is ambiguous at +/-pi, so the statistic must fail closed.
        with self.assertRaises(sp.SurrogateInputError):
            C.phase_loop_winding([[1 + 0j], [-1 + 0j], [1 + 0j]], 0)

    def test_designed_vortex_winding_is_unchanged(self):
        spectra = [[cmath.exp(1j * c * math.pi / 2)] for c in range(4)]
        self.assertEqual(C.phase_loop_winding(spectra, 0), -1)

    def test_zero_lag_null_winding_is_undefined_and_fails_closed(self):
        # Its real-coefficient draws have exact 0/pi relative phases. Before the fix this
        # reported spurious variation (-1 and 0 around an original of 1).
        x = _independent(32, 3, 7)
        with self.assertRaises(sp.SurrogateInputError):
            C.winding_variation(x, N.zero_lag_real_part_gaussian, range(4), 3)

    def test_common_phase_never_varies_the_winding(self):
        x = _independent(32, 3, 5)
        report = C.winding_variation(x, N.common_phase_prichard_theiler, range(40), 3)
        self.assertFalse(report["varies_from_original"])

    def test_empty_seed_set_is_rejected(self):
        with self.assertRaises(sp.SurrogateInputError):
            C.winding_variation(_pair(8), N.cholesky_gaussian_csd, [], 1)


class ReproducibilityTests(unittest.TestCase):
    def test_new_entry_points_reproduce_for_the_same_seed(self):
        x = _pair(16)
        a, _ = N.cholesky_gaussian_csd(x, 9, estimator="multitaper")
        b, _ = N.cholesky_gaussian_csd(x, 9, estimator="multitaper")
        self.assertEqual(a, b)
        c, _ = N.zero_lag_real_part_gaussian(x, 9, estimator="multitaper")
        d, _ = N.zero_lag_real_part_gaussian(x, 9, estimator="multitaper")
        self.assertEqual(c, d)


if __name__ == "__main__":
    unittest.main()
