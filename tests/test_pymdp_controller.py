"""Tests for the speculative pymdp active-inference controller.

These test the REAL variational-free-energy computation (via pymdp), plus the
firewall obligations that keep this module in the speculative track.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_HAVE_PYMDP = importlib.util.find_spec("pymdp") is not None
pytestmark = pytest.mark.skipif(not _HAVE_PYMDP, reason="requires inferactively-pymdp")


def test_rigid_prior_pays_more_free_energy_than_flexible_under_surprise():
    from sim.speculative.pymdp_controller import variational_free_energy

    A = np.array([[0.9, 0.1], [0.1, 0.9]])  # P(o|s)
    # observe outcome 1 (surprising for a prior concentrated on state 0)
    rigid = variational_free_energy(A, 1, np.array([0.95, 0.05]))
    flexible = variational_free_energy(A, 1, np.array([0.5, 0.5]))
    assert rigid.variational_free_energy > flexible.variational_free_energy


def test_free_energy_monotone_in_prior_precision_under_surprise():
    from sim.speculative.pymdp_controller import prior_cost_gradient, rigidity_increases_free_energy_under_surprise

    results = prior_cost_gradient()
    f = [r.variational_free_energy for r in results]
    assert f == sorted(f)  # non-decreasing
    assert rigidity_increases_free_energy_under_surprise() is True


def test_posterior_is_a_valid_distribution():
    from sim.speculative.pymdp_controller import variational_free_energy

    A = np.array([[0.8, 0.2], [0.2, 0.8]])
    r = variational_free_energy(A, 0, np.array([0.5, 0.5]))
    assert abs(sum(r.posterior) - 1.0) < 1e-6
    assert all(0.0 <= p <= 1.0 for p in r.posterior)


def test_report_carries_banner_and_passes_guardrails():
    from sim.speculative import SPECULATIVE_BANNER, validate_speculative_text
    from sim.speculative.pymdp_controller import render_report

    text = render_report()
    assert SPECULATIVE_BANNER in text
    validate_speculative_text(text)  # raises if a banned phrase slipped in
    # no consciousness/biology overclaim in the rendered text
    low = text.lower()
    for banned in ("proves consciousness", "enlightenment", "nirvana", "liberation detected"):
        assert banned not in low
