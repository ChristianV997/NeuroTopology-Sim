"""Tests for wrapped phase differences, branch jumps, topological charges, and orientation covariance."""

import numpy as np
import pytest

from experimental.phase_cochain_reference.cochain import (
    compute_confidence_weighted_scores,
    compute_topological_charges,
    compute_triangle_loop_winding,
    compute_wrapped_1_cochain,
    wrap_to_pi,
)
from experimental.phase_cochain_reference.fixtures import (
    build_annulus_fixture,
    build_single_triangle_fixture,
    build_vortex_quad_fixture,
)


def test_wrap_to_pi_scalar_and_array() -> None:
    """Test principal value phase wrapping to [-pi, pi)."""
    assert np.isclose(wrap_to_pi(0.0), 0.0)
    assert np.isclose(wrap_to_pi(np.pi), -np.pi)
    assert np.isclose(wrap_to_pi(-np.pi), -np.pi)
    assert np.isclose(wrap_to_pi(2.0 * np.pi), 0.0)
    assert np.isclose(wrap_to_pi(3.0 * np.pi), -np.pi)
    assert np.isclose(wrap_to_pi(np.pi / 2.0), np.pi / 2.0)
    assert np.isclose(wrap_to_pi(-3.0 * np.pi / 2.0), np.pi / 2.0)

    arr = np.array([0.0, np.pi / 2.0, np.pi, -3.0 * np.pi / 2.0, 4.0 * np.pi])
    wrapped = wrap_to_pi(arr)
    expected = np.array([0.0, np.pi / 2.0, -np.pi, np.pi / 2.0, 0.0])
    assert np.allclose(wrapped, expected)
    assert np.all(wrapped >= -np.pi) and np.all(wrapped < np.pi)


def test_wrapped_1_cochain_half_turn_stays_in_principal_branch() -> None:
    """Regression: raw edge difference exactly +π must not leave omega=+π (outside [-π, π)).

    ``np.rint(0.5)`` is banker's-round-to-even (0), so ``n=round(raw/2π)`` alone
    leaves omega=+π. Principal-branch wrapping must map this to omega=-π, n=+1.
    """
    c = build_single_triangle_fixture()
    # Edge (0,1) has raw = θ1 - θ0 = +π
    theta = np.array([0.0, np.pi, 0.0])
    w1 = compute_wrapped_1_cochain(c, theta)
    assert np.all(w1.cochain >= -np.pi - 1e-15)
    assert np.all(w1.cochain < np.pi)  # strict: +π is not in [-π, π)
    e01 = c.edge_index_map[(0, 1)]
    assert w1.branch_jumps[e01] == 1
    assert np.isclose(w1.cochain[e01], -np.pi)
    assert np.allclose(w1.cochain, w1.raw_difference - 2.0 * np.pi * w1.branch_jumps)


def test_wrapped_1_cochain_identity() -> None:
    """Verify that wrapped 1-cochain satisfies omega = d0 @ theta - 2pi * n with omega in [-pi, pi)."""
    c = build_vortex_quad_fixture()
    rng = np.random.default_rng(42)
    theta = rng.uniform(-5.0 * np.pi, 5.0 * np.pi, size=c.num_vertices)

    w1 = compute_wrapped_1_cochain(c, theta)
    reconstructed = w1.raw_difference - 2.0 * np.pi * w1.branch_jumps

    assert np.allclose(w1.cochain, reconstructed)
    assert np.all(w1.cochain >= -np.pi - 1e-12)
    assert np.all(w1.cochain < np.pi)  # strict upper bound
    assert np.issubdtype(w1.branch_jumps.dtype, np.integer)


def test_topological_charges_exact_integer_theorem() -> None:
    """Verify that q = -d1 @ n matches continuous circulation d1(omega) / (2pi) exactly."""
    c = build_annulus_fixture()
    rng = np.random.default_rng(123)
    theta = rng.uniform(-np.pi, np.pi, size=c.num_vertices)

    w1 = compute_wrapped_1_cochain(c, theta)
    q = compute_topological_charges(c, w1)

    assert np.issubdtype(q.dtype, np.integer)
    assert q.shape == (c.num_triangles,)

    # Verify each triangle charge is strictly integer
    circ = (c.d1 @ w1.cochain) / (2.0 * np.pi)
    assert np.allclose(circ, q, atol=1e-12)


def test_uniform_and_linear_phase_zero_charges() -> None:
    """Uniform phase and small linear phase gradients must yield zero topological charge."""
    c = build_vortex_quad_fixture()

    # Uniform phase
    theta_uniform = np.full(c.num_vertices, 1.234)
    w1_u = compute_wrapped_1_cochain(c, theta_uniform)
    q_u = compute_topological_charges(c, w1_u)
    assert np.all(q_u == 0)

    # Linear gradient (curl-free)
    coords = c.coordinates
    assert coords is not None
    k = np.array([0.2, -0.1])
    theta_linear = coords @ k
    w1_l = compute_wrapped_1_cochain(c, theta_linear)
    q_l = compute_topological_charges(c, w1_l)
    assert np.all(q_l == 0)


def test_single_vortex_and_antivortex() -> None:
    """Single triangle carries exact +1 vortex or -1 antivortex."""
    c = build_single_triangle_fixture()

    # Vortex phases (+1)
    theta_vortex = np.array([0.0, 2.0 * np.pi / 3.0, -2.0 * np.pi / 3.0])
    w1_v = compute_wrapped_1_cochain(c, theta_vortex)
    q_v = compute_topological_charges(c, w1_v)
    assert q_v[0] == 1

    # Antivortex phases (-1)
    theta_antivortex = np.array([0.0, -2.0 * np.pi / 3.0, 2.0 * np.pi / 3.0])
    w1_av = compute_wrapped_1_cochain(c, theta_antivortex)
    q_av = compute_topological_charges(c, w1_av)
    assert q_av[0] == -1


def test_triangle_loop_winding_orientation_covariance() -> None:
    """Even permutations preserve loop winding; odd permutations negate loop winding."""
    phases = np.array([0.0, 2.0 * np.pi / 3.0, -2.0 * np.pi / 3.0])

    # Canonical order
    w_012 = compute_triangle_loop_winding(phases, (0, 1, 2))
    assert w_012 == 1

    # Even (cyclic) permutations
    w_120 = compute_triangle_loop_winding(phases, (1, 2, 0))
    w_201 = compute_triangle_loop_winding(phases, (2, 0, 1))
    assert w_120 == 1
    assert w_201 == 1

    # Odd permutations (reversals)
    w_021 = compute_triangle_loop_winding(phases, (0, 2, 1))
    w_210 = compute_triangle_loop_winding(phases, (2, 1, 0))
    w_102 = compute_triangle_loop_winding(phases, (1, 0, 2))
    assert w_021 == -1
    assert w_210 == -1
    assert w_102 == -1


def test_triangle_loop_winding_matches_coboundary_at_half_turn_cut() -> None:
    """Regression: naive wrap(θ_a-θ_c) disagrees with q=-d1@n when an edge hits -π.

    Phases [0, 0, 3π] put edges (0,2) and (1,2) on the principal-branch cut.
    ``wrap(-x)`` is not ``-wrap(x)`` there, so summing three independent wraps
    yields winding -1 while the coboundary integer charge is 0. Loop winding
    must use canonical edge branch jumps (same as ``compute_topological_charges``).
    """
    c = build_single_triangle_fixture()
    theta = np.array([0.0, 0.0, 3.0 * np.pi])
    q = int(compute_topological_charges(c, compute_wrapped_1_cochain(c, theta))[0])
    assert q == 0
    assert compute_triangle_loop_winding(theta, (0, 1, 2)) == q
    assert compute_triangle_loop_winding(theta, (1, 2, 0)) == q
    assert compute_triangle_loop_winding(theta, (2, 0, 1)) == q
    assert compute_triangle_loop_winding(theta, (0, 2, 1)) == -q


def test_confidence_weighted_scores() -> None:
    """Confidence weights scale scores without altering raw integer charges."""
    charges = np.array([1, -1, 0, 2], dtype=np.int64)
    weights = np.array([0.8, 0.5, 1.0, 0.25])

    scores = compute_confidence_weighted_scores(charges, weights)
    expected = np.array([0.8, -0.5, 0.0, 0.5])

    assert np.allclose(scores, expected)
    # Raw charges remain integer
    assert np.issubdtype(charges.dtype, np.integer)
    assert np.array_equal(charges, np.array([1, -1, 0, 2]))

    # Error handling on invalid weights
    with pytest.raises(ValueError, match="strictly positive"):
        compute_confidence_weighted_scores(charges, np.array([0.8, -0.1, 1.0, 0.25]))
    with pytest.raises(ValueError, match="strictly positive"):
        compute_confidence_weighted_scores(charges, np.array([0.8, 0.0, 1.0, 0.25]))
