"""Real-part (zero-lag) null: PSD of Re C, ensemble behaviour, and estimator validity labels.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.
The real-part null is an ensemble zero-lag / real-covariance null. These tests check the
estimator and null properties it depends on, not any property of a biological signal.
"""
from __future__ import annotations

import math
import random
import unittest

from tools.surrogate_nulls import csd as C
from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp


def _independent(n, d, seed):
    rng = random.Random(seed)
    return [[rng.gauss(0.0, 1.0) for _ in range(n)] for _ in range(d)]


def _real_part(mat):
    d = len(mat)
    return [[complex(mat[i][j].real, 0.0) for j in range(d)] for i in range(d)]


def _block_target(n):
    """Hermitian PSD two-channel target with a non-zero imaginary part at every bin."""
    block = [[complex(2.0, 0.0), complex(0.3, 0.4)], [complex(0.3, -0.4), complex(1.0, 0.0)]]
    return [block for _ in range(sp.n_freq(n))]


class RealPartPositiveSemidefiniteTests(unittest.TestCase):
    def _check_all_bins(self, csd_by_bin):
        for k, mat in enumerate(csd_by_bin):
            re = _real_part(mat)
            d = len(re)
            for i in range(d):
                for j in range(d):
                    self.assertAlmostEqual(re[i][j].real, re[j][i].real, places=12, msg=f"bin {k}")
            # matrix_diagnostics raises NonPositiveDefiniteError on a materially indefinite matrix.
            _, min_rel, _, _ = C.matrix_diagnostics(re)
            self.assertGreaterEqual(min_rel, -C.DEFAULT_PSD_TOL, msg=f"bin {k}")

    def test_negative_control_indefinite_real_matrix_is_rejected(self):
        # The PSD check must have teeth: an indefinite real symmetric matrix must raise.
        indefinite = [[complex(1.0, 0.0), complex(2.0, 0.0)], [complex(2.0, 0.0), complex(1.0, 0.0)]]
        with self.assertRaises(sp.NonPositiveDefiniteError):
            C.matrix_diagnostics(indefinite)

    def test_real_part_of_multitaper_csd_is_psd_across_data_seeds(self):
        for data_seed in range(4):
            x = _independent(32, 3, data_seed)
            csd, _ = C.estimate_csd(x, "multitaper", n_tapers=5)
            self._check_all_bins(csd)

    def test_real_part_of_boxcar_csd_is_psd_for_each_halfwidth(self):
        x = _independent(32, 3, 7)
        for halfwidth in (1, 2):
            csd, _ = C.estimate_csd(x, "periodogram_boxcar", smoothing_halfwidth=halfwidth)
            self._check_all_bins(csd)

    def test_real_part_of_single_periodogram_is_psd_and_rank_deficient(self):
        # Rank one for more than one channel: the smallest eigenvalue is numerically zero, not negative.
        x = _independent(32, 3, 7)
        csd, _ = C.estimate_csd(x, "single_periodogram")
        self._check_all_bins(csd)


class RealPartDrawTests(unittest.TestCase):
    def test_draws_on_real_part_are_exactly_real_at_every_bin(self):
        n = 32
        x = _independent(n, 3, 2)
        csd, _ = C.estimate_csd(x, "multitaper", n_tapers=5)
        real_target = [_real_part(m) for m in csd]
        spectra, _ = N.draw_from_csd(real_target, n, 3, real_coefficients=True)
        for c in range(3):
            for k in range(sp.n_freq(n)):
                self.assertEqual(spectra[c][k].imag, 0.0, msg=f"channel {c} bin {k}")

    def test_real_coefficient_draw_rejects_a_complex_target(self):
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd(_block_target(16), 16, 0, real_coefficients=True)


class RealPartEnsembleTests(unittest.TestCase):
    """Across seeds: the imaginary part of the estimate is discarded, and the real part is
    matched in expectation. Both are checked on a target whose imaginary part is non-zero."""

    def setUp(self):
        self.n = 16
        self.target = _block_target(self.n)
        self.x = _independent(self.n, 2, 0)

    def test_imaginary_part_of_the_estimate_is_discarded_in_every_realisation(self):
        for seed in range(20):
            signals, _ = N.zero_lag_real_part_gaussian(self.x, seed, spectral_estimate=self.target)
            measured = [sp.rfft(s) for s in signals]
            for k in range(sp.n_freq(self.n)):
                cross = measured[0][k] * measured[1][k].conjugate()
                self.assertLess(abs(cross.imag), 1e-12, msg=f"seed {seed} bin {k}")

    def test_ensemble_real_part_matches_the_real_target_within_monte_carlo_error(self):
        k = 3
        values = []
        imag_total = 0.0
        for seed in range(400):
            signals, _ = N.zero_lag_real_part_gaussian(self.x, seed, spectral_estimate=self.target)
            measured = [sp.rfft(s) for s in signals]
            cross = sp.periodogram_csd(measured, self.n)[k][0][1]
            values.append(cross.real)
            imag_total += abs(cross.imag)
        self.assertLess(imag_total, 1e-9)
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        se = math.sqrt(var / len(values))
        target_real = self.target[k][0][1].real
        self.assertLess(abs(mean - target_real), 5.0 * se,
                        msg=f"mean {mean:.4f} vs real target {target_real} (SE {se:.4f})")


class EstimatorValidityLabelTests(unittest.TestCase):
    def setUp(self):
        self.x = _independent(32, 3, 4)

    def test_multitaper_with_rank_headroom_is_labelled_as_such(self):
        _, report = N.cholesky_gaussian_csd(self.x, 0, estimator="multitaper", n_tapers=4)  # K = d + 1
        self.assertEqual(report.status["estimator_validity"],
                         "MULTIWINDOW_ESTIMATE_WITH_RANK_HEADROOM_REPORTED_PER_BIN")

    def test_multitaper_without_rank_headroom_is_labelled_low_rank(self):
        _, report = N.cholesky_gaussian_csd(self.x, 0, estimator="multitaper", n_tapers=2)  # K < d + 1
        self.assertEqual(report.status["estimator_validity"],
                         "MULTIWINDOW_ESTIMATE_LOW_RANK_REPORTED_PER_BIN")

    def test_single_periodogram_is_labelled_as_a_rank_one_diagnostic(self):
        _, report = N.cholesky_gaussian_csd(self.x, 0, estimator="single_periodogram")
        self.assertEqual(report.status["estimator_validity"], "DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL")

    def test_boxcar_label_depends_on_the_smoothing_halfwidth(self):
        _, unsmoothed = N.cholesky_gaussian_csd(self.x, 0, estimator="periodogram_boxcar", smoothing_halfwidth=0)
        _, smoothed = N.cholesky_gaussian_csd(self.x, 0, estimator="periodogram_boxcar", smoothing_halfwidth=1)
        self.assertEqual(unsmoothed.status["estimator_validity"],
                         "DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL")
        self.assertEqual(smoothed.status["estimator_validity"],
                         "SMOOTHED_PERIODOGRAM_RANK_UP_TO_2H_PLUS_1_REPORTED_PER_BIN")

    def test_supplied_estimate_is_labelled_as_not_validated_against_data(self):
        x2 = _independent(32, 2, 4)  # the 2x2 block target must match the channel count
        _, report = N.cholesky_gaussian_csd(x2, 0, spectral_estimate=_block_target(32))
        self.assertEqual(report.status["estimator_validity"], "SUPPLIED_NOT_VALIDATED_AGAINST_DATA")

    def test_legacy_cross_spectral_wrapper_reports_its_halfwidth_validity(self):
        _, unsmoothed = N.cholesky_gaussian_cross_spectral(self.x, 0, smoothing_halfwidth=0)
        _, smoothed = N.cholesky_gaussian_cross_spectral(self.x, 0, smoothing_halfwidth=1)
        self.assertEqual(unsmoothed.status["estimator_validity"],
                         "DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL")
        self.assertEqual(smoothed.status["estimator_validity"],
                         "SMOOTHED_PERIODOGRAM_RANK_UP_TO_2H_PLUS_1_REPORTED_PER_BIN")


if __name__ == "__main__":
    unittest.main()
