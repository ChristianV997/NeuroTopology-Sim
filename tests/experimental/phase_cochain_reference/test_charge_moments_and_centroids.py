"""Tests for charge moments, centroids, shift-invariance identities, and dipole separation."""

import numpy as np

from experimental.phase_cochain_reference.cochain import compute_charge_moments
from experimental.phase_cochain_reference.complex import SimplicialComplex
from experimental.phase_cochain_reference.fixtures import (
    build_dipole_complex_fixture,
    build_single_triangle_fixture,
    build_vortex_quad_fixture,
)


def test_zero_charges_produce_none_centroids() -> None:
    """When all charges are zero, centroids and separation must be None, not 0.0."""
    c = build_vortex_quad_fixture()
    zero_charges = np.zeros(c.num_triangles, dtype=int)

    summary = compute_charge_moments(c, zero_charges)
    assert summary.net_charge == 0
    assert summary.abs_charge == 0
    assert summary.positive_charge_count == 0
    assert summary.negative_charge_count == 0
    assert summary.magnitude_centroid is None
    assert summary.positive_centroid is None
    assert summary.negative_centroid is None
    assert summary.positive_negative_separation is None
    assert not summary.is_dipole_separated


def test_monopolar_separation_guardrail() -> None:
    """Monopolar charge distributions MUST return None for separation, never 0.0."""
    c = build_single_triangle_fixture()

    # Pure positive charge
    summary_pos = compute_charge_moments(c, np.array([1]))
    assert summary_pos.positive_centroid is not None
    assert summary_pos.negative_centroid is None
    assert summary_pos.positive_negative_separation is None
    assert not summary_pos.is_dipole_separated

    # Pure negative charge
    summary_neg = compute_charge_moments(c, np.array([-1]))
    assert summary_neg.positive_centroid is None
    assert summary_neg.negative_centroid is not None
    assert summary_neg.positive_negative_separation is None
    assert not summary_neg.is_dipole_separated


def test_dipole_fixture_moments_and_separation() -> None:
    """Dipole fixture with q=(+1, -1) separated by distance d=4.0."""
    sep = 4.0
    c = build_dipole_complex_fixture(separation_distance=sep)
    charges = np.array([1, -1], dtype=int)

    summary = compute_charge_moments(c, charges)
    assert summary.net_charge == 0
    assert summary.abs_charge == 2
    assert summary.positive_charge_count == 1
    assert summary.negative_charge_count == 1
    assert summary.is_dipole_separated

    assert summary.positive_negative_separation is not None
    assert np.isclose(summary.positive_negative_separation, sep)

    # Check barycenters
    barys = c.triangle_barycenters()
    assert summary.positive_centroid is not None
    assert summary.negative_centroid is not None
    assert np.allclose(summary.positive_centroid, barys[0])
    assert np.allclose(summary.negative_centroid, barys[1])


def test_signed_first_moment_translation_identity() -> None:
    """Verify origin-shift identity: m(r + v) = m(r) + Q_net * v."""
    c = build_dipole_complex_fixture(separation_distance=4.0)
    assert c.coordinates is not None

    shift_v = np.array([10.5, -23.4])
    c_shifted = SimplicialComplex(
        num_vertices=c.num_vertices,
        edges=c.edges,
        triangles=c.triangles,
        coordinates=c.coordinates + shift_v,
    )

    # 1. Neutral dipole case: Q_net == 0 => strictly translation invariant
    charges_neutral = np.array([1, -1], dtype=int)
    m_orig = compute_charge_moments(c, charges_neutral).signed_first_moment
    m_shift = compute_charge_moments(c_shifted, charges_neutral).signed_first_moment
    assert m_orig is not None and m_shift is not None
    assert np.allclose(m_shift, m_orig)

    # 2. Non-neutral case: Q_net == 1
    charges_net1 = np.array([1, 0], dtype=int)
    m1_orig = compute_charge_moments(c, charges_net1).signed_first_moment
    m1_shift = compute_charge_moments(c_shifted, charges_net1).signed_first_moment
    assert m1_orig is not None and m1_shift is not None
    expected_shifted = m1_orig + 1 * shift_v
    assert np.allclose(m1_shift, expected_shifted)


def test_complex_without_coordinates() -> None:
    """A complex without coordinates should return counts and None for spatial metrics."""
    c = SimplicialComplex(
        num_vertices=3,
        edges=((0, 1), (1, 2), (0, 2)),
        triangles=((0, 1, 2),),
        coordinates=None,
    )
    summary = compute_charge_moments(c, np.array([1]))
    assert summary.net_charge == 1
    assert summary.abs_charge == 1
    assert summary.magnitude_centroid is None
    assert summary.positive_centroid is None
    assert summary.negative_centroid is None
    assert summary.signed_first_moment is None
    assert summary.positive_negative_separation is None
    assert not summary.is_dipole_separated
