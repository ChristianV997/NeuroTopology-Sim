from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.polynomial import legendre as npl

from tools.mne_csd_reference_audit.legendre import (
    PROPOSAL_CONSTANTS,
    g_function,
    h_function,
    legendre_polynomials,
    numpy_crosscheck_coefficients,
)


# The brief gives each constant to 15 significant digits, so representation error alone is up to
# ~3.3e-15 relative (G(0) = -1.519e-4). 1e-14 leaves a factor of three over that. The bound is
# relative: an absolute bound admits ~1e-12 relative drift for H(0) ~ 9e-4.
@pytest.mark.parametrize("name", sorted(PROPOSAL_CONSTANTS))
def test_proposal_constant_matches_fifty_term_series(name):
    x, shift, claimed = PROPOSAL_CONSTANTS[name]
    fn = g_function if shift == 0 else h_function
    computed = float(fn(np.array([x]), 4.0, 50)[0])
    assert abs(computed - claimed) / abs(claimed) < 1e-14, (name, computed, claimed)


def test_recurrence_agrees_with_numpy_legval_on_the_same_formula():
    x = np.linspace(-1.0, 1.0, 41)
    for shift, fn in ((0, g_function), (1, h_function)):
        coeffs = numpy_crosscheck_coefficients(4.0, 50, shift)
        expected = npl.legval(x, coeffs)
        np.testing.assert_allclose(fn(x, 4.0, 50), expected, rtol=1e-12, atol=1e-18)


def test_low_order_polynomials_match_closed_forms():
    x = np.linspace(-1.0, 1.0, 17)
    polys = legendre_polynomials(3, x)
    np.testing.assert_allclose(polys[2], (3 * x**2 - 1) / 2, atol=1e-14)
    np.testing.assert_allclose(polys[3], (5 * x**3 - 3 * x) / 2, atol=1e-14)


def test_h_with_stiffness_m_equals_g_with_stiffness_m_minus_one():
    # h_m uses (n(n+1))^(m-1); g_{m-1} uses the same denominator. This is an identity of the formulas.
    x = np.linspace(-1.0, 1.0, 25)
    np.testing.assert_allclose(h_function(x, 4.0, 50), g_function(x, 3.0, 50), rtol=1e-13, atol=1e-18)


def test_fifty_term_truncation_is_part_of_the_h_constant():
    shift = h_function(np.array([1.0]), 4.0, 4000)[0] - h_function(np.array([1.0]), 4.0, 50)[0]
    assert 1e-9 < abs(shift) < 1e-8, shift


def test_h1_truncation_shift_matches_the_documented_relative_figure():
    # docs/mne_csd_reference_audit.md states H(1) moves ~1.8e-7 relative between N = 50 and N = 4000.
    # Measured 1.829e-7; the window allows for evaluation differences, not for a different claim.
    h50 = h_function(np.array([1.0]), 4.0, 50)[0]
    h4000 = h_function(np.array([1.0]), 4.0, 4000)[0]
    rel = abs(h4000 - h50) / abs(h50)
    assert 1.7e-7 < rel < 1.9e-7, rel


def _coefficients(shift: int, n_terms: int) -> list[float]:
    # MNE 1.13.2 _calc_g (shift 0) / _calc_h (shift 1), written here directly, not via the package.
    return [0.0] + [(2 * n + 1) / ((n * (n + 1)) ** (4 - shift) * 4.0 * math.pi) for n in range(1, n_terms + 1)]


def test_legendre_ode_links_package_h_to_the_laplacian_of_g():
    # G is evaluated from coefficients written here, not from the package. The sphere Laplacian of a function
    # of x = cos(theta) is (1 - x^2) f'' - 2 x f', and it maps P_n to -n(n+1) P_n. So -Lap G = H term by term,
    # with exponents m and m - 1. The package's H is compared against it, so an exponent error in h_function
    # fails here. The residual is rounding only: 2.2e-16 relative at N = 50 when measured.
    x = np.linspace(-0.999, 0.999, 401)
    cg = np.array(_coefficients(0, 50))
    lap_g = (1 - x**2) * npl.legval(x, npl.legder(cg, 2)) - 2 * x * npl.legval(x, npl.legder(cg, 1))
    h = h_function(x, 4.0, 50)
    assert np.max(np.abs(-lap_g - h)) / np.max(np.abs(h)) < 1e-13


def test_g_constant_is_insensitive_to_truncation_at_fifteen_digits():
    shift = g_function(np.array([1.0]), 4.0, 4000)[0] - g_function(np.array([1.0]), 4.0, 50)[0]
    assert abs(shift) < 1e-11, shift


@pytest.mark.parametrize("bad", [0, -1])
def test_non_positive_term_count_is_rejected(bad):
    with pytest.raises(ValueError):
        g_function(np.array([0.5]), 4.0, bad)


@pytest.mark.parametrize("bad", [np.nan, np.inf, 1.0 + 1e-6, -1.5])
def test_out_of_domain_arguments_are_rejected(bad):
    with pytest.raises(ValueError):
        legendre_polynomials(5, np.array([bad]))


def test_proposal_constants_are_finite_and_have_the_stated_signs():
    values = {k: v[2] for k, v in PROPOSAL_CONSTANTS.items()}
    assert all(math.isfinite(v) for v in values.values())
    assert values["G(1)"] > 0 and values["H(1)"] > 0
    assert values["G(0)"] < 0 and values["H(0)"] < 0
