"""Tests for weighted Hodge-Helmholtz decomposition, orthogonality, and harmonic forms."""

import numpy as np
import pytest

from experimental.phase_cochain_reference.fixtures import (
    build_annulus_fixture,
    build_single_triangle_fixture,
    build_vortex_quad_fixture,
)
from experimental.phase_cochain_reference.hodge import compute_weighted_hodge_decomposition


def test_hodge_orthogonality_and_energy_conservation() -> None:
    """Verify weighted orthogonality and energy conservation across components."""
    c = build_vortex_quad_fixture()
    rng = np.random.default_rng(999)
    omega = rng.normal(size=c.num_edges)

    # Non-uniform positive metric weights
    w_e = rng.uniform(0.5, 2.5, size=c.num_edges)
    w_t = rng.uniform(0.5, 2.5, size=c.num_triangles)

    decomp = compute_weighted_hodge_decomposition(
        c,
        omega,
        weights_edges=w_e,
        weights_faces=w_t,
    )

    # Reconstruction identity
    assert decomp.relative_reconstruction_error < 1e-12

    # Weighted orthogonality: <u, v>_{W1} == 0
    assert abs(decomp.orthogonality_exact_coexact) < 1e-12
    assert abs(decomp.orthogonality_exact_harmonic) < 1e-12
    assert abs(decomp.orthogonality_coexact_harmonic) < 1e-12

    # Energy conservation: E_total == E_exact + E_coexact + E_harmonic
    assert decomp.relative_energy_error < 1e-12


def test_pure_gradient_signal() -> None:
    """A pure gradient omega = d0 @ alpha must decompose into exact component only."""
    c = build_annulus_fixture()
    rng = np.random.default_rng(42)
    alpha = rng.normal(size=c.num_vertices)
    omega_grad = c.d0 @ alpha

    decomp = compute_weighted_hodge_decomposition(c, omega_grad)

    assert np.allclose(decomp.exact, omega_grad, atol=1e-12)
    assert np.allclose(decomp.coexact, 0.0, atol=1e-12)
    assert np.allclose(decomp.harmonic, 0.0, atol=1e-12)

    assert decomp.energy_exact > 0.0
    assert decomp.energy_coexact < 1e-20
    assert decomp.energy_harmonic < 1e-20


def test_pure_solenoidal_signal_on_disk() -> None:
    """A pure curl on a contractible disk (b1=0) must decompose into coexact component only."""
    c = build_vortex_quad_fixture()
    rng = np.random.default_rng(77)
    beta = rng.normal(size=c.num_triangles)
    omega_curl = c.d1.T @ beta

    decomp = compute_weighted_hodge_decomposition(c, omega_curl)

    assert np.allclose(decomp.coexact, omega_curl, atol=1e-12)
    assert np.allclose(decomp.exact, 0.0, atol=1e-12)
    assert np.allclose(decomp.harmonic, 0.0, atol=1e-12)

    assert decomp.energy_coexact > 0.0
    assert decomp.energy_exact < 1e-20
    assert decomp.energy_harmonic < 1e-20


def test_annulus_non_trivial_harmonic_component() -> None:
    """An annulus (b1=1) supports non-trivial harmonic 1-forms with zero curl and zero divergence."""
    c = build_annulus_fixture()
    # The inner boundary cycle consists of edges (0, 1), (1, 2), (0, 2)
    # The outer boundary cycle consists of edges (3, 4), (4, 5), (3, 5)
    # Construct a circulating 1-form on the inner and outer cycles with zero divergence at all vertices
    omega_circ = np.zeros(c.num_edges, dtype=float)
    edge_map = c.edge_index_map

    # Flow along inner triangle: 0 -> 1 -> 2 -> 0
    # In canonical edges: (0, 1) is +1, (1, 2) is +1, (0, 2) is -1 (directed 0 -> 2, so opposite flow)
    omega_circ[edge_map[(0, 1)]] = 1.0
    omega_circ[edge_map[(1, 2)]] = 1.0
    omega_circ[edge_map[(0, 2)]] = -1.0

    # Flow along outer triangle: 3 -> 4 -> 5 -> 3
    omega_circ[edge_map[(3, 4)]] = 1.0
    omega_circ[edge_map[(4, 5)]] = 1.0
    omega_circ[edge_map[(3, 5)]] = -1.0

    # Check that divergence at every vertex is zero: delta1(omega) = d0.T @ omega == 0
    div = c.d0.T @ omega_circ
    assert np.allclose(div, 0.0)

    # Decompose under uniform metric weights
    decomp = compute_weighted_hodge_decomposition(c, omega_circ)

    # Because divergence is zero, exact component must be 0
    assert np.allclose(decomp.exact, 0.0, atol=1e-12)

    # Non-trivial harmonic component must carry significant energy
    assert decomp.energy_harmonic > 0.0
    assert decomp.relative_reconstruction_error < 1e-12
    assert decomp.relative_energy_error < 1e-12


def test_zero_signal_decomposition() -> None:
    """Decomposition of zero 1-form yields zero components and zero energies."""
    c = build_single_triangle_fixture()
    omega_zero = np.zeros(c.num_edges)

    decomp = compute_weighted_hodge_decomposition(c, omega_zero)
    assert np.allclose(decomp.exact, 0.0)
    assert np.allclose(decomp.coexact, 0.0)
    assert np.allclose(decomp.harmonic, 0.0)
    assert decomp.energy_total == 0.0
    assert decomp.relative_reconstruction_error == 0.0


def test_invalid_weights_and_inputs() -> None:
    """Decomposition must raise ValueError on negative/zero weights or non-finite inputs."""
    c = build_single_triangle_fixture()
    omega = np.ones(c.num_edges)

    # Non-positive edge weight
    with pytest.raises(ValueError, match="strictly positive"):
        compute_weighted_hodge_decomposition(c, omega, weights_edges=np.array([1.0, 0.0, 1.0]))

    # Non-positive face weight
    with pytest.raises(ValueError, match="strictly positive"):
        compute_weighted_hodge_decomposition(c, omega, weights_faces=np.array([-0.5]))

    # Non-finite omega
    with pytest.raises(ValueError, match="finite"):
        compute_weighted_hodge_decomposition(c, np.array([1.0, np.nan, 0.0]))
