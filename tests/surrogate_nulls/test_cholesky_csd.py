"""Cholesky Gaussian cross-spectral null: expectation, single-draw honesty, and failure paths.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.

Declared before measurement (not tuned to pass):
- ENSEMBLE_TOL = 0.15: relative Frobenius error, summed over bins, of the ensemble-mean
  raw periodogram against the smoothed target, over ENSEMBLE_SEEDS = 800 seeds, N = 32,
  halfwidth = 1. Monte-Carlo noise for this design is about 0.04 (observed 0.040).
- A control target (identity) must fail the same criterion (> 0.5), so the test can fail.
"""
from __future__ import annotations

import math
import random
import unittest

from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp

ENSEMBLE_TOL = 0.15
ENSEMBLE_SEEDS = 800
CONTROL_MIN = 0.5


def _correlated_pair(n, seed=7):
    rng = random.Random(seed)
    x0 = [rng.gauss(0.0, 1.0) for _ in range(n)]
    x1 = [0.7 * a + 0.5 * rng.gauss(0.0, 1.0) for a in x0]
    return [x0, x1]


def _ensemble_mean_periodogram(x, n, seeds, halfwidth=1):
    """Average the raw periodogram of surrogate time series over seeds (round-trip through rFFT)."""
    d = len(x)
    bins = sp.n_freq(n)
    acc = [[[0j] * d for _ in range(d)] for _ in range(bins)]
    for seed in range(seeds):
        surrogate, _ = N.cholesky_gaussian_cross_spectral(x, seed, smoothing_halfwidth=halfwidth)
        raw = sp.periodogram_csd([sp.rfft(s) for s in surrogate], n)
        for k in range(bins):
            for i in range(d):
                for j in range(d):
                    acc[k][i][j] += raw[k][i][j] / seeds
    return acc


class ExpectationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n = 32
        cls.x = _correlated_pair(cls.n)
        raw = sp.periodogram_csd([sp.rfft(c) for c in cls.x], cls.n)
        cls.target = N._target_for_compare(sp.smooth_csd(raw, 1), cls.n)
        cls.mean = _ensemble_mean_periodogram(cls.x, cls.n, ENSEMBLE_SEEDS)

    def test_ensemble_mean_matches_declared_smoothed_csd_within_tolerance(self):
        error = N._csd_rel_error(self.mean, self.target)
        self.assertLess(error, ENSEMBLE_TOL, msg=f"ensemble relative error {error:.4f}")

    def test_control_identity_target_fails_the_same_criterion(self):
        # Proves the criterion can fail: a wrong target must be rejected by the same comparison.
        identity = [[[complex(1.0 if i == j else 0.0, 0.0) for j in range(2)] for i in range(2)]
                    for _ in range(sp.n_freq(self.n))]
        error = N._csd_rel_error(self.mean, identity)
        self.assertGreater(error, CONTROL_MIN, msg=f"control error {error:.4f}")


class SingleRealisationHonestyTests(unittest.TestCase):
    def test_single_realisation_is_not_reported_as_exact(self):
        x = _correlated_pair(32)
        _, report = N.cholesky_gaussian_cross_spectral(x, 0)
        self.assertIn("NOT_EXACT", report.status["auto_spectrum"])
        self.assertIn("NOT_EXACT", report.status["cross_spectrum"])
        self.assertGreater(report.cross_spectrum_rel_error, 0.3)

    def test_report_states_expectation_only_in_notes(self):
        x = _correlated_pair(32)
        _, report = N.cholesky_gaussian_cross_spectral(x, 0)
        self.assertTrue(any("in expectation" in note or "not exact" in note for note in report.notes))


class SingularAndPsdTests(unittest.TestCase):
    def test_singular_csd_is_ridge_regularised_and_reported(self):
        base = [math.sin(0.4 * t) + 0.2 * t for t in range(16)]
        x = [base, list(base)]  # identical channels: rank-1 CSD at every bin
        signals, report = N.cholesky_gaussian_cross_spectral(x, 1)
        self.assertEqual(set(report.rank_deficient_bins), set(range(sp.n_freq(16))))
        self.assertTrue(set(report.ridge_applied_bins) <= set(report.rank_deficient_bins))
        self.assertTrue(all(math.isfinite(v) for row in signals for v in row))

    def test_singular_csd_without_ridge_fails_closed(self):
        base = [math.sin(0.4 * t) + 0.2 * t for t in range(16)]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            N.cholesky_gaussian_cross_spectral([base, list(base)], 1, ridge_rel=0.0)

    def test_indefinite_hermitian_matrix_fails_closed_even_with_ridge(self):
        identity = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(1.0, 0.0)]]
        indefinite = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(-0.5, 0.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            N.draw_from_csd([identity, indefinite, identity], 4, 0)

    def test_non_hermitian_matrix_is_rejected(self):
        non_hermitian = [[complex(1.0, 0.0), complex(0.0, 1.0)], [complex(0.0, 1.0), complex(1.0, 0.0)]]
        ok = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(1.0, 0.0)]]
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([ok, non_hermitian, ok], 4, 0)

    def test_zero_trace_with_nonzero_entries_is_rejected(self):
        off = [[complex(0.0, 0.0), complex(1.0, 0.0)], [complex(1.0, 0.0), complex(0.0, 0.0)]]
        ok = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(1.0, 0.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            N.draw_from_csd([ok, off, ok], 4, 0)

    def test_dimensional_mismatch_is_rejected(self):
        ok2 = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(1.0, 0.0)]]
        ok3 = [[complex(1.0, 0.0) if i == j else complex(0.0, 0.0) for j in range(3)] for i in range(3)]
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([ok2, ok3, ok2], 4, 0)  # one bin is 3x3 in a 2-channel problem
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([ok2, ok2], 4, 0)       # two bins where four samples need three


class DcNyquistAndDegenerateTests(unittest.TestCase):
    def test_dc_and_nyquist_coefficients_are_exactly_real(self):
        # The drawn coefficients are real by construction, so the imaginary parts are exactly zero.
        target = [[[complex(2.0, 0.0), complex(0.5, 0.0)], [complex(0.5, 0.0), complex(1.0, 0.0)]]
                  for _ in range(sp.n_freq(8))]
        for k in range(sp.n_freq(8)):
            target[k][0][1] = complex(0.3, 0.1)
            target[k][1][0] = complex(0.3, -0.1)
        spectra, _ = N.draw_from_csd(target, 8, 4)
        for channel in spectra:
            self.assertEqual(channel[0].imag, 0.0)
            self.assertEqual(channel[4].imag, 0.0)

    def test_round_trip_residue_at_dc_and_nyquist_is_within_numerical_tolerance(self):
        # Re-measuring a real time series with a floating-point DFT leaves a residue near 1e-16.
        x = _correlated_pair(8)
        surrogate, _ = N.cholesky_gaussian_cross_spectral(x, 4)
        for channel in surrogate:
            measured = sp.rfft(channel)
            self.assertLess(abs(measured[0].imag), 1e-12)
            self.assertLess(abs(measured[4].imag), 1e-12)

    def test_zero_signal_gives_zero_surrogate_and_zero_power_bins(self):
        x = [[0.0] * 8, [0.0] * 8]
        surrogate, report = N.cholesky_gaussian_cross_spectral(x, 2)
        self.assertTrue(all(v == 0.0 for row in surrogate for v in row))
        self.assertEqual(set(report.zero_power_bins), set(range(sp.n_freq(8))))

    def test_same_seed_reproduces_and_different_seed_differs(self):
        x = _correlated_pair(16)
        a, _ = N.cholesky_gaussian_cross_spectral(x, 9)
        b, _ = N.cholesky_gaussian_cross_spectral(x, 9)
        c, _ = N.cholesky_gaussian_cross_spectral(x, 10)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


if __name__ == "__main__":
    unittest.main()
