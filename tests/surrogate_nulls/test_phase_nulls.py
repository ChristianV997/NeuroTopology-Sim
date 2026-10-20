"""Common-phase and independent-phase nulls: what each preserves, and where each fails.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.
"""
from __future__ import annotations

import cmath
import math
import random
import unittest

from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp

TWO_PI = 2.0 * math.pi


def _correlated_pair(n, seed=7):
    rng = random.Random(seed)
    x0 = [rng.gauss(0.0, 1.0) for _ in range(n)]
    x1 = [0.7 * a + 0.5 * rng.gauss(0.0, 1.0) for a in x0]
    return [x0, x1]


def _winding(spectra, k):
    """Toy phase-loop winding at bin ``k`` for loop 0 -> 1 -> 2 -> 0 (test statistic only)."""
    phases = [cmath.phase(spectra[c][k]) for c in range(3)]
    total = 0.0
    for a, b in ((0, 1), (1, 2), (2, 0)):
        diff = phases[a] - phases[b]
        diff = (diff + math.pi) % TWO_PI - math.pi
        total += diff
    return round(total / TWO_PI)


def _wrapped_difference(a, b):
    diff = (a - b + math.pi) % TWO_PI - math.pi
    return abs(diff)


class CommonPhaseTests(unittest.TestCase):
    def setUp(self):
        self.n = 32
        self.x = _correlated_pair(self.n)

    def test_preserves_same_frequency_relative_phase_at_every_randomized_bin(self):
        original = [sp.rfft(c) for c in self.x]
        for seed in range(5):
            surrogate, _ = N.common_phase_prichard_theiler(self.x, seed)
            measured = [sp.rfft(s) for s in surrogate]
            for k in sp.randomized_bins(self.n):
                orig_rel = cmath.phase(original[0][k] * original[1][k].conjugate())
                surr_rel = cmath.phase(measured[0][k] * measured[1][k].conjugate())
                self.assertLess(_wrapped_difference(orig_rel, surr_rel), 1e-9, msg=f"seed {seed} bin {k}")

    def test_preserves_auto_and_cross_spectrum_exactly(self):
        surrogate, report = N.common_phase_prichard_theiler(self.x, 3)
        self.assertLess(max(report.auto_spectrum_rel_error), 1e-10)
        self.assertLess(report.cross_spectrum_rel_error, 1e-10)
        self.assertEqual(report.status["cross_spectrum"], "PRESERVED_EXACT_BY_CONSTRUCTION")

    def test_report_declares_it_invalid_for_winding_null(self):
        _, report = N.common_phase_prichard_theiler(self.x, 0)
        self.assertEqual(report.status["intended_use"], "INVALID_FOR_NARROWBAND_SPATIAL_WINDING_NULL")

    def test_marginal_is_not_claimed_as_preserved(self):
        _, report = N.common_phase_prichard_theiler(self.x, 0)
        self.assertEqual(report.status["marginal"], "NOT_PRESERVED_MEASURED")


class WindingFailureTests(unittest.TestCase):
    """Common phase must fail as a winding null: a designed winding survives every draw."""

    def setUp(self):
        self.n = 32
        self.k_wind = 3
        thetas = (0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0)
        self.x = [[math.cos(TWO_PI * self.k_wind * t / self.n + th) for t in range(self.n)] for th in thetas]

    def test_designed_winding_is_detected_on_original(self):
        spectra = [sp.rfft(c) for c in self.x]
        self.assertEqual(abs(_winding(spectra, self.k_wind)), 1)

    def test_common_phase_cannot_change_the_winding(self):
        original_w = _winding([sp.rfft(c) for c in self.x], self.k_wind)
        windings = set()
        for seed in range(40):
            surrogate, _ = N.common_phase_prichard_theiler(self.x, seed)
            windings.add(_winding([sp.rfft(s) for s in surrogate], self.k_wind))
        self.assertEqual(windings, {original_w})

    def test_independent_phase_does_randomise_the_winding(self):
        windings = set()
        for seed in range(40):
            surrogate, _ = N.independent_phase_univariate_ft(self.x, seed)
            windings.add(_winding([sp.rfft(s) for s in surrogate], self.k_wind))
        self.assertGreaterEqual(len(windings), 2)


class IndependentPhaseTests(unittest.TestCase):
    def setUp(self):
        self.n = 32

    def test_preserves_each_channel_power_exactly(self):
        x = _correlated_pair(self.n)
        _, report = N.independent_phase_univariate_ft(x, 2)
        self.assertLess(max(report.auto_spectrum_rel_error), 1e-10)

    def test_destroys_cross_spectrum_in_expectation(self):
        # Identical channels: the original cross-spectrum equals the auto-spectrum.
        base = [math.sin(TWO_PI * 2 * t / self.n) + 0.3 * math.cos(TWO_PI * 5 * t / self.n) for t in range(self.n)]
        x = [base, list(base)]
        original = sp.periodogram_csd([sp.rfft(c) for c in x], self.n)
        seeds = 300
        mean = [[[0j, 0j], [0j, 0j]] for _ in range(len(original))]
        for seed in range(seeds):
            surrogate, _ = N.independent_phase_univariate_ft(x, seed)
            raw = sp.periodogram_csd([sp.rfft(s) for s in surrogate], self.n)
            for k in range(len(raw)):
                for i in range(2):
                    for j in range(2):
                        mean[k][i][j] += raw[k][i][j] / seeds
        numerator = sum(abs(mean[k][0][1]) for k in range(len(original)))
        denominator = sum(abs(original[k][0][1]) for k in range(len(original)))
        self.assertLess(numerator / denominator, 0.25)

    def test_report_declares_a_weaker_null_and_not_volume_conduction_preserving(self):
        x = _correlated_pair(self.n)
        _, report = N.independent_phase_univariate_ft(x, 0)
        self.assertEqual(report.status["intended_use"], "DIFFERENT_AND_POSSIBLY_TOO_WEAK_NULL")
        self.assertTrue(any("not a volume-conduction-preserving null" in note for note in report.notes))


if __name__ == "__main__":
    unittest.main()
