"""Adversarial checks for PR #417's surrogate-null contracts.

Synthetic signals only. These tests exercise the candidate implementation directly;
they are software/statistical checks, not evidence for a biological mechanism.
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
ENSEMBLE_SEEDS = 384
MC_SE_MULTIPLIER = 5.0


def _phase_vortex(n=32, k=3):
    """Four narrowband channels whose phase advances by pi/2 around a loop."""
    return [
        [math.cos(TWO_PI * k * t / n + TWO_PI * channel / 4.0) for t in range(n)]
        for channel in range(4)
    ]


def _independent(n, d, seed):
    rng = random.Random(seed)
    return [[rng.gauss(0.0, 1.0) for _ in range(n)] for _ in range(d)]


def _wrap(angle):
    return (angle + math.pi) % TWO_PI - math.pi


def _edge_relative_phases(spectra, k):
    phases = [cmath.phase(channel[k]) for channel in spectra]
    return tuple(_wrap(phases[i] - phases[(i + 1) % len(phases)]) for i in range(len(phases)))


def _single_periodogram_gaussian(data, seed):
    return N.cholesky_gaussian_csd(data, seed, estimator="single_periodogram")


def _shrunken_multitaper_gaussian(data, seed):
    return N.cholesky_gaussian_csd(
        data, seed, estimator="multitaper", n_tapers=5, shrinkage=0.2
    )


def _sample_csd_ensemble(data, generator, seeds, **kwargs):
    n = len(data[0])
    d = len(data)
    samples = [[[[] for _ in range(d)] for _ in range(d)] for _ in range(sp.n_freq(n))]
    for seed in seeds:
        surrogate, _ = generator(data, seed, **kwargs)
        measured = sp.periodogram_csd([sp.rfft(channel) for channel in surrogate], n)
        for k in range(len(measured)):
            for i in range(d):
                for j in range(d):
                    samples[k][i][j].append(measured[k][i][j])
    return samples


def _assert_mean_within_mc_error(test_case, samples, target, label):
    """Check each real/imaginary mean within five empirical standard errors."""
    n_seeds = len(samples[0][0][0])
    for k, matrix in enumerate(samples):
        for i, row in enumerate(matrix):
            for j, values in enumerate(row):
                for component in ("real", "imag"):
                    observed = [getattr(value, component) for value in values]
                    mean = sum(observed) / n_seeds
                    variance = sum((value - mean) ** 2 for value in observed) / (n_seeds - 1)
                    standard_error = math.sqrt(variance / n_seeds)
                    expected = getattr(target[k][i][j], component)
                    numerical_floor = 1e-12 * max(1.0, abs(expected))
                    tolerance = MC_SE_MULTIPLIER * standard_error + numerical_floor
                    test_case.assertLessEqual(
                        abs(mean - expected),
                        tolerance,
                        msg=(f"{label}: bin={k}, pair=({i},{j}), component={component}, "
                             f"mean={mean:.6g}, target={expected:.6g}, SE={standard_error:.3g}, "
                             f"limit={tolerance:.3g}"),
                    )


class CommonPhaseVortexTests(unittest.TestCase):
    def test_common_phase_preserves_vortex_edge_phases_and_winding(self):
        n, k = 32, 3
        signal = _phase_vortex(n, k)
        original_spectra = [sp.rfft(channel) for channel in signal]
        original_edges = _edge_relative_phases(original_spectra, k)
        original_winding = C.phase_loop_winding(original_spectra, k)
        self.assertEqual(abs(original_winding), 1)

        for seed in (0, 1, 7, 19, 41):
            surrogate, report = N.common_phase_prichard_theiler(signal, seed)
            measured = [sp.rfft(channel) for channel in surrogate]
            edges = _edge_relative_phases(measured, k)
            for edge, (before, after) in enumerate(zip(original_edges, edges)):
                self.assertLess(
                    abs(_wrap(after - before)), 1e-9,
                    msg=f"seed={seed}, edge={edge}, status={report.status}",
                )
            self.assertEqual(C.phase_loop_winding(measured, k), original_winding)


class RankOneEstimatorTests(unittest.TestCase):
    def test_single_periodogram_is_diagnosed_and_does_not_randomize_vortex_winding(self):
        n, k = 32, 3
        signal = _phase_vortex(n, k)
        _, report = _single_periodogram_gaussian(signal, 0)
        self.assertEqual(report.estimator, "single_periodogram")
        # At the designed nonzero bin, the unsmoothed single-epoch CSD is rank one.
        # Near-zero off-tone bins can be dominated by transform round-off and are not
        # evidence about the rank of the target bin.
        assert report.effective_rank_per_bin is not None
        effective_ranks = report.effective_rank_per_bin
        self.assertEqual(effective_ranks[k], 1)
        self.assertIn(k, report.ridge_applied_bins)
        self.assertEqual(report.rank_status, N.RANK_STATUS)

        variation = C.winding_variation(signal, _single_periodogram_gaussian, range(32), k)
        self.assertFalse(variation["varies_from_original"], msg=f"diagnostics={report}")
        self.assertEqual(set(variation["distinct_values"]), {variation["original_value"]})


class NearSingularMatrixTests(unittest.TestCase):
    def test_positive_near_singular_csd_is_finite_and_reported_as_effectively_rank_one(self):
        n = 8
        matrix = [
            [complex(1.0, 0.0), 0j],
            [0j, complex(1e-14, 0.0)],
        ]
        spectra, info = N.draw_from_csd(
            [matrix for _ in range(sp.n_freq(n))], n, seed=3, rank_tol=1e-10
        )

        self.assertEqual(info["effective_rank"], [1] * sp.n_freq(n))
        self.assertTrue(all(math.isinf(value) for value in info["condition"]))
        self.assertEqual(info["rank_deficient"], list(range(sp.n_freq(n))))
        self.assertEqual(info["ridge_applied"], list(range(sp.n_freq(n))))
        self.assertTrue(all(math.isfinite(value.real) and math.isfinite(value.imag)
                            for channel in spectra for value in channel))


class ShrunkenMultitaperTests(unittest.TestCase):
    def test_shrunken_full_rank_estimate_varies_relative_phase_and_reports_diagnostics(self):
        n, d, k = 32, 3, 4
        signal = _independent(n, d, 23)
        _, report = _shrunken_multitaper_gaussian(signal, 0)
        variation = C.relative_phase_spread(
            signal, _shrunken_multitaper_gaussian, range(24), k
        )

        self.assertTrue(variation["varies"], msg=f"diagnostics={report}")
        self.assertGreater(variation["max_spread"], 0.1)
        self.assertEqual(report.estimator, "multitaper")
        self.assertEqual(report.estimator_source, "estimated_from_input")
        self.assertEqual(report.n_tapers, 5)
        self.assertEqual(report.shrinkage, 0.2)
        self.assertEqual(report.estimator_dof_per_bin, tuple(10 for _ in range(sp.n_freq(n))))
        self.assertEqual(set(report.effective_rank_per_bin), {d})
        self.assertEqual(report.ridge_applied_bins, ())
        self.assertEqual(
            report.status["cross_spectrum"],
            "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
        )
        self.assertEqual(
            report.status["intended_use"],
            "SECOND_ORDER_GAUSSIAN_NULL_UNDER_STATIONARITY_AND_LINEAR_GAUSSIAN_MODEL",
        )


class EnsembleMomentTests(unittest.TestCase):
    def setUp(self):
        self.n = 16
        self.signal = _independent(self.n, 2, 37)
        self.target, _ = C.estimate_csd(
            self.signal, "multitaper", n_tapers=4, shrinkage=0.15
        )

    def test_gaussian_csd_moments_match_target_within_monte_carlo_error(self):
        samples = _sample_csd_ensemble(
            self.signal,
            N.cholesky_gaussian_csd,
            range(ENSEMBLE_SEEDS),
            estimator="multitaper",
            n_tapers=4,
            shrinkage=0.15,
        )
        _assert_mean_within_mc_error(self, samples, self.target, "Gaussian CSD")

    def test_real_part_null_matches_real_target_in_ensemble(self):
        real_target = [
            [[complex(value.real, 0.0) for value in row] for row in matrix]
            for matrix in self.target
        ]
        samples = _sample_csd_ensemble(
            self.signal,
            N.zero_lag_real_part_gaussian,
            range(ENSEMBLE_SEEDS),
            estimator="multitaper",
            n_tapers=4,
            shrinkage=0.15,
        )
        # The assertion is about the ensemble mean only, not every realization's phases.
        _assert_mean_within_mc_error(self, samples, real_target, "real-part CSD")


class ReportContractTests(unittest.TestCase):
    def test_reports_distinguish_exact_control_from_expectation_nulls(self):
        signal = _independent(16, 2, 11)
        _, control = N.common_phase_prichard_theiler(signal, 2)
        _, gaussian = N.cholesky_gaussian_csd(
            signal, 2, estimator="multitaper", n_tapers=4, shrinkage=0.1
        )
        _, real_part = N.zero_lag_real_part_gaussian(
            signal, 2, estimator="multitaper", n_tapers=4, shrinkage=0.1
        )

        self.assertEqual(control.null_id, "common_phase_prichard_theiler")
        self.assertEqual(control.status["role"], "CONTROL_DIAGNOSTIC_ONLY")
        self.assertEqual(control.status["same_frequency_relative_phase"], "PRESERVED_EXACT_BY_CONSTRUCTION")
        self.assertEqual(control.status["cross_spectrum"], "PRESERVED_EXACT_BY_CONSTRUCTION")

        self.assertEqual(gaussian.null_id, "cholesky_gaussian_csd")
        self.assertEqual(gaussian.status["cross_spectrum"], "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT")
        self.assertIn("linear-Gaussian", N.CONTRACTS["cholesky_gaussian_cross_spectral"]["intended_use"])
        self.assertIn("IN EXPECTATION", N.CONTRACTS["cholesky_gaussian_cross_spectral"]["preserved"])

        self.assertEqual(real_part.null_id, "zero_lag_real_part_gaussian")
        self.assertEqual(real_part.status["cross_spectrum_real_part"], "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT")
        self.assertEqual(
            real_part.status["intended_use"],
            "EXPLORATORY_ASSUMPTION_DEPENDENT_ZERO_LAG_REAL_PART_NULL",
        )
        self.assertIn("IN EXPECTATION", N.CONTRACTS["zero_lag_real_part_gaussian"]["preserved"])


class RealSignalSymmetryTests(unittest.TestCase):
    def test_generated_real_signals_have_conjugate_symmetric_spectra(self):
        n = 16
        signals, report = N.cholesky_gaussian_csd(
            _independent(n, 2, 5), 9, estimator="multitaper", n_tapers=4, shrinkage=0.1
        )
        self.assertEqual(report.dc_imag_discarded, 0.0)
        self.assertEqual(report.nyquist_imag_discarded, 0.0)

        for channel_index, channel in enumerate(signals):
            full = [
                sum(value * cmath.exp(-2j * math.pi * k * t / n) for t, value in enumerate(channel))
                for k in range(n)
            ]
            self.assertLess(abs(full[0].imag), 1e-10)
            self.assertLess(abs(full[n // 2].imag), 1e-10)
            for k in range(1, n // 2):
                self.assertLess(
                    abs(full[n - k] - full[k].conjugate()),
                    1e-10 * max(1.0, abs(full[k])),
                    msg=f"channel={channel_index}, bin={k}",
                )


if __name__ == "__main__":
    unittest.main()
