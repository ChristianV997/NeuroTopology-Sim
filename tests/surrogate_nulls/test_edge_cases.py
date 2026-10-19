"""Edge cases for the surrogate-null vertical: shapes, bins, input validation, reproducibility.

Synthetic arrays only. Deterministic seeds. No subprocess, network, or dataset access.
"""
from __future__ import annotations

import math
import pathlib
import random
import unittest

from tools.surrogate_nulls import nulls as N
from tools.surrogate_nulls import spectral as sp

_PKG = pathlib.Path(__file__).resolve().parents[2] / "tools" / "surrogate_nulls"


def _pair(n, seed=7):
    rng = random.Random(seed)
    x0 = [rng.gauss(0.0, 1.0) for _ in range(n)]
    x1 = [0.7 * a + 0.5 * rng.gauss(0.0, 1.0) for a in x0]
    return [x0, x1]


class BinSetTests(unittest.TestCase):
    def test_even_length_randomized_and_fixed_bins(self):
        self.assertEqual(sp.randomized_bins(8), [1, 2, 3])
        self.assertEqual(sp.fixed_bins(8), [0, 4])

    def test_odd_length_randomized_and_fixed_bins(self):
        self.assertEqual(sp.randomized_bins(7), [1, 2, 3])
        self.assertEqual(sp.fixed_bins(7), [0])

    def test_tiny_lengths(self):
        self.assertEqual(sp.randomized_bins(1), [])
        self.assertEqual(sp.fixed_bins(1), [0])
        self.assertEqual(sp.randomized_bins(2), [])
        self.assertEqual(sp.fixed_bins(2), [0, 1])


class SpectralConventionTests(unittest.TestCase):
    def test_round_trip_is_exact_for_several_lengths(self):
        rng = random.Random(1)
        for n in (1, 2, 3, 7, 8, 9, 16):
            x = [rng.gauss(0.0, 1.0) for _ in range(n)]
            y, discarded = sp.irfft(sp.rfft(x), n)
            self.assertLess(max(abs(a - b) for a, b in zip(x, y)), 1e-12, msg=f"n={n}")
            self.assertLess(discarded["dc_imag"], 1e-12)
            self.assertLess(discarded["nyquist_imag"], 1e-12)

    def test_dc_imaginary_part_is_discarded_and_reported(self):
        spectrum = sp.rfft([1.0, 2.0, 3.0, 4.0])
        spectrum[0] = complex(spectrum[0].real, 5.0)
        y, discarded = sp.irfft(spectrum, 4)
        self.assertEqual(discarded["dc_imag"], 5.0)
        self.assertTrue(all(isinstance(v, float) for v in y))

    def test_nyquist_imaginary_part_is_discarded_and_reported(self):
        spectrum = sp.rfft([1.0, 2.0, 3.0, 4.0])
        spectrum[2] = complex(spectrum[2].real, -3.0)
        _, discarded = sp.irfft(spectrum, 4)
        self.assertEqual(discarded["nyquist_imag"], 3.0)

    def test_irfft_rejects_wrong_bin_count(self):
        with self.assertRaises(sp.SurrogateInputError):
            sp.irfft([0j, 0j], 8)


class OneChannelAndOneSampleTests(unittest.TestCase):
    def test_one_channel_runs_for_every_null_and_has_no_cross_spectrum(self):
        x = [[math.sin(0.3 * t) + 0.1 * t for t in range(16)]]
        for name in N.NULL_IDS:
            surrogate, report = N.GENERATORS[name](x, 2)
            self.assertEqual(len(surrogate), 1, msg=name)
            self.assertEqual(len(surrogate[0]), 16, msg=name)
            self.assertIsNone(report.cross_spectrum_rel_error, msg=name)

    def test_one_sample_is_identity_for_the_deterministic_nulls(self):
        x = [[1.25], [-0.5]]
        for name in ("common_phase_prichard_theiler", "independent_phase_univariate_ft", "mv_iaaft_rank_adjusted"):
            surrogate, _ = N.GENERATORS[name](x, 0)
            self.assertEqual(len(surrogate[0]), 1, msg=name)
            for got, want in zip(surrogate, x):
                self.assertAlmostEqual(got[0], want[0], places=12, msg=name)

    def test_one_sample_cholesky_draws_finite_values(self):
        surrogate, report = N.cholesky_gaussian_cross_spectral([[1.25], [-0.5]], 0)
        self.assertTrue(all(math.isfinite(row[0]) for row in surrogate))
        self.assertEqual(report.randomized_bins, ())


class InputValidationTests(unittest.TestCase):
    def test_non_finite_values_are_rejected_by_every_null(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            x = [[0.0, bad, 1.0, 2.0], [1.0, 2.0, 3.0, 4.0]]
            for name in N.NULL_IDS:
                with self.assertRaises(sp.SurrogateInputError, msg=f"{name} {bad}"):
                    N.GENERATORS[name](x, 0)

    def test_bool_and_complex_samples_are_rejected(self):
        for bad in (True, 1 + 2j):
            x = [[0.0, bad, 1.0, 2.0], [1.0, 2.0, 3.0, 4.0]]
            with self.assertRaises(sp.SurrogateInputError):
                N.common_phase_prichard_theiler(x, 0)

    def test_ragged_and_empty_inputs_are_rejected(self):
        with self.assertRaises(sp.SurrogateInputError):
            N.common_phase_prichard_theiler([[1.0, 2.0], [1.0]], 0)
        with self.assertRaises(sp.SurrogateInputError):
            N.common_phase_prichard_theiler([], 0)
        with self.assertRaises(sp.SurrogateInputError):
            N.common_phase_prichard_theiler([[]], 0)
        with self.assertRaises(sp.SurrogateInputError):
            N.common_phase_prichard_theiler("abc", 0)

    def test_seed_must_be_an_integer(self):
        x = _pair(8)
        for bad in (1.5, True, "3", None):
            with self.assertRaises(sp.SurrogateInputError, msg=repr(bad)):
                N.common_phase_prichard_theiler(x, bad)

    def test_parameter_validation(self):
        x = _pair(8)
        with self.assertRaises(sp.SurrogateInputError):
            N.cholesky_gaussian_cross_spectral(x, 0, smoothing_halfwidth=-1)
        with self.assertRaises(sp.SurrogateInputError):
            N.cholesky_gaussian_cross_spectral(x, 0, ridge_rel=-1e-3)
        with self.assertRaises(sp.SurrogateInputError):
            N.cholesky_gaussian_cross_spectral(x, 0, ridge_rel=float("nan"))
        with self.assertRaises(sp.SurrogateInputError):
            N.mv_iaaft_rank_adjusted(x, 0, max_iter=0)

    def test_draw_from_csd_checks_sample_count(self):
        ok = [[complex(1.0, 0.0), complex(0.0, 0.0)], [complex(0.0, 0.0), complex(1.0, 0.0)]]
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([ok], 0, 0)
        with self.assertRaises(sp.SurrogateInputError):
            N.draw_from_csd([ok, ok], 8, 0)  # 8 samples need 5 bins


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_reproduces_every_null(self):
        x = _pair(16)
        for name in N.NULL_IDS:
            a, _ = N.GENERATORS[name](x, 11)
            b, _ = N.GENERATORS[name](x, 11)
            self.assertEqual(a, b, msg=name)

    def test_different_seeds_change_the_randomised_nulls(self):
        x = _pair(16)
        for name in ("common_phase_prichard_theiler", "independent_phase_univariate_ft",
                     "cholesky_gaussian_cross_spectral"):
            a, _ = N.GENERATORS[name](x, 11)
            b, _ = N.GENERATORS[name](x, 12)
            self.assertNotEqual(a, b, msg=name)


class StaticBoundaryTests(unittest.TestCase):
    """The core must not reach subprocess, network, or dataset code."""

    FORBIDDEN = ("subprocess", "socket", "urllib", "http.client", "requests", "scipy", "numpy", "os.system")

    def test_no_forbidden_imports_in_the_package(self):
        for path in _PKG.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in self.FORBIDDEN:
                self.assertNotIn(f"import {token}", text, msg=f"{path.name} imports {token}")
                self.assertNotIn(f"from {token}", text, msg=f"{path.name} imports from {token}")


class HermitianScaleTests(unittest.TestCase):
    """Hermitian symmetry is judged relative to the matrix's own largest entry."""

    def test_small_scale_asymmetry_is_rejected(self):
        s = 1e-20
        m = [[complex(s), complex(s, 0.5 * s)], [complex(s, 0.5 * s), complex(s)]]
        self.assertFalse(sp.is_hermitian(m))

    def test_small_scale_hermitian_matrix_is_accepted(self):
        s = 1e-20
        m = [[complex(s), complex(s, 0.5 * s)], [complex(s, -0.5 * s), complex(s)]]
        self.assertTrue(sp.is_hermitian(m))

    def test_unit_scale_tolerance_is_unchanged(self):
        ok = [[1.0, complex(1.0, 1e-10)], [complex(1.0, -1e-10), 1.0]]
        bad = [[1.0, complex(1.0, 1e-8)], [complex(1.0, -1e-9), 1.0]]
        self.assertTrue(sp.is_hermitian(ok))
        self.assertFalse(sp.is_hermitian(bad))

    def test_zero_matrix_is_hermitian(self):
        self.assertTrue(sp.is_hermitian([[0j, 0j], [0j, 0j]]))

    def test_cholesky_rejects_non_hermitian_and_non_square_input(self):
        with self.assertRaises(sp.SurrogateInputError):
            sp.cholesky_hermitian([[1 + 0j, 0.5 + 0j], [0j, 1 + 0j]])
        with self.assertRaises(sp.SurrogateInputError):
            sp.cholesky_hermitian([[1 + 0j, 0j]])

    def test_cholesky_factor_reproduces_a_small_scale_matrix(self):
        s = 1e-20
        m = [[complex(2 * s), complex(s, 0.5 * s)], [complex(s, -0.5 * s), complex(s)]]
        factor = sp.cholesky_hermitian(m)
        for i in range(2):
            for j in range(2):
                got = sum(factor[i][k] * factor[j][k].conjugate() for k in range(2))
                self.assertLess(abs(got - m[i][j]), 1e-12 * s, msg=f"({i},{j})")


if __name__ == "__main__":
    unittest.main()
