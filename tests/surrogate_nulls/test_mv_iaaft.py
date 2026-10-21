"""MV-IAAFT rank-adjusted null: exact marginal, honest spectral status, and reporting.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.

What IAAFT is claimed to preserve: the sorted values of each channel exactly, after the
final rank adjustment. It does NOT preserve the post-rank cross-spectrum; that is measured,
and the strict gate is reported UNMET when missed. These tests check the status labels
against the measured numbers rather than assuming the algorithm meets them.
"""
from __future__ import annotations

import math
import random
import unittest

from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp


def _correlated_pair(n, seed=7):
    rng = random.Random(seed)
    x0 = [rng.gauss(0.0, 1.0) for _ in range(n)]
    x1 = [0.7 * a + 0.5 * rng.gauss(0.0, 1.0) for a in x0]
    return [x0, x1]


class MvIaaftTests(unittest.TestCase):
    def setUp(self):
        self.n = 32
        self.x = _correlated_pair(self.n)

    def test_marginal_is_exact_after_final_rank_adjustment(self):
        surrogate, report = N.mv_iaaft_rank_adjusted(self.x, 3)
        self.assertLessEqual(report.marginal_max_abs_error, N.MARGINAL_EXACT_TOL)
        self.assertEqual(report.status["marginal"], "EXACT_POST_RANK")
        for got, original in zip(surrogate, self.x):
            self.assertEqual(sorted(got), sorted(original))

    def test_reports_pre_and_post_rank_spectral_errors_for_every_channel(self):
        _, report = N.mv_iaaft_rank_adjusted(self.x, 3)
        self.assertEqual(len(report.auto_spectrum_rel_error), 2)
        self.assertEqual(len(report.pre_rank_auto_spectrum_rel_error), 2)
        self.assertIsNotNone(report.cross_spectrum_rel_error)
        self.assertIsNotNone(report.pre_rank_cross_spectrum_rel_error)

    def test_strict_cross_status_matches_the_measured_value(self):
        _, report = N.mv_iaaft_rank_adjusted(self.x, 3)
        expected = (
            "MET_POST_RANK_STRICT"
            if report.cross_spectrum_rel_error <= N.CROSS_SPECTRUM_STRICT_TOL
            else "UNMET_POST_RANK_STRICT"
        )
        self.assertEqual(report.status["cross_spectrum_strict"], expected)
        self.assertEqual(report.status["cross_spectrum"], "NOT_TARGETED_MEASURED_ONLY")

    def test_auto_spectrum_status_matches_the_measured_value(self):
        _, report = N.mv_iaaft_rank_adjusted(self.x, 3)
        expected = (
            "MET_POST_RANK_WITHIN_TOL"
            if max(report.auto_spectrum_rel_error) <= N.AUTO_SPECTRUM_TOL
            else "UNMET_POST_RANK_WITHIN_TOL"
        )
        self.assertEqual(report.status["auto_spectrum"], expected)

    def test_non_convergence_is_reported_not_hidden(self):
        # One iteration cannot establish a stable rank order (it needs two to compare).
        _, report = N.mv_iaaft_rank_adjusted(self.x, 3, max_iter=1)
        self.assertFalse(report.converged)
        self.assertEqual(report.status["converged"], "NO_MAX_ITER_REACHED")
        self.assertEqual(report.iterations, 1)

    def test_converges_within_budget_for_the_reference_seed(self):
        _, report = N.mv_iaaft_rank_adjusted(self.x, 3)
        self.assertTrue(report.converged)
        self.assertEqual(report.status["converged"], "YES")

    def test_single_channel_has_no_cross_spectrum_and_says_so(self):
        _, report = N.mv_iaaft_rank_adjusted([self.x[0]], 3)
        self.assertIsNone(report.cross_spectrum_rel_error)
        self.assertEqual(report.status["cross_spectrum_strict"], "NOT_APPLICABLE_SINGLE_CHANNEL")

    def test_same_seed_is_reproducible(self):
        a, _ = N.mv_iaaft_rank_adjusted(self.x, 5)
        b, _ = N.mv_iaaft_rank_adjusted(self.x, 5)
        self.assertEqual(a, b)

    def test_report_declares_what_is_preserved(self):
        _, report = N.mv_iaaft_rank_adjusted(self.x, 3)
        self.assertEqual(report.status["intended_use"], "MARGINAL_PRESERVING_NULL_WITH_APPROXIMATE_AUTO_SPECTRA")


class CsdRelativeErrorTests(unittest.TestCase):
    def test_tiny_scale_does_not_hide_a_large_relative_error(self):
        target = 1e-20
        actual = 1.21e-20

        error = N._csd_rel_error([[[actual]]], [[[target]]])

        # Independent scalar oracle: |1.21*t - t| / |t| = 0.21.
        self.assertAlmostEqual(error, 0.21, delta=1e-14)

    def test_relative_error_is_scale_invariant(self):
        base = [[2.0, complex(0.3, 0.4)], [complex(0.3, -0.4), 1.0]]
        for scale in (1e-200, 1e-20, 1.0, 1e20, 1e200):
            with self.subTest(scale=scale):
                target = [[[scale * value for value in row] for row in base]]
                factor = 1.21 * scale
                actual = [[[factor * value for value in row] for row in base]]

                error = N._csd_rel_error(actual, target)

                self.assertAlmostEqual(error, 0.21, delta=1e-14)

    def test_both_zero_inputs_have_zero_relative_error(self):
        self.assertEqual(N._csd_rel_error([[[0j]]], [[[0j]]]), 0.0)

    def test_nonzero_actual_with_zero_target_fails_closed(self):
        error = N._csd_rel_error([[[1e-20]]], [[[0.0]]])
        self.assertEqual(error, math.inf)

    def test_zero_actual_with_nonzero_target_has_unit_relative_error(self):
        self.assertEqual(N._csd_rel_error([[[0.0]]], [[[1e-20]]]), 1.0)

    def test_non_finite_values_fail_closed(self):
        for actual, target in (
            (float("nan"), 1.0),
            (float("inf"), 1.0),
            (1.0, float("nan")),
            (1.0, float("inf")),
        ):
            with self.subTest(actual=actual, target=target):
                error = N._csd_rel_error([[[actual]]], [[[target]]])
                self.assertEqual(error, math.inf)

    def test_large_finite_hermitian_inputs_do_not_overflow(self):
        target = [[[1.7e308, -1.7e308], [-1.7e308, 1.7e308]]]
        actual = [[[1.7e308, 1.7e308], [1.7e308, 1.7e308]]]

        error = N._csd_rel_error(actual, target)

        self.assertAlmostEqual(error, math.sqrt(2.0), delta=1e-14)

    def test_small_residual_survives_extreme_target_dynamic_range(self):
        target = [[[1e160, 0.0], [0.0, 1e-160]]]
        actual = [[[1e160, 0.0], [0.0, 2e-160]]]

        error = N._csd_rel_error(actual, target)

        # The only residual is 1e-160 against a Frobenius target norm of 1e160.
        self.assertTrue(math.isclose(error, 1e-320, rel_tol=0.1, abs_tol=0.0), error)


if __name__ == "__main__":
    unittest.main()
