"""Unit tests for production weighted 2D discrete Hodge-Helmholtz decomposition.

HOLD / SYNTHETIC_ONLY
=====================
Validates algebraic identities, energy closure, orthogonality, boundary conditions,
gauge invariance, and conditioning diagnostics on synthetic oriented 2-complexes.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from neurotopology_sim.experimental.topology.hodge_2d import (
    BoundaryCondition,
    BoundaryConditionError,
    CochainComplexError,
    GaugePolicy,
    HodgeError,
    HodgeResult,
    IllConditionedMetricError,
    MetricError,
    MetricType,
    detect_boundary_elements,
    effective_condition_number,
    hodge_decompose,
    validate_cochain_complex,
    validate_edge_metric,
    weighted_inner_product,
    weighted_norm_sq,
)


# -----------------------------------------------------------------------------
# Fixtures: Tiny oriented 2-complexes
# -----------------------------------------------------------------------------

def fixture_single_triangle():
    r"""Single oriented triangle (open disk with boundary, 0 interior nodes).

    Vertices: 0, 1, 2
    Edges:
        e0: 0 -> 1
        e1: 1 -> 2
        e2: 0 -> 2
    Face:
        f0: boundary [e0, e1, -e2]
    """
    d0 = np.array([
        [-1,  1,  0],  # e0
        [ 0, -1,  1],  # e1
        [-1,  0,  1],  # e2
    ], dtype=float)

    d1 = np.array([
        [1, 1, -1],    # f0
    ], dtype=float)

    return d0, d1


def fixture_quad_fan():
    r"""Quad fan with 1 interior node and 4 boundary nodes.

    Center: vertex 0 (interior)
    Rim: vertices 1, 2, 3, 4 (boundary)
    Edges:
        spokes: e0 (0->1), e1 (0->2), e2 (0->3), e3 (0->4)
        rim:    e4 (1->2), e5 (2->3), e6 (3->4), e7 (4->1)
    Faces:
        f0: +e0 + e4 - e1  (0->1->2)
        f1: +e1 + e5 - e2  (0->2->3)
        f2: +e2 + e6 - e3  (0->3->4)
        f3: +e3 + e7 - e0  (0->4->1)
    """
    d0 = np.array([
        [-1,  1,  0,  0,  0],  # e0: 0->1
        [-1,  0,  1,  0,  0],  # e1: 0->2
        [-1,  0,  0,  1,  0],  # e2: 0->3
        [-1,  0,  0,  0,  1],  # e3: 0->4
        [ 0, -1,  1,  0,  0],  # e4: 1->2
        [ 0,  0, -1,  1,  0],  # e5: 2->3
        [ 0,  0,  0, -1,  1],  # e6: 3->4
        [ 0,  1,  0,  0, -1],  # e7: 4->1
    ], dtype=float)

    d1 = np.array([
        [ 1, -1,  0,  0,  1,  0,  0,  0],  # f0: e0 - e1 + e4
        [ 0,  1, -1,  0,  0,  1,  0,  0],  # f1: e1 - e2 + e5
        [ 0,  0,  1, -1,  0,  0,  1,  0],  # f2: e2 - e3 + e6
        [-1,  0,  0,  1,  0,  0,  0,  1],  # f3: -e0 + e3 + e7
    ], dtype=float)

    return d0, d1


def fixture_closed_cycle_1skeleton():
    r"""1-skeleton 3-cycle (circle with hole, b1 = 1, 0 faces).

    Vertices: 0, 1, 2
    Edges: e0 (0->1), e1 (1->2), e2 (2->0)
    Faces: none (0 faces)
    """
    d0 = np.array([
        [-1,  1,  0],  # e0: 0->1
        [ 0, -1,  1],  # e1: 1->2
        [ 1,  0, -1],  # e2: 2->0
    ], dtype=float)

    d1 = np.zeros((0, 3), dtype=float)
    return d0, d1


def fixture_closed_tetrahedron():
    r"""Closed triangulated tetrahedron (2-sphere, dependent face rows).

    Vertices: 0, 1, 2, 3
    Edges:
        e0: 0->1, e1: 1->2, e2: 0->2
        e3: 0->3, e4: 1->3, e5: 2->3
    Faces:
        f0: (0, 1, 2) -> +e0 + e1 - e2
        f1: (0, 2, 3) -> +e2 + e5 - e3
        f2: (0, 3, 1) -> +e3 - e4 - e0
        f3: (1, 3, 2) -> +e4 - e5 - e1
    Sum of face rows:
        f0 + f1 + f2 + f3 = 0 (closed 2-cycle)
    """
    d0 = np.array([
        [-1,  1,  0,  0],  # e0: 0->1
        [ 0, -1,  1,  0],  # e1: 1->2
        [-1,  0,  1,  0],  # e2: 0->2
        [-1,  0,  0,  1],  # e3: 0->3
        [ 0, -1,  0,  1],  # e4: 1->3
        [ 0,  0, -1,  1],  # e5: 2->3
    ], dtype=float)

    d1 = np.array([
        [ 1,  1, -1,  0,  0,  0],  # f0
        [ 0,  0,  1, -1,  0,  1],  # f1
        [-1,  0,  0,  1, -1,  0],  # f2
        [ 0, -1,  0,  0,  1, -1],  # f3
    ], dtype=float)

    return d0, d1


def fixture_disconnected_triangles():
    r"""Two disconnected disjoint triangles (c = 2 components)."""
    t0_d0, t0_d1 = fixture_single_triangle()
    t1_d0, t1_d1 = fixture_single_triangle()

    e0, v0 = t0_d0.shape
    e1, v1 = t1_d0.shape
    f0 = t0_d1.shape[0]
    f1 = t1_d1.shape[0]

    d0 = np.zeros((e0 + e1, v0 + v1), dtype=float)
    d0[:e0, :v0] = t0_d0
    d0[e0:, v0:] = t1_d0

    d1 = np.zeros((f0 + f1, e0 + e1), dtype=float)
    d1[:f0, :e0] = t0_d1
    d1[f0:, e0:] = t1_d1

    return d0, d1


# -----------------------------------------------------------------------------
# Complex Validation Tests
# -----------------------------------------------------------------------------

def test_cochain_exactness_all_fixtures():
    """Verify d1 @ d0 == 0 strictly holds for all geometric test fixtures."""
    for name, fixture_fn in [
        ("single_triangle", fixture_single_triangle),
        ("quad_fan", fixture_quad_fan),
        ("closed_cycle", fixture_closed_cycle_1skeleton),
        ("closed_tetrahedron", fixture_closed_tetrahedron),
        ("disconnected_triangles", fixture_disconnected_triangles),
    ]:
        d0, d1 = fixture_fn()
        max_res = validate_cochain_complex(d0, d1)
        assert max_res == 0.0, f"Fixture {name} failed d1 @ d0 == 0 exactness."


def test_cochain_exactness_violation_fails_closed():
    """Verify that tampering with incidence entries raises CochainComplexError."""
    d0, d1 = fixture_single_triangle()
    d1_bad = d1.copy()
    d1_bad[0, 0] = 0.0  # break boundary cancellation
    with pytest.raises(CochainComplexError, match="d1 @ d0 == 0 violated"):
        validate_cochain_complex(d0, d1_bad)


def test_cochain_dimension_mismatch_fails_closed():
    """Verify dimension mismatches between d0 and d1 are caught."""
    d0, d1 = fixture_single_triangle()
    with pytest.raises(CochainComplexError, match="Edge dimension mismatch"):
        validate_cochain_complex(d0, d1[:, :2])


def test_cochain_non_finite_fails_closed():
    """Verify NaN or Inf in d0 or d1 raises CochainComplexError."""
    d0, d1 = fixture_single_triangle()
    d0_bad = d0.copy()
    d0_bad[0, 0] = np.nan
    with pytest.raises(CochainComplexError, match="non-finite"):
        validate_cochain_complex(d0_bad, d1)


# -----------------------------------------------------------------------------
# Exact / Coexact Component Recovery Tests
# -----------------------------------------------------------------------------

def test_pure_exact_component_recovery():
    """A purely gradient 1-cochain omega = d0 @ alpha is 100% exact."""
    d0, d1 = fixture_quad_fan()
    rng = np.random.default_rng(42)
    alpha_true = rng.standard_normal(d0.shape[1])
    omega = d0 @ alpha_true

    res = hodge_decompose(omega, d0, d1)

    assert np.allclose(res.exact, omega, atol=1e-10)
    assert np.allclose(res.coexact, 0.0, atol=1e-10)
    assert np.allclose(res.harmonic, 0.0, atol=1e-10)
    assert math.isclose(res.energy_exact, res.energy_total, rel_tol=1e-9)
    assert res.relative_reconstruction_error < 1e-10


def test_pure_coexact_component_recovery():
    """A purely curl 1-cochain omega = W1^{-1} d1^T gamma is 100% coexact."""
    d0, d1 = fixture_quad_fan()
    rng = np.random.default_rng(123)
    weights = np.array([1.2, 0.8, 1.5, 2.0, 0.5, 1.1, 0.9, 1.3])
    gamma_true = rng.standard_normal(d1.shape[0])
    omega = (1.0 / weights) * (d1.T @ gamma_true)

    res = hodge_decompose(omega, d0, d1, edge_metric=weights)

    assert np.allclose(res.coexact, omega, atol=1e-10)
    assert np.allclose(res.exact, 0.0, atol=1e-10)
    assert np.allclose(res.harmonic, 0.0, atol=1e-10)
    assert math.isclose(res.energy_coexact, res.energy_total, rel_tol=1e-9)
    assert res.relative_reconstruction_error < 1e-10


# -----------------------------------------------------------------------------
# Orthogonality & Energy Closure Tests
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_fn", [
    fixture_single_triangle,
    fixture_quad_fan,
    fixture_closed_cycle_1skeleton,
    fixture_closed_tetrahedron,
    fixture_disconnected_triangles,
])
def test_weighted_orthogonality_and_energy_closure(fixture_fn):
    """Verify mutual W1-orthogonality and total energy closure across all complexes."""
    d0, d1 = fixture_fn()
    n_edges = d0.shape[0]
    rng = np.random.default_rng(2026)
    omega = rng.standard_normal(n_edges)
    weights = rng.uniform(0.5, 2.5, size=n_edges)

    res = hodge_decompose(omega, d0, d1, edge_metric=weights)

    # 1. Exact-Coexact Orthogonality (algebraically exact: <d0 alpha, W1^{-1} d1^T gamma> = 0)
    assert abs(res.orthogonality_exact_coexact) < 1e-10

    # 2. Exact-Harmonic Orthogonality (<d0 alpha, h>_W1 = 0)
    assert abs(res.orthogonality_exact_harmonic) < 1e-10

    # 3. Coexact-Harmonic Orthogonality (<W1^{-1} d1^T gamma, h>_W1 = 0)
    assert abs(res.orthogonality_coexact_harmonic) < 1e-10

    # 4. Energy Closure
    sum_energies = res.energy_exact + res.energy_coexact + res.energy_harmonic
    assert math.isclose(res.energy_total, sum_energies, rel_tol=1e-10, abs_tol=1e-10)
    assert res.relative_energy_error < 1e-10

    # 5. Reconstruction Residual
    reconstructed = res.exact + res.coexact + res.harmonic
    assert np.allclose(omega, reconstructed, atol=1e-10)
    assert res.relative_reconstruction_error < 1e-10


# -----------------------------------------------------------------------------
# Non-trivial Harmonic Component & Closed 1st Homology
# -----------------------------------------------------------------------------

def test_harmonic_component_in_cycle_complex():
    """Verify non-trivial 1-cochain around a hole is identified as harmonic."""
    d0, d1 = fixture_closed_cycle_1skeleton()
    # Uniform circulation around the 3-cycle
    omega = np.array([1.0, 1.0, 1.0])

    res = hodge_decompose(omega, d0, d1)

    # d0^T omega = 0 (divergence free) -> exact is 0
    assert np.allclose(res.exact, 0.0, atol=1e-10)
    # d1 has 0 faces -> coexact is 0
    assert np.allclose(res.coexact, 0.0, atol=1e-10)
    # Entire signal is harmonic!
    assert np.allclose(res.harmonic, omega, atol=1e-10)
    assert math.isclose(res.energy_harmonic, res.energy_total, rel_tol=1e-10)
    assert res.diagnostics["harmonic_is_closed"] is True
    assert res.diagnostics["harmonic_is_coclosed"] is True


# -----------------------------------------------------------------------------
# Closed Surfaces and Dependent Face Rows
# -----------------------------------------------------------------------------

def test_closed_tetrahedron_dependent_face_rows():
    """Verify closed surface with rank-deficient M runs stably and flags dependent rows."""
    d0, d1 = fixture_closed_tetrahedron()
    rng = np.random.default_rng(999)
    omega = rng.standard_normal(d0.shape[0])

    res = hodge_decompose(omega, d0, d1)

    assert res.diagnostics["dependent_face_rows"] is True
    assert res.diagnostics["rank_M_effective"] == 3  # 4 faces, 1 dependency
    assert res.relative_reconstruction_error < 1e-10
    assert res.relative_energy_error < 1e-10


# -----------------------------------------------------------------------------
# Boundary Conditions and Zero-Interior-Node Handling
# -----------------------------------------------------------------------------

def test_boundary_detection():
    """Verify automatic boundary edge and vertex detection."""
    # Single triangle: 3 boundary edges, 3 boundary vertices, 0 interior
    d0_tri, d1_tri = fixture_single_triangle()
    b_edges, b_verts = detect_boundary_elements(d0_tri, d1_tri)
    assert np.all(b_edges)
    assert np.all(b_verts)

    # Quad fan: 4 rim boundary edges, 4 boundary vertices, center vertex is interior
    d0_fan, d1_fan = fixture_quad_fan()
    b_edges_fan, b_verts_fan = detect_boundary_elements(d0_fan, d1_fan)
    assert np.sum(b_edges_fan) == 4  # e4, e5, e6, e7
    assert b_verts_fan[0] == False   # center vertex 0 is interior!
    assert np.all(b_verts_fan[1:])   # rim vertices 1..4 are boundary


def test_dirichlet_potential_quad_fan():
    """Test Dirichlet boundary condition on quad fan pins boundary vertices to zero."""
    d0, d1 = fixture_quad_fan()
    rng = np.random.default_rng(77)
    omega = rng.standard_normal(d0.shape[0])

    res = hodge_decompose(
        omega, d0, d1,
        boundary_condition=BoundaryCondition.DIRICHLET_POTENTIAL
    )

    # Boundary vertices (1, 2, 3, 4) must have potential alpha == 0
    assert np.allclose(res.potential[1:], 0.0, atol=1e-12)
    # Total energy must still close
    assert res.relative_energy_error < 1e-10
    assert res.relative_reconstruction_error < 1e-10


def test_zero_interior_nodes_dirichlet_handling():
    """Single triangle has 0 interior nodes; Dirichlet potential yields alpha = 0."""
    d0, d1 = fixture_single_triangle()
    omega = np.array([1.0, 2.0, -1.0])

    res = hodge_decompose(
        omega, d0, d1,
        boundary_condition=BoundaryCondition.DIRICHLET_POTENTIAL
    )

    assert res.diagnostics["zero_interior_nodes"] is True
    assert res.diagnostics["dirichlet_all_boundary"] is True
    assert np.allclose(res.potential, 0.0, atol=1e-12)
    assert np.allclose(res.exact, 0.0, atol=1e-12)
    assert res.relative_reconstruction_error < 1e-10


# -----------------------------------------------------------------------------
# Gauge Invariance of Exact Component
# -----------------------------------------------------------------------------

def test_gauge_policy_invariance_of_exact_component():
    """Verify that omega_exact is identical across MINIMUM_NORM, PINNED_VERTEX, and ZERO_MEAN."""
    d0, d1 = fixture_quad_fan()
    rng = np.random.default_rng(314)
    omega = rng.standard_normal(d0.shape[0])

    res_min_norm = hodge_decompose(omega, d0, d1, gauge=GaugePolicy.MINIMUM_NORM)
    res_pinned   = hodge_decompose(omega, d0, d1, gauge=GaugePolicy.PINNED_VERTEX)
    res_zero_mean = hodge_decompose(omega, d0, d1, gauge=GaugePolicy.ZERO_MEAN)

    # Exact 1-cochains must match to machine precision
    assert np.allclose(res_min_norm.exact, res_pinned.exact, atol=1e-12)
    assert np.allclose(res_min_norm.exact, res_zero_mean.exact, atol=1e-12)

    # Pinned vertex potential must have alpha[0] == 0
    assert abs(res_pinned.potential[0]) < 1e-12

    # Zero mean potential must sum to 0
    assert abs(np.sum(res_zero_mean.potential)) < 1e-12


# -----------------------------------------------------------------------------
# General SPD Metric Matrix Support
# -----------------------------------------------------------------------------

def test_general_spd_metric_decomposition():
    """Verify decomposition under a full 2D symmetric positive-definite metric matrix."""
    d0, d1 = fixture_single_triangle()
    n_edges = d0.shape[0]

    # Construct random SPD matrix W1 = A^T A + 0.5 I
    rng = np.random.default_rng(555)
    A = rng.standard_normal((n_edges, n_edges))
    W1 = A.T @ A + 0.5 * np.eye(n_edges)

    omega = np.array([2.0, -1.0, 1.5])

    res = hodge_decompose(
        omega, d0, d1,
        edge_metric=W1,
        metric_type=MetricType.GENERAL_SPD
    )

    assert res.metric_type == MetricType.GENERAL_SPD.value
    assert res.diagnostics["is_diagonal_metric"] is False

    # Check mutual W1-orthogonality under full matrix
    assert abs(res.orthogonality_exact_coexact) < 1e-10
    assert abs(res.orthogonality_exact_harmonic) < 1e-10
    assert abs(res.orthogonality_coexact_harmonic) < 1e-10

    # Energy closure
    assert res.relative_energy_error < 1e-10
    assert res.relative_reconstruction_error < 1e-10


# -----------------------------------------------------------------------------
# Metric Validation & Fail-Closed Checks
# -----------------------------------------------------------------------------

def test_non_positive_diagonal_metric_fails_closed():
    """Non-positive or zero weights raise MetricError."""
    with pytest.raises(MetricError, match="strictly positive"):
        validate_edge_metric([1.0, 0.0, 2.0], 3)

    with pytest.raises(MetricError, match="strictly positive"):
        validate_edge_metric([1.0, -0.5, 2.0], 3)


def test_non_finite_metric_fails_closed():
    """NaN or Inf weights raise MetricError."""
    with pytest.raises(MetricError, match="non-finite"):
        validate_edge_metric([1.0, np.nan, 2.0], 3)


def test_non_symmetric_2d_metric_fails_closed():
    """Asymmetric 2D matrix raises MetricError."""
    W_bad = np.array([[1.0, 0.5], [0.2, 1.0]])
    with pytest.raises(MetricError, match="not symmetric"):
        validate_edge_metric(W_bad, 2)


def test_non_spd_2d_metric_fails_closed():
    """Negative-eigenvalue 2D matrix raises MetricError."""
    W_bad = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues 3, -1
    with pytest.raises(MetricError, match="not positive definite"):
        validate_edge_metric(W_bad, 2)


# -----------------------------------------------------------------------------
# Conditioning Diagnostics & Rejection
# -----------------------------------------------------------------------------

def test_ill_conditioned_metric_diagnostics():
    """Extreme weight separation is flagged in diagnostics or rejected."""
    d0, d1 = fixture_single_triangle()
    # Construct extreme weight ratio 1e8 > sqrt(1e12) = 1e6
    ill_weights = np.array([1e-4, 1.0, 1e4])

    res = hodge_decompose(
        [1.0, 1.0, 1.0], d0, d1,
        edge_metric=ill_weights,
        cond_reject=1e6,  # threshold = sqrt(1e6) = 1e3
        fail_on_ill_conditioned=False
    )
    assert res.diagnostics["accepted"] is False
    assert res.verdict == "REJECTED_ILL_CONDITIONED"

    with pytest.raises(IllConditionedMetricError, match="rejected"):
        hodge_decompose(
            [1.0, 1.0, 1.0], d0, d1,
            edge_metric=ill_weights,
            cond_reject=1e6,
            fail_on_ill_conditioned=True
        )


# -----------------------------------------------------------------------------
# Interoperability Aliases and as_dict Serialization
# -----------------------------------------------------------------------------

def test_interoperability_aliases_and_serialization():
    """Verify compatibility properties (ortho_*, stream_gamma, as_dict)."""
    d0, d1 = fixture_single_triangle()
    omega = np.array([1.0, 0.5, -0.5])
    res = hodge_decompose(omega, d0, d1)

    assert res.ortho_exact_coexact == res.orthogonality_exact_coexact
    assert res.ortho_exact_harmonic == res.orthogonality_exact_harmonic
    assert res.ortho_coexact_harmonic == res.orthogonality_coexact_harmonic
    assert np.all(res.stream_gamma == res.stream_function)
    assert res.reconstruction_residual_w1 == res.reconstruction_residual_norm
    assert res.accepted is True
    assert res.verdict == "PASS_SYNTHETIC"

    d = res.as_dict()
    assert isinstance(d, dict)
    assert isinstance(d["exact"], list)
    assert isinstance(d["coexact"], list)
    assert "diagnostics" in d


# -----------------------------------------------------------------------------
# Additional Branch Coverage & Error Handling
# -----------------------------------------------------------------------------

def test_empty_complex_handling():
    """Verify empty edge complex (0 edges) returns zero result cleanly."""
    d0 = np.zeros((0, 3), dtype=float)
    d1 = np.zeros((0, 0), dtype=float)
    omega = np.zeros(0, dtype=float)

    res = hodge_decompose(omega, d0, d1)
    assert res.energy_total == 0.0
    assert len(res.exact) == 0
    assert len(res.coexact) == 0
    assert len(res.harmonic) == 0
    assert res.accepted is True
    assert res.verdict == "PASS_SYNTHETIC"


def test_invalid_boundary_condition_and_gauge():
    """Verify invalid boundary conditions or gauges raise appropriate errors."""
    d0, d1 = fixture_single_triangle()
    omega = np.ones(3)

    with pytest.raises(BoundaryConditionError, match="Unsupported boundary condition"):
        hodge_decompose(omega, d0, d1, boundary_condition="invalid_bc")

    with pytest.raises(BoundaryConditionError, match="Invalid boundary condition type"):
        hodge_decompose(omega, d0, d1, boundary_condition=12345)

    with pytest.raises(HodgeError, match="Unsupported gauge policy"):
        hodge_decompose(omega, d0, d1, gauge="unknown_gauge")

    with pytest.raises(HodgeError, match="Invalid gauge policy type"):
        hodge_decompose(omega, d0, d1, gauge=3.14)

    with pytest.raises(NotImplementedError, match="RELATIVE is reserved"):
        hodge_decompose(omega, d0, d1, boundary_condition=BoundaryCondition.RELATIVE)

    with pytest.raises(NotImplementedError, match="RELATIVE is reserved"):
        hodge_decompose(omega, d0, d1, boundary_condition="relative")


def test_invalid_omega_inputs():
    """Verify non-finite or mismatched omega raises CochainComplexError."""
    d0, d1 = fixture_single_triangle()

    with pytest.raises(CochainComplexError, match="does not match num_edges"):
        hodge_decompose(np.ones(4), d0, d1)

    with pytest.raises(CochainComplexError, match="non-finite entries"):
        hodge_decompose([1.0, np.nan, 2.0], d0, d1)


def test_invalid_face_metric():
    """Verify face_metric validation catches shape and value errors."""
    d0, d1 = fixture_single_triangle()
    omega = np.ones(3)

    with pytest.raises(MetricError, match="face_metric shape"):
        hodge_decompose(omega, d0, d1, face_metric=[1.0, 2.0])

    with pytest.raises(MetricError, match="face_metric must contain strictly positive"):
        hodge_decompose(omega, d0, d1, face_metric=[0.0])

    with pytest.raises(MetricError, match="face_metric must contain strictly positive"):
        hodge_decompose(omega, d0, d1, face_metric=[np.inf])


def test_invalid_edge_metric_dimensions():
    """Verify 1D, 2D shape mismatch and >2D arrays raise MetricError."""
    with pytest.raises(MetricError, match="does not match num_edges"):
        validate_edge_metric([1.0, 2.0], 3)

    with pytest.raises(MetricError, match="does not match"):
        validate_edge_metric(np.eye(2), 3)

    with pytest.raises(MetricError, match="1D or 2D"):
        validate_edge_metric(np.zeros((2, 2, 2)), 2)


def test_boundary_vertices_shape_mismatch():
    """Verify boundary_vertices shape validation."""
    d0, d1 = fixture_single_triangle()
    omega = np.ones(3)

    with pytest.raises(BoundaryConditionError, match="boundary_vertices shape"):
        hodge_decompose(
            omega, d0, d1,
            boundary_condition=BoundaryCondition.DIRICHLET_POTENTIAL,
            boundary_vertices=[True, False]  # length 2 != 3 vertices
        )


def test_effective_condition_number_edge_cases():
    """Verify effective_condition_number with empty or zero matrices."""
    cond, rank = effective_condition_number(np.zeros((0, 0)))
    assert cond == 0.0 and rank == 0

    cond, rank = effective_condition_number(np.zeros((3, 3)))
    assert cond == float("inf") and rank == 0


def test_single_vertex_pinned_gauge():
    """Verify pinned vertex gauge on a 1-vertex complex."""
    d0 = np.zeros((1, 1), dtype=float)
    d1 = np.zeros((0, 1), dtype=float)
    omega = np.array([1.0])

    res = hodge_decompose(omega, d0, d1, gauge=GaugePolicy.PINNED_VERTEX)
    assert res.potential.shape == (1,)
    assert res.potential[0] == 0.0


def test_zero_and_tiny_cochains():
    """Verify zero cochain and tiny cochains decompose stably without numerical issues."""
    d0, d1 = fixture_quad_fan()
    n_edges = d0.shape[0]

    # Exactly zero cochain
    omega_zero = np.zeros(n_edges, dtype=float)
    res_zero = hodge_decompose(omega_zero, d0, d1)
    assert res_zero.energy_total == 0.0
    assert res_zero.energy_exact == 0.0
    assert res_zero.energy_coexact == 0.0
    assert res_zero.energy_harmonic == 0.0
    assert np.allclose(res_zero.exact, 0.0)
    assert np.allclose(res_zero.coexact, 0.0)
    assert np.allclose(res_zero.harmonic, 0.0)
    assert res_zero.relative_reconstruction_error == 0.0
    assert res_zero.relative_energy_error == 0.0

    # Tiny cochain (near machine epsilon, 1e-14)
    omega_tiny = np.full(n_edges, 1e-14, dtype=float)
    res_tiny = hodge_decompose(omega_tiny, d0, d1)
    assert res_tiny.relative_reconstruction_error < 1e-8
    assert res_tiny.relative_energy_error < 1e-8


def test_planar_embedding_and_sensor_space_disclosure():
    """Verify diagnostics explicitly disclaim planar embedding and label as sensor-space algebraic."""
    d0, d1 = fixture_quad_fan()
    omega = np.ones(d0.shape[0])

    res = hodge_decompose(omega, d0, d1)
    assert res.diagnostics["planar_embedding_proven"] is False
    assert res.diagnostics["sensor_space_algebraic_only"] is True
    assert "no biological or clinical claims" in res.diagnostics["scientific_claim_disclaimer"]


def test_no_silent_regularization_on_singular_or_nonpositive_inputs():
    """Verify zero/negative weights are rejected, not silently regularized with epsilon."""
    d0, d1 = fixture_single_triangle()

    # Zero weight must fail closed, NOT be clamped to epsilon
    with pytest.raises(MetricError, match="strictly positive"):
        hodge_decompose([1.0, 1.0, 1.0], d0, d1, edge_metric=[1.0, 0.0, 1.0])

    # Negative weight must fail closed
    with pytest.raises(MetricError, match="strictly positive"):
        hodge_decompose([1.0, 1.0, 1.0], d0, d1, edge_metric=[1.0, -1e-8, 1.0])

    # Closed tetrahedron has singular M: rank deficiency must be honestly reported
    d0_tet, d1_tet = fixture_closed_tetrahedron()
    res = hodge_decompose(np.ones(d0_tet.shape[0]), d0_tet, d1_tet)
    assert res.diagnostics["rank_M_effective"] == 3
    assert res.diagnostics["dependent_face_rows"] is True


def test_invariance_under_consistent_edge_and_face_reorientation():
    """Verify decomposition is invariant under consistent orientation reversals.

    1. Edge reorientation (edge k reversed):
       - d0[k, :] -> -d0[k, :]
       - d1[:, k] -> -d1[:, k]
       - omega[k] -> -omega[k]
       Expectation:
       - omega_exact[k] -> -omega_exact[k]
       - omega_coexact[k] -> -omega_coexact[k]
       - omega_harm[k] -> -omega_harm[k]
       - potential alpha is invariant
       - stream function beta is invariant
       - energies and orthogonalities are invariant

    2. Face reorientation (face f reversed):
       - d1[f, :] -> -d1[f, :]
       Expectation:
       - omega_coexact is invariant
       - face potential gamma[f] -> -gamma[f]
       - stream function beta[f] -> -beta[f]
       - energies and orthogonalities are invariant
    """
    d0, d1 = fixture_quad_fan()
    rng = np.random.default_rng(20261018)
    omega = rng.standard_normal(d0.shape[0])
    weights = rng.uniform(0.8, 2.0, size=d0.shape[0])

    res_orig = hodge_decompose(omega, d0, d1, edge_metric=weights)

    # 1. Flip edge 2
    edge_flip = 2
    d0_e = d0.copy()
    d0_e[edge_flip, :] *= -1.0
    d1_e = d1.copy()
    d1_e[:, edge_flip] *= -1.0
    omega_e = omega.copy()
    omega_e[edge_flip] *= -1.0

    res_edge = hodge_decompose(omega_e, d0_e, d1_e, edge_metric=weights)

    # Component on flipped edge must be negated; other components unchanged
    expected_exact = res_orig.exact.copy()
    expected_exact[edge_flip] *= -1.0
    assert np.allclose(res_edge.exact, expected_exact, atol=1e-11)

    expected_coexact = res_orig.coexact.copy()
    expected_coexact[edge_flip] *= -1.0
    assert np.allclose(res_edge.coexact, expected_coexact, atol=1e-11)

    # Potential alpha and stream function beta must be invariant
    assert np.allclose(res_edge.potential, res_orig.potential, atol=1e-11)
    assert np.allclose(res_edge.stream_function, res_orig.stream_function, atol=1e-11)

    # Energies and orthogonalities must be identical
    assert math.isclose(res_edge.energy_total, res_orig.energy_total, rel_tol=1e-10)
    assert math.isclose(res_edge.energy_exact, res_orig.energy_exact, rel_tol=1e-10)
    assert math.isclose(res_edge.energy_coexact, res_orig.energy_coexact, rel_tol=1e-10)
    assert math.isclose(res_edge.energy_harmonic, res_orig.energy_harmonic, rel_tol=1e-10, abs_tol=1e-12)

    # 2. Flip face 1
    face_flip = 1
    d1_f = d1.copy()
    d1_f[face_flip, :] *= -1.0

    res_face = hodge_decompose(omega, d0, d1_f, edge_metric=weights)

    # Coexact 1-cochain is strictly invariant under face orientation choice
    assert np.allclose(res_face.coexact, res_orig.coexact, atol=1e-11)
    assert np.allclose(res_face.exact, res_orig.exact, atol=1e-11)
    assert np.allclose(res_face.harmonic, res_orig.harmonic, atol=1e-11)

    # Face stream function at flipped face must negate
    expected_beta = res_orig.stream_function.copy()
    expected_beta[face_flip] *= -1.0
    assert np.allclose(res_face.stream_function, expected_beta, atol=1e-11)

    assert math.isclose(res_face.energy_total, res_orig.energy_total, rel_tol=1e-10)
    assert math.isclose(res_face.energy_coexact, res_orig.energy_coexact, rel_tol=1e-10)


def test_scale_aware_numerical_closure():
    """Verify scale-aware numerical closure across 10 orders of magnitude."""
    d0, d1 = fixture_quad_fan()
    rng = np.random.default_rng(888)
    base_omega = rng.standard_normal(d0.shape[0])

    for scale in [1e-5, 1e-2, 1.0, 1e2, 1e5]:
        omega = scale * base_omega
        weights = rng.uniform(0.5, 2.5, size=d0.shape[0]) * scale

        res = hodge_decompose(omega, d0, d1, edge_metric=weights)

        # Scale-relative reconstruction and energy errors must stay below 1e-10
        assert res.relative_reconstruction_error < 1e-10
        assert res.relative_energy_error < 1e-10
        assert abs(res.orthogonality_exact_coexact) / (res.energy_total + 1e-12) < 1e-10
