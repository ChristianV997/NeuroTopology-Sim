"""Focused tests for oriented integer phase winding (synthetic only).

HOLD / SYNTHETIC_ONLY. Algebraic sensor-space fixtures only — not biological
vortex / cortical-wave evidence. ``d1 @ d0 == 0`` is a cochain identity check,
not a proof of valid planar embedding.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

import neurotopology_sim.experimental.topology.winding as winding_mod
from neurotopology_sim.experimental.topology.winding import (
    TWO_PI,
    ChargeMomentResult,
    WindingError,
    branch_index_floor,
    charge_moments,
    origin_shifted_moment,
    phase_winding,
    signed_first_moment,
)


def test_imports_real_implementation_not_skipped():
    """Guard: tests bind the production module path and are not skipped."""
    path = inspect.getfile(winding_mod)
    assert path.endswith("neurotopology_sim/experimental/topology/winding.py")
    assert inspect.isfunction(phase_winding)
    assert getattr(test_imports_real_implementation_not_skipped, "pytestmark", None) in (
        None,
        [],
    )


def _standard_triangle_incidence() -> tuple[np.ndarray, np.ndarray]:
    """Canonical oriented triangle: edges (0,1),(1,2),(0,2).

    d0: (d0 θ)_e = θ_v - θ_u for e=(u,v)
    d1: (d1 ω)_t = ω_01 + ω_12 - ω_02
    """
    d0 = np.array(
        [
            [-1, 1, 0],  # (0,1)
            [0, -1, 1],  # (1,2)
            [-1, 0, 1],  # (0,2)
        ],
        dtype=np.int64,
    )
    d1 = np.array([[1, 1, -1]], dtype=np.int64)
    return d0, d1


def _reversed_edge_orientation() -> tuple[np.ndarray, np.ndarray]:
    """Same triangle with edge (0,1) orientation reversed → edge list (1,0),(1,2),(0,2).

    d0 row 0 becomes θ_0 - θ_1; d1 coefficient for that edge flips sign.
    """
    d0 = np.array(
        [
            [1, -1, 0],  # (1,0): θ_0 - θ_1
            [0, -1, 1],  # (1,2)
            [-1, 0, 1],  # (0,2)
        ],
        dtype=np.int64,
    )
    # Boundary: -(1,0) + (1,2) - (0,2)  equivalently  ω_(0←1) term with −1 on first edge
    # Original: +ω_01 + ω_12 - ω_02; reversing (0,1) means ω_10 = -ω_01, so d1 uses −1 on edge0.
    d1 = np.array([[-1, 1, -1]], dtype=np.int64)
    return d0, d1


def test_cochain_identity_required():
    d0, d1 = _standard_triangle_incidence()
    assert np.array_equal(d1 @ d0, np.zeros((1, 3), dtype=np.int64))
    bad_d1 = np.array([[1, 1, 1]], dtype=np.int64)
    with pytest.raises(WindingError, match="incidence identity"):
        phase_winding([0.0, 0.0, 0.0], d0, bad_d1)


def test_ccw_unit_winding_positive():
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0])
    result = phase_winding(theta, d0, d1)
    assert result.face_charge.dtype == np.int64
    assert result.branch_index.dtype == np.int64
    assert result.face_charge.tolist() == [1]
    assert result.net_charge == 1
    assert result.identity_residual_max_abs < 1e-12
    # Continuous check: d1 @ omega ≈ 2π q
    circ = float(np.asarray(d1.astype(float) @ result.omega).reshape(()))
    assert abs(circ - TWO_PI) < 1e-12


def test_cw_unit_winding_negative():
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.0, -2.0 * np.pi / 3.0, 2.0 * np.pi / 3.0])
    result = phase_winding(theta, d0, d1)
    assert result.face_charge.tolist() == [-1]
    assert result.net_charge == -1


def test_ccw_alternate_representative():
    """θ with values already in (-π, π] still yields +1 for CCW ordering."""
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.0, 2.0 * np.pi / 3.0, -2.0 * np.pi / 3.0])
    result = phase_winding(theta, d0, d1)
    assert result.face_charge.tolist() == [1]


def test_global_phase_offsets_preserve_integer_winding():
    """Several global phase offsets leave integer plaquette winding unchanged.

    Algebraic gauge: θ → θ + φ·1 does not change D0@θ differences, hence q.
    """
    d0, d1 = _standard_triangle_incidence()
    base = np.array([0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0])
    offsets = (0.0, 0.3, -1.7, np.pi / 2.0, 2.0 * np.pi, -5.0 * np.pi / 3.0)
    charges = []
    for phi in offsets:
        result = phase_winding(base + phi, d0, d1)
        assert result.face_charge.dtype == np.int64
        assert result.face_charge.tolist() == [1]
        assert result.identity_residual_max_abs < 1e-10
        charges.append(int(result.net_charge))
    assert charges == [1] * len(offsets)


def test_reversed_edge_orientation_preserves_charge():
    d0_std, d1_std = _standard_triangle_incidence()
    d0_rev, d1_rev = _reversed_edge_orientation()
    assert np.array_equal(d1_rev @ d0_rev, np.zeros((1, 3), dtype=np.int64))
    theta = np.array([0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0])
    q_std = phase_winding(theta, d0_std, d1_std).face_charge
    q_rev = phase_winding(theta, d0_rev, d1_rev).face_charge
    assert q_std.tolist() == q_rev.tolist() == [1]


def test_branch_tie_at_plus_and_minus_pi():
    # Exact +π → n=1, omega=-π, flagged as tie
    n_plus, omega_plus = branch_index_floor([np.pi])
    assert int(n_plus[0]) == 1
    assert abs(float(omega_plus[0]) + np.pi) < 1e-15

    n_minus, omega_minus = branch_index_floor([-np.pi])
    assert int(n_minus[0]) == 0
    assert abs(float(omega_minus[0]) + np.pi) < 1e-15

    d0 = np.array([[-1, 1]], dtype=np.int64)
    d1 = np.zeros((0, 1), dtype=np.int64)
    # theta such that raw = +π
    theta = np.array([0.0, np.pi])
    result = phase_winding(theta, d0, d1, tie_tol=0.0)
    assert result.tie_edge_count == 1
    assert bool(result.tie_edge_mask[0]) is True

    # Exact −π raw difference also lands on the cut and is flagged.
    theta_m = np.array([np.pi, 0.0])  # raw = 0 - π = −π
    result_m = phase_winding(theta_m, d0, d1, tie_tol=0.0)
    assert float(result_m.raw_difference[0]) == pytest.approx(-np.pi)
    assert result_m.tie_edge_count == 1

    # Near-cut within tolerance: omega within tie_tol of −π must be flagged.
    eps = 5e-13
    theta_near = np.array([0.0, -np.pi + eps])  # raw ≈ −π + eps → omega ≈ −π + eps
    result_near = phase_winding(theta_near, d0, d1, tie_tol=1e-12)
    assert abs(float(result_near.omega[0]) + np.pi) <= 1e-12
    assert result_near.tie_edge_count == 1
    assert bool(result_near.tie_edge_mask[0]) is True

    # Comfortably interior edge is not flagged.
    theta_safe = np.array([0.0, 0.5])
    result_safe = phase_winding(theta_safe, d0, d1, tie_tol=1e-12)
    assert result_safe.tie_edge_count == 0


def test_winding_identity_d1_omega_equals_minus_2pi_d1_n():
    """Verify D1@omega = -2π (D1@n) and q = -D1@n (integer)."""
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0])
    result = phase_winding(theta, d0, d1)
    d1_f = d1.astype(float)
    lhs = d1_f @ result.omega
    rhs = -TWO_PI * (d1_f @ result.branch_index.astype(float))
    assert np.allclose(lhs, rhs, atol=1e-12)
    q_int = - (d1 @ result.branch_index)
    assert q_int.dtype == np.int64 or np.issubdtype(q_int.dtype, np.integer)
    assert np.array_equal(result.face_charge, q_int)
    assert result.face_charge.dtype == np.int64


def test_floor_convention_matches_mission_formula():
    raw = np.array([np.pi, -np.pi, 0.0, 3.0 * np.pi, -3.0 * np.pi / 2.0])
    n, omega = branch_index_floor(raw)
    expected_n = np.floor((raw + np.pi) / TWO_PI).astype(np.int64)
    assert np.array_equal(n, expected_n)
    assert np.all(omega >= -np.pi)
    assert np.all(omega < np.pi)


def test_zero_charge_smooth_field():
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.1, 0.2, 0.15])
    result = phase_winding(theta, d0, d1)
    assert result.face_charge.tolist() == [0]
    assert result.net_charge == 0
    assert result.abs_charge == 0
    assert result.d1_d0_residual_max_abs == 0.0


def test_rejects_malformed_shapes_and_nonfinite():
    d0, d1 = _standard_triangle_incidence()
    with pytest.raises(WindingError, match="vertex_phase length"):
        phase_winding([0.0, 1.0], d0, d1)
    with pytest.raises(WindingError, match="1-D"):
        phase_winding(np.zeros((3, 2)), d0, d1)
    with pytest.raises(WindingError, match="non-finite"):
        phase_winding([0.0, float("nan"), 0.0], d0, d1)
    with pytest.raises(WindingError, match="non-finite"):
        phase_winding([0.0, float("inf"), 0.0], d0, d1)
    with pytest.raises(WindingError, match="inconsistent edge"):
        phase_winding([0.0, 0.0, 0.0], d0, np.array([[1, 1]], dtype=np.int64))


def test_rejects_invalid_incidence_values():
    d0, d1 = _standard_triangle_incidence()
    bad = d0.astype(float)
    bad[0, 0] = 2.0
    with pytest.raises(WindingError, match="entries must lie"):
        phase_winding([0.0, 0.0, 0.0], bad, d1)
    bad2 = d0.astype(float)
    bad2[0, 0] = 0.5
    with pytest.raises(WindingError, match="integer-valued"):
        phase_winding([0.0, 0.0, 0.0], bad2, d1)
    with pytest.raises(WindingError, match="non-finite"):
        bad3 = d0.astype(float)
        bad3[0, 0] = float("nan")
        phase_winding([0.0, 0.0, 0.0], bad3, d1)


class _FakeSparse:
    """Minimal sparse-like duck type (no scipy install required)."""

    format = "csr"
    nnz = 3

    def tocsr(self):
        return self


def test_rejects_sparse_like_and_object_incidence():
    d0, d1 = _standard_triangle_incidence()
    with pytest.raises(WindingError, match="sparse"):
        phase_winding([0.0, 0.0, 0.0], _FakeSparse(), d1)
    with pytest.raises(WindingError, match="sparse"):
        phase_winding([0.0, 0.0, 0.0], d0, _FakeSparse())
    obj = np.empty((3, 3), dtype=object)
    obj[:] = 0
    with pytest.raises(WindingError, match="object|numeric"):
        phase_winding([0.0, 0.0, 0.0], obj, d1)
    with pytest.raises(WindingError, match="2-D dense"):
        phase_winding([0.0, 0.0, 0.0], np.array([1, 0, -1]), d1)


def test_rejects_unsupported_wrap_interval_and_negative_tie_tol():
    d0, d1 = _standard_triangle_incidence()
    with pytest.raises(WindingError, match="wrap_interval"):
        phase_winding([0.0, 0.0, 0.0], d0, d1, wrap_interval="(-pi,pi]")
    with pytest.raises(WindingError, match="tie_tol"):
        phase_winding([0.0, 0.0, 0.0], d0, d1, tie_tol=-1.0)


def test_origin_shift_moment_sign_independently_derived():
    """Derive p_q(a)=p_q(0)-Q_net*a from r'=r-a; do not accept by naming alone.

    Independent algebra:
        p(0) = Σ q_t r_t
        p(a) = Σ q_t (r_t - a) = p(0) - (Σ q_t) a
    So the minus sign is required under ORIGIN_SHIFT_COORDINATE_MAP = r' = r - a.
    """
    from neurotopology_sim.experimental.topology.winding import (
        ORIGIN_SHIFT_COORDINATE_MAP,
    )

    assert ORIGIN_SHIFT_COORDINATE_MAP == "r_prime = r - a"
    q = np.array([2, -1], dtype=np.int64)  # Q_net = +1
    r0 = np.array([[1.0, 0.0], [0.0, 1.0]])
    a = np.array([0.4, -0.2])
    p0 = signed_first_moment(q, r0)
    # Manual expansion of Σ q (r - a)
    p_manual = q[0] * (r0[0] - a) + q[1] * (r0[1] - a)
    p_via_coords = signed_first_moment(q, r0 - a)
    p_via_helper = origin_shifted_moment(p0, int(np.sum(q)), a)
    assert np.allclose(p_via_coords, p_manual)
    assert np.allclose(p_via_helper, p_manual)
    assert np.allclose(p_via_helper, p0 - float(np.sum(q)) * a)
    # Opposite convention a→−a would flip the correction sign — reject that here.
    assert not np.allclose(p_via_helper, p0 + float(np.sum(q)) * a)


def test_net_charge_and_origin_shift_identity():
    # Two-face dipole: +1 and -1
    # Face 0: verts 0,1,2 ; Face 1: verts 3,4,5
    d0 = np.zeros((6, 6), dtype=np.int64)
    edges = [(0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5)]
    for e_idx, (u, v) in enumerate(edges):
        d0[e_idx, v] = 1
        d0[e_idx, u] = -1
    d1 = np.zeros((2, 6), dtype=np.int64)
    d1[0, 0] = 1
    d1[0, 1] = 1
    d1[0, 2] = -1
    d1[1, 3] = 1
    d1[1, 4] = 1
    d1[1, 5] = -1
    assert np.array_equal(d1 @ d0, np.zeros((2, 6), dtype=np.int64))

    theta = np.array(
        [
            0.0,
            2.0 * np.pi / 3.0,
            4.0 * np.pi / 3.0,  # CCW → +1
            0.0,
            -2.0 * np.pi / 3.0,
            2.0 * np.pi / 3.0,  # CW → -1
        ]
    )
    result = phase_winding(theta, d0, d1)
    assert result.face_charge.tolist() == [1, -1]
    assert result.net_charge == 0
    assert result.abs_charge == 2

    bary = np.array([[-2.0, 0.0], [2.0, 0.0]], dtype=float)
    p0 = signed_first_moment(result.face_charge, bary)
    a = np.array([1.5, -0.25])
    # Recompute with shifted coords r' = r - a
    p_shifted = signed_first_moment(result.face_charge, bary - a)
    predicted = origin_shifted_moment(p0, result.net_charge, a)
    assert np.allclose(p_shifted, predicted)
    # With Q_net=0, moment is translation-invariant
    assert np.allclose(p_shifted, p0)

    # Nonzero net charge: single +1 face
    d0_1, d1_1 = _standard_triangle_incidence()
    theta_ccw = np.array([0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0])
    q = phase_winding(theta_ccw, d0_1, d1_1).face_charge
    bary1 = np.array([[0.5, math.sqrt(3) / 6.0]])
    p0_1 = signed_first_moment(q, bary1)
    a1 = np.array([0.3, -0.1])
    p_shift_1 = signed_first_moment(q, bary1 - a1)
    assert np.allclose(p_shift_1, origin_shifted_moment(p0_1, int(np.sum(q)), a1))
    assert np.allclose(p_shift_1, p0_1 - float(np.sum(q)) * a1)


def test_missing_sign_charge_separation_undefined():
    q_mono = np.array([1, 1, 0], dtype=np.int64)
    coords = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]])
    moments = charge_moments(q_mono, coords)
    assert isinstance(moments, ChargeMomentResult)
    assert moments.charge_separation_defined is False
    assert math.isnan(moments.charge_separation)
    assert moments.status == "undefined_separation"
    assert moments.negative_centroid is None
    assert moments.positive_centroid is not None

    q_zero = np.array([0, 0], dtype=np.int64)
    moments0 = charge_moments(q_zero, coords[:2])
    assert moments0.charge_separation_defined is False
    assert math.isnan(moments0.charge_separation)

    q_dipole = np.array([1, -1], dtype=np.int64)
    coords_d = np.array([[-2.0, 0.0], [2.0, 0.0]])
    moments_d = charge_moments(q_dipole, coords_d)
    assert moments_d.charge_separation_defined is True
    assert moments_d.charge_separation == pytest.approx(4.0)


def test_empty_faces_ok():
    d0 = np.array([[-1, 1]], dtype=np.int64)
    d1 = np.zeros((0, 1), dtype=np.int64)
    result = phase_winding([0.0, 0.5], d0, d1)
    assert result.face_charge.shape == (0,)
    assert result.net_charge == 0
    assert result.identity_residual_max_abs == 0.0


def test_omega_in_principal_interval():
    d0, d1 = _standard_triangle_incidence()
    rng = np.random.default_rng(0)
    for _ in range(20):
        theta = rng.uniform(-4 * np.pi, 4 * np.pi, size=3)
        result = phase_winding(theta, d0, d1)
        assert np.all(result.omega >= -np.pi)
        assert np.all(result.omega < np.pi)
        # Identity residual
        assert result.identity_residual_max_abs < 1e-10
