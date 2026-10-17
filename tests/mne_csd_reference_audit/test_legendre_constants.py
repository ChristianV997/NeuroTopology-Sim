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


@pytest.mark.parametrize("name", sorted(PROPOSAL_CONSTANTS))
def test_proposal_constant_matches_fifty_term_series(name):
    x, shift, claimed = PROPOSAL_CONSTANTS[name]
    fn = g_function if shift == 0 else h_function
    computed = float(fn(np.array([x]), 4.0, 50)[0])
    assert abs(computed - claimed) < 1e-15, (name, computed, claimed)


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
