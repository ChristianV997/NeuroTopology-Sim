"""Tests for `sim/speculative/non_hermitian.py` -- offline, no network.

Cross-validation pattern: an independent QuTiP recomputation of quantities
`analysis/itct/itct_cessation_protocol_v3_full_stack.py` computes by hand
via `scipy.linalg.expm`, following this repo's existing
mne-connectivity-vs-hand-rolled-wPLI cross-validation discipline.
"""
from __future__ import annotations

import numpy as np
import pytest

from analysis.itct.itct_cessation_protocol_v3_full_stack import (
    exceptional_point_discriminant,
    synthetic_plv_series,
)
from sim.speculative.non_hermitian import (
    cross_validate_exceptional_point,
    cross_validate_loschmidt_echo,
    eigenvalue_gap_qutip,
    loschmidt_echo_qutip,
)


@pytest.fixture
def plv_matrix():
    series, _ = synthetic_plv_series(n_windows=1, n_channels=8, seed=0)
    return series[0]


# ── Loschmidt echo: QuTiP vs. hand-rolled scipy ──────────────────────────────

def test_loschmidt_echo_qutip_matches_scipy_reference(plv_matrix):
    result = cross_validate_loschmidt_echo(plv_matrix)
    assert result["agree"], f"scipy={result['scipy_value']} qutip={result['qutip_value']}"


def test_loschmidt_echo_qutip_matches_scipy_across_several_plv_matrices():
    for seed in range(5):
        series, _ = synthetic_plv_series(n_windows=1, n_channels=6, seed=seed)
        result = cross_validate_loschmidt_echo(series[0])
        assert result["difference"] < 1e-6, f"seed={seed}: {result}"


def test_loschmidt_echo_qutip_is_bounded_probability(plv_matrix):
    val = loschmidt_echo_qutip(plv_matrix)
    assert 0.0 <= val <= 1.0 + 1e-9


def test_loschmidt_echo_qutip_at_t_zero_is_one(plv_matrix):
    """At t=0, e^{-iHt} = identity, so the echo must be exactly 1."""
    val = loschmidt_echo_qutip(plv_matrix, t=0.0)
    assert val == pytest.approx(1.0, abs=1e-9)


def test_loschmidt_echo_qutip_varies_with_t(plv_matrix):
    v1 = loschmidt_echo_qutip(plv_matrix, t=0.5)
    v2 = loschmidt_echo_qutip(plv_matrix, t=3.0)
    assert v1 != pytest.approx(v2, abs=1e-6)


# ── Exceptional point: QuTiP eigenvalue-gap vs. discriminant formula ────────

def test_eigenvalue_gap_zero_at_analytically_derived_exceptional_point():
    result = cross_validate_exceptional_point(g1=0.2, g2=0.5)
    assert result["confirmed_exceptional_point"]
    assert result["eigenvalue_gap_at_ep"] < 1e-6


def test_eigenvalue_gap_nonzero_away_from_exceptional_point():
    """Sanity check that the gap metric is meaningful at all: away from the
    exceptional point (kappa=0, no coupling), the two eigenvalues must be
    distinct whenever g1 != g2."""
    gap = eigenvalue_gap_qutip(kappa=0.0, g1=0.2, g2=0.9)
    assert gap > 0.1


def test_exceptional_point_confirmed_across_several_gamma_pairs():
    for g1, g2 in [(0.1, 0.4), (0.05, 0.8), (0.3, 0.31), (0.0, 0.6)]:
        result = cross_validate_exceptional_point(g1=g1, g2=g2)
        assert result["confirmed_exceptional_point"], f"g1={g1}, g2={g2}: {result}"


def test_discriminant_formula_agrees_with_zero_at_derived_kappa():
    """The hand-rolled `exceptional_point_discriminant` itself (not just the
    QuTiP cross-check) must evaluate to (numerically) zero at the
    analytically derived exceptional-point kappa."""
    g1, g2, w0 = 0.2, 0.5, 1.0
    a, d = w0 - 1j * g1, w0 - 1j * g2
    kappa_ep = complex(np.sqrt(-((a - d) ** 2) / 4))
    discriminant = exceptional_point_discriminant(kappa_ep, g1, g2, w0)
    assert discriminant == pytest.approx(0.0, abs=1e-9)
