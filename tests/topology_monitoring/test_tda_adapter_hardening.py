"""Hardening and adversarial tests for persistent-homology adapter layer.

Adversarial coverage:
- coincident points and degenerate point clouds
- integer-centered phase vortex cancellation vs TDA translation invariance
- asymmetric, non-square, and negative distance matrices
- non-finite values (NaN, Inf, -Inf) and complex inputs
- backend missing capability probing and runtime error wrapping
- oversized and invalid streaming windows
- multi-permutation node reordering invariance
- deterministic repeated execution and checksum stability
- exact trapezoidal integration against analytic tent functions
- strict null serialization (no NaN or Infinity)
- strict separation between graph beta-1 homology and spatial winding charge
"""
from __future__ import annotations

import json
import math
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from topo_monitor.tda_adapters import (
    BackendCapabilityStatus,
    BackendName,
    DeterministicFallbackBackend,
    InputKind,
    PersistenceInterval,
    ScientificStatus,
    StreamingWindowConfig,
    TDAConfig,
    assert_not_spatial_charge,
    compute_persistence,
    compute_persistence_landscape,
    get_all_capabilities,
    get_backend,
    list_available_backends,
    stream_point_cloud_generator,
    stream_point_cloud_windows,
    validate_distance_matrix,
    validate_input,
    validate_point_cloud,
    verify_reordering_invariance,
)
from topo_monitor.tda_adapters.types import sanitize_float, sanitize_value


# ---------------------------------------------------------------------------
# 1. Coincident Points and Degenerate Point Clouds
# ---------------------------------------------------------------------------
def test_coincident_points_fallback() -> None:
    """A point cloud where all points are coincident has 1 connected component and 0 persistent H1 holes."""
    n_points = 8
    coincident = np.ones((n_points, 3), dtype=np.float64) * 5.0

    res = compute_persistence(coincident, backend="deterministic-fallback")
    assert res.num_points == n_points
    # Exactly one essential H0 component (death is None)
    essential_h0 = [iv for iv in res.beta_0_intervals if iv.death is None]
    assert len(essential_h0) == 1
    # All other vertices die at birth 0.0 (zero persistence), so no non-zero finite intervals
    assert all(iv.persistence is None or iv.persistence == 0.0 for iv in res.beta_0_intervals)
    # No H1 features formed
    assert len(res.beta_1_intervals) == 0
    assert res.landscape_integrated_area == 0.0
    assert res.deterministic_checksum is not None


def test_degenerate_point_clouds_shapes_and_collinear() -> None:
    """Minimal valid shapes, collinear arrangements, and invalid dimension rejections."""
    # Minimal valid: 2 points in 1D
    pts_2d1 = np.array([[0.0], [2.0]], dtype=np.float64)
    res_min = compute_persistence(pts_2d1, backend="deterministic-fallback")
    assert res_min.num_points == 2
    assert len(res_min.beta_0_intervals) >= 1
    assert len(res_min.beta_1_intervals) == 0

    # Collinear points in 2D (a straight line cannot form a 1-cycle)
    collinear = np.column_stack([np.linspace(0, 10, 12), np.linspace(0, 20, 12)])
    res_collinear = compute_persistence(collinear, backend="deterministic-fallback")
    assert len(res_collinear.beta_1_intervals) == 0
    assert res_collinear.landscape_integrated_area == 0.0

    # Dimension D = 0 is invalid
    with pytest.raises(ValueError, match="at least 1 dimension"):
        validate_point_cloud(np.zeros((5, 0)))

    # Less than 2 points is invalid
    with pytest.raises(ValueError, match="at least 2 points"):
        validate_point_cloud(np.zeros((1, 3)))

    with pytest.raises(ValueError, match="at least 2 points"):
        validate_point_cloud(np.zeros((0, 2)))

    # 1D or 3D tensor is invalid
    with pytest.raises(ValueError, match="2-dimensional"):
        validate_point_cloud(np.array([1.0, 2.0, 3.0]))

    with pytest.raises(ValueError, match="2-dimensional"):
        validate_point_cloud(np.zeros((2, 2, 2)))

    # Complex-valued point cloud is rejected
    with pytest.raises(ValueError, match="real-valued"):
        validate_point_cloud(np.array([[1.0 + 1j, 2.0], [3.0, 4.0]]))


# ---------------------------------------------------------------------------
# 2. Asymmetric, Non-Square, and Negative Distance Matrices
# ---------------------------------------------------------------------------
def test_adversarial_distance_matrices() -> None:
    """Distance matrices must strictly be real, square, symmetric, zero-diagonal, and non-negative."""
    # Asymmetric matrix
    asym = np.array([
        [0.0, 1.0, 1.5],
        [1.1, 0.0, 2.0],
        [1.5, 2.0, 0.0],
    ])
    with pytest.raises(ValueError, match="not symmetric"):
        validate_distance_matrix(asym)

    # Non-zero diagonal
    bad_diag = np.array([
        [0.05, 1.0],
        [1.0, 0.0],
    ])
    with pytest.raises(ValueError, match="diagonal must be 0"):
        validate_distance_matrix(bad_diag)

    # Negative distance
    neg = np.array([
        [0.0, -0.2],
        [-0.2, 0.0],
    ])
    with pytest.raises(ValueError, match="negative entries"):
        validate_distance_matrix(neg)

    # Non-square
    non_sq = np.zeros((3, 4))
    with pytest.raises(ValueError, match="must be square"):
        validate_distance_matrix(non_sq)

    # Size < 2
    with pytest.raises(ValueError, match="size at least"):
        validate_distance_matrix(np.zeros((1, 1)))

    # Complex input
    with pytest.raises(ValueError, match="real-valued"):
        validate_distance_matrix(np.array([[0.0, 1j], [1j, 0.0]]))

    # Negative atol
    with pytest.raises(ValueError, match="atol must be non-negative"):
        validate_distance_matrix(np.zeros((2, 2)), atol=-1.0)


# ---------------------------------------------------------------------------
# 3. Non-Finite Values (NaN, Inf, -Inf)
# ---------------------------------------------------------------------------
def test_non_finite_values_rejection() -> None:
    """Inputs with NaN or Inf must be rejected with explicit ValueErrors."""
    # Point cloud with NaN
    nan_pc = np.array([[1.0, 2.0], [np.nan, 4.0]])
    with pytest.raises(ValueError, match="non-finite"):
        validate_point_cloud(nan_pc)

    # Point cloud with Inf
    inf_pc = np.array([[1.0, 2.0], [np.inf, 4.0]])
    with pytest.raises(ValueError, match="non-finite"):
        validate_point_cloud(inf_pc)

    # Point cloud with -Inf
    neginf_pc = np.array([[1.0, 2.0], [-np.inf, 4.0]])
    with pytest.raises(ValueError, match="non-finite"):
        validate_point_cloud(neginf_pc)

    # Distance matrix with NaN
    nan_dm = np.array([[0.0, np.nan], [np.nan, 0.0]])
    with pytest.raises(ValueError, match="non-finite"):
        validate_distance_matrix(nan_dm)

    # Distance matrix with Inf
    inf_dm = np.array([[0.0, np.inf], [np.inf, 0.0]])
    with pytest.raises(ValueError, match="non-finite"):
        validate_distance_matrix(inf_dm)


# ---------------------------------------------------------------------------
# 4. Backend Missing Capability and Runtime Error Wrapping
# ---------------------------------------------------------------------------
def test_backend_missing_and_runtime_error_wrapping() -> None:
    """Missing backends report MISSING and runtime exceptions are cleanly wrapped in RuntimeError."""
    caps = get_all_capabilities()
    assert BackendName.FALLBACK.value in caps
    assert caps[BackendName.FALLBACK.value].status == BackendCapabilityStatus.AVAILABLE

    # Requesting missing backend raises RuntimeError
    with patch("topo_monitor.tda_adapters.backends.RipserBackend.get_capability") as mock_cap:
        mock_cap.return_value.status = BackendCapabilityStatus.MISSING
        mock_cap.return_value.details = "mocked missing package"
        mock_cap.return_value.description = "mocked missing"
        with pytest.raises(RuntimeError, match="not available"):
            get_backend("ripser")

    # Backend runtime computation failure is cleanly wrapped
    backend = DeterministicFallbackBackend()
    with pytest.raises(ValueError, match="restricted to bounded fixtures"):
        # Points exceed bound
        backend.compute(np.zeros((200, 2)), InputKind.POINT_CLOUD)

    with pytest.raises(ValueError, match="requires at least 2 points"):
        backend.compute(np.zeros((1, 2)), InputKind.POINT_CLOUD)


# ---------------------------------------------------------------------------
# 5. Oversized and Invalid Streaming Windows
# ---------------------------------------------------------------------------
def test_streaming_window_adversarial_parameters() -> None:
    """Streaming window bounds and edge cases must raise clean ValueErrors."""
    pts = np.zeros((20, 2))

    # window_size < 2
    with pytest.raises(ValueError, match="window_size must be >= 2"):
        list(stream_point_cloud_generator(pts, StreamingWindowConfig(window_size=1)))

    # step_size < 1
    with pytest.raises(ValueError, match="step_size must be >= 1"):
        list(stream_point_cloud_generator(pts, StreamingWindowConfig(step_size=0)))

    # max_allowed_points_per_window < 2
    with pytest.raises(ValueError, match="max_allowed_points_per_window must be >= 2"):
        list(stream_point_cloud_generator(pts, StreamingWindowConfig(max_allowed_points_per_window=1)))

    # window_size > max_allowed_points_per_window
    with pytest.raises(ValueError, match="exceeds memory limit"):
        list(stream_point_cloud_generator(pts, StreamingWindowConfig(window_size=100, max_allowed_points_per_window=50)))

    # Total points less than window_size
    cfg = StreamingWindowConfig(window_size=16, step_size=8)
    short_pts = np.zeros((10, 2))
    with pytest.raises(ValueError, match="smaller than window_size"):
        list(stream_point_cloud_generator(short_pts, cfg))

    # Empty point cloud (0 points in 2D)
    with pytest.raises(ValueError, match="at least 2 points"):
        list(stream_point_cloud_generator(np.zeros((0, 2)), cfg))

    # 1D empty list
    with pytest.raises(ValueError, match="2-dimensional"):
        list(stream_point_cloud_generator([], cfg))


# ---------------------------------------------------------------------------
# 6. Multi-Permutation Node Reordering Invariance
# ---------------------------------------------------------------------------
def test_node_permutation_invariance_multi() -> None:
    """Node permutation invariance across multiple random permutations and geometries."""
    # 1. Circle points (point cloud)
    theta = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    circle = np.column_stack([np.cos(theta), np.sin(theta)])

    rng = np.random.default_rng(42)
    for _ in range(3):
        order = rng.permutation(len(circle)).tolist()
        assert verify_reordering_invariance(circle, input_kind="point_cloud", order=order, backend="deterministic-fallback")

    # 2. Distance matrix: unit square with diagonals
    s2 = np.sqrt(2.0)
    dm = np.array([
        [0.0, 1.0, s2,  1.0],
        [1.0, 0.0, 1.0, s2],
        [s2,  1.0, 0.0, 1.0],
        [1.0, s2,  1.0, 0.0],
    ], dtype=np.float64)

    for perm in [[3, 2, 1, 0], [1, 3, 0, 2], [2, 0, 3, 1]]:
        assert verify_reordering_invariance(dm, input_kind="distance_matrix", order=perm, backend="deterministic-fallback")


# ---------------------------------------------------------------------------
# 7. Deterministic Repeated Execution and Checksum Stability
# ---------------------------------------------------------------------------
def test_deterministic_repeated_execution_checksum() -> None:
    """Repeated execution produces identical bit-for-bit SHA-256 checksums."""
    theta = np.linspace(0, 2 * np.pi, 10, endpoint=False)
    pts = np.column_stack([np.cos(theta), np.sin(theta)])

    checksums = [
        compute_persistence(pts, backend="deterministic-fallback").deterministic_checksum
        for _ in range(5)
    ]
    assert len(set(checksums)) == 1, "Checksums across repeated executions must be identical"


# ---------------------------------------------------------------------------
# 8. Beta-1 Persistence Landscapes and Exact Trapezoidal Integration
# ---------------------------------------------------------------------------
def test_persistence_landscape_analytic_trapezoidal_area() -> None:
    """Verify trapezoidal integration against the analytic area of a known single tent function."""
    # An interval with birth b=1.0, death d=3.0 has persistence 2.0.
    # The tent function f(t) = max(0, min(t - 1, 3 - t)) is an isosceles triangle
    # with base [1.0, 3.0] (width 2.0) and peak at t=2.0 with height 1.0.
    # Analytic area = 0.5 * base * height = 0.5 * 2.0 * 1.0 = 1.0.
    iv = PersistenceInterval(dimension=1, birth=1.0, death=3.0)
    layers, grid, area = compute_persistence_landscape(
        intervals=[iv],
        num_layers=2,
        resolution=201,
        filtration_range=(0.0, 4.0),
    )

    assert len(layers) == 2
    assert len(grid) == 201
    assert np.isclose(area, 1.0, atol=1e-3), f"Expected analytic area 1.0, got {area}"

    # Empty intervals produce zero area
    empty_layers, _, empty_area = compute_persistence_landscape(
        intervals=[],
        num_layers=3,
        resolution=50,
    )
    assert empty_area == 0.0
    assert all(all(val == 0.0 for val in row) for row in empty_layers)


# ---------------------------------------------------------------------------
# 9. Filtration Threshold Sweeps Stability
# ---------------------------------------------------------------------------
def test_filtration_threshold_sweeps_stability() -> None:
    """Sweep max_edge_length to verify deterministic, finite, non-crashing behavior."""
    s2 = np.sqrt(2.0)
    dm = np.array([
        [0.0, 1.0, s2,  1.0],
        [1.0, 0.0, 1.0, s2],
        [s2,  1.0, 0.0, 1.0],
        [1.0, s2,  1.0, 0.0],
    ], dtype=np.float64)

    thresholds = np.linspace(0.5, 2.5, 9)
    for thresh in thresholds:
        cfg = TDAConfig(max_edge_length=float(thresh))
        res = compute_persistence(dm, backend="deterministic-fallback", config=cfg)
        assert res.runtime_seconds >= 0.0
        assert np.isfinite(res.runtime_seconds)
        for iv in res.beta_0_intervals + res.beta_1_intervals:
            assert np.isfinite(iv.birth)
            if iv.death is not None:
                assert np.isfinite(iv.death)


# ---------------------------------------------------------------------------
# 10. Strict Null Serialization (No NaN or Infinity)
# ---------------------------------------------------------------------------
def test_strict_null_serialization_and_metadata_sanitization() -> None:
    """All non-finite values in intervals, landscapes, or metadata serialize to null, not NaN or Inf."""
    iv_inf = PersistenceInterval(dimension=1, birth=1.0, death=None)
    res = compute_persistence(
        np.array([[0.0, 1.0], [1.0, 0.0]]),
        input_kind="distance_matrix",
        backend="deterministic-fallback",
        config=TDAConfig(max_edge_length=0.5),
    )
    # Inject non-finite value into metadata to test sanitization
    res.metadata["nan_metric"] = float("nan")
    res.metadata["inf_metric"] = float("inf")
    res.metadata["valid_float"] = 3.14

    # Serialization with allow_nan=False must succeed without error
    json_str = res.to_json()
    data = json.loads(json_str)

    assert data["metadata"]["nan_metric"] is None
    assert data["metadata"]["inf_metric"] is None
    assert data["metadata"]["valid_float"] == 3.14
    assert "NaN" not in json_str
    assert "Infinity" not in json_str


# ---------------------------------------------------------------------------
# 11. Strict Scientific Separation: Graph Beta-1 vs Spatial Topological Charge
# ---------------------------------------------------------------------------
def test_graph_beta1_vs_spatial_charge_strict_separation() -> None:
    """Graph beta-1 cycle rank must never be labeled or treated as spatial topological charge."""
    for label in ["spatial_charge", "spatial_topological_charge", "winding_charge", "vortex_charge", "topological_charge", "spatial_winding"]:
        with pytest.raises(ValueError, match="Scientific semantics violation"):
            assert_not_spatial_charge(label)

    # Fallback status is strictly APPROXIMATE_FIXTURE_ONLY
    backend = DeterministicFallbackBackend()
    assert backend.scientific_status == ScientificStatus.APPROXIMATE_FIXTURE_ONLY


# ---------------------------------------------------------------------------
# 12. Spatial Vortex Integer-Coordinate Cancellation Investigation & TDA Immunity
# ---------------------------------------------------------------------------
def test_spatial_vortex_integer_coordinate_cancellation_investigation() -> None:
    """Investigate the numerical singularity cancellation on discrete grids vs TDA translation immunity.

    Demonstrates:
    1. A spatial phase vortex centered exactly on a grid vertex (e.g., integer coordinate (10, 10))
       causes plaquette boundary cancellation, evaluating discrete winding sum to 0.0 because
       the central node atan2(0,0)=0 lies on the shared vertex of four neighboring cells.
    2. When shifted off-integer by half a cell (e.g. (10.5, 10.5)), the singularity is enclosed
       strictly inside a single plaquette, restoring the correct integer winding charge (+1.0).
    3. Persistent homology (TDA H1) computed on points sampled around the vortex center is
       completely invariant to coordinate translation (both integer and off-integer centers
       yield identical birth, death, and persistent cycle features).
    """
    # 1. Discrete spatial plaquette winding calculation on a 21x21 grid
    grid_size = 21
    y_idx, x_idx = np.mgrid[0:grid_size, 0:grid_size]

    def compute_plaquette_winding(cx: float, cy: float) -> float:
        phases = np.arctan2(y_idx - cy, x_idx - cx)
        wrap = lambda val: (val + np.pi) % (2 * np.pi) - np.pi
        local = (
            wrap(phases[1:, :-1] - phases[:-1, :-1])
            + wrap(phases[1:, 1:] - phases[1:, :-1])
            + wrap(phases[:-1, 1:] - phases[1:, 1:])
            + wrap(phases[:-1, :-1] - phases[:-1, 1:])
        ) / (2 * np.pi)
        return float(np.rint(np.sum(local)))

    # Case A: Integer center (10.0, 10.0) - singularity coincides exactly with a grid node.
    # At (10, 10), dy=0, dx=0 -> atan2(0, 0)=0 by floating-point convention, placing the
    # singularity directly on the corner vertex shared by four adjacent plaquettes.
    # The jump across the negative axis branch cut produces spurious cancellation (-2.0 or 0.0),
    # completely failing to recover the true topological charge (+1.0).
    integer_winding = compute_plaquette_winding(10.0, 10.0)
    assert integer_winding != 1.0, "Integer-centered vortex fails to recover true charge +1.0 on discrete plaquette grid"
    assert integer_winding in (-2.0, 0.0), f"Integer vortex exhibits spurious cancellation / branch cut artifact: {integer_winding}"

    # Case B: Off-integer center (10.5, 10.5) - singularity is enclosed strictly inside a cell.
    # The cell contour encloses the singularity without intersecting it, correctly recovering unit charge (|q| = 1.0).
    off_integer_winding = compute_plaquette_winding(10.5, 10.5)
    assert abs(off_integer_winding) == 1.0, f"Off-integer vortex encloses singularity and evaluates to unit charge, got {off_integer_winding}"

    # 2. TDA persistent homology (H1) translation invariance
    # Sample points on a circle of radius R=2.0 around the center
    radius = 2.0
    theta = np.linspace(0, 2 * np.pi, 16, endpoint=False)

    # Point cloud centered at integer (10.0, 10.0)
    pts_int = np.column_stack([10.0 + radius * np.cos(theta), 10.0 + radius * np.sin(theta)])
    res_int = compute_persistence(pts_int, backend="deterministic-fallback")

    # Point cloud centered at off-integer (10.5, 10.5)
    pts_off = np.column_stack([10.5 + radius * np.cos(theta), 10.5 + radius * np.sin(theta)])
    res_off = compute_persistence(pts_off, backend="deterministic-fallback")

    # TDA H1 detects the 1-cycle with identical persistence regardless of centering
    assert len(res_int.beta_1_intervals) == 1
    assert len(res_off.beta_1_intervals) == 1
    iv_int = res_int.beta_1_intervals[0]
    iv_off = res_off.beta_1_intervals[0]

    assert np.isclose(iv_int.birth, iv_off.birth, atol=1e-5)
    assert np.isclose(iv_int.death, iv_off.death, atol=1e-5)
    assert np.isclose(res_int.landscape_integrated_area, res_off.landscape_integrated_area, atol=1e-5)
