"""Comprehensive tests for persistent homology backend adapters.

Covers:
- simple triangle/cycle fixtures
- cycle creation/destruction
- beta-1 interval extraction
- threshold sweeps
- distance-matrix validation
- backend absence and capabilities
- fallback behavior
- deterministic output and checksums
- invalid dimensions and non-finite input
- memory-bounded window processing
- distinction between graph beta-1 and spatial charge
- node reordering invariance
- null serialization (no NaN or Infinity)
"""
from __future__ import annotations

import json
import os
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
    get_all_capabilities,
    get_backend,
    list_available_backends,
    stream_point_cloud_generator,
    stream_point_cloud_windows,
    verify_reordering_invariance,
    validate_distance_matrix,
    validate_input,
    validate_point_cloud,
)


@pytest.fixture
def equilateral_triangle() -> np.ndarray:
    """3 vertices with all pairwise distances equal to 1.0."""
    return np.array([
        [0.0, 1.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 0.0],
    ], dtype=np.float64)


@pytest.fixture
def unit_square_distances() -> np.ndarray:
    """4 vertices forming a unit square with edges 1.0 and diagonals sqrt(2)."""
    s2 = np.sqrt(2.0)
    return np.array([
        [0.0, 1.0, s2,  1.0],
        [1.0, 0.0, 1.0, s2],
        [s2,  1.0, 0.0, 1.0],
        [1.0, s2,  1.0, 0.0],
    ], dtype=np.float64)


@pytest.fixture
def circle_points() -> np.ndarray:
    """16 points evenly spaced on a unit circle."""
    theta = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    return np.column_stack([np.cos(theta), np.sin(theta)])


# 1. Simple triangle / cycle fixtures
def test_simple_triangle_and_cycle_fixtures(equilateral_triangle: np.ndarray, unit_square_distances: np.ndarray) -> None:
    for backend_name in ["deterministic-fallback", "ripser"]:
        caps = get_all_capabilities()
        if caps[backend_name].status != BackendCapabilityStatus.AVAILABLE:
            continue

        # In an equilateral triangle, 1-cycle forms at 1.0 and is immediately filled by the 2-simplex at 1.0
        res_tri = compute_persistence(equilateral_triangle, backend=backend_name)
        # Any H1 feature that might exist has 0 persistence (or is empty)
        assert all(iv.death == iv.birth for iv in res_tri.beta_1_intervals) or len(res_tri.beta_1_intervals) == 0

        # In a unit square, 1-cycle forms at 1.0 and is filled at sqrt(2)
        res_sq = compute_persistence(unit_square_distances, backend=backend_name)
        assert len(res_sq.beta_1_intervals) == 1
        h1 = res_sq.beta_1_intervals[0]
        assert np.isclose(h1.birth, 1.0, atol=1e-4)
        assert np.isclose(h1.death, np.sqrt(2.0), atol=1e-4)


# 2. Cycle creation / destruction
def test_cycle_creation_destruction(unit_square_distances: np.ndarray) -> None:
    res = compute_persistence(unit_square_distances, backend="deterministic-fallback")
    assert len(res.beta_1_intervals) == 1
    iv = res.beta_1_intervals[0]
    assert iv.birth < iv.death
    assert np.isclose(iv.persistence, np.sqrt(2.0) - 1.0, atol=1e-4)

    # Adding diagonal edge at weight 1.0 destroys the cycle at birth (forms triangles immediately)
    triangulated = unit_square_distances.copy()
    triangulated[0, 2] = triangulated[2, 0] = 1.0
    res_triang = compute_persistence(triangulated, backend="deterministic-fallback")
    # All cycles are filled immediately at filtration 1.0
    active_persistent_h1 = [i for i in res_triang.beta_1_intervals if i.death is not None and i.death > i.birth + 1e-6]
    assert len(active_persistent_h1) == 0


# 3. Beta-1 interval extraction and persistence landscapes
def test_beta1_interval_extraction(circle_points: np.ndarray) -> None:
    res = compute_persistence(
        circle_points,
        backend="deterministic-fallback",
        config=TDAConfig(compute_landscape=True, landscape_layers=3, landscape_resolution=50),
    )
    assert len(res.beta_1_intervals) == 1
    h1 = res.beta_1_intervals[0]
    assert h1.dimension == 1
    assert h1.birth > 0.0
    assert h1.death is not None and h1.death > h1.birth
    assert h1.persistence is not None and h1.persistence > 0.0

    # Check landscape layers
    assert res.landscape is not None
    assert len(res.landscape) == 3
    assert len(res.landscape[0]) == 50
    assert res.landscape_integrated_area is not None
    assert res.landscape_integrated_area > 0.0


# 4. Threshold sweeps
def test_threshold_sweeps(unit_square_distances: np.ndarray) -> None:
    # Sub-threshold: max_edge_length < 1.0 -> no edges form -> H1 = 0
    res_sub = compute_persistence(
        unit_square_distances,
        backend="deterministic-fallback",
        config=TDAConfig(max_edge_length=0.5),
    )
    assert len(res_sub.beta_1_intervals) == 0

    # Intermediate threshold: 1.0 <= max_edge_length < sqrt(2) -> cycle born, but death (sqrt(2)) is beyond threshold
    res_mid = compute_persistence(
        unit_square_distances,
        backend="deterministic-fallback",
        config=TDAConfig(max_edge_length=1.2),
    )
    assert len(res_mid.beta_1_intervals) == 1
    # Unclosed within bounded filtration -> death is None
    assert res_mid.beta_1_intervals[0].death is None

    # Full threshold: max_edge_length >= sqrt(2) -> cycle born and dies
    res_full = compute_persistence(
        unit_square_distances,
        backend="deterministic-fallback",
        config=TDAConfig(max_edge_length=2.0),
    )
    assert len(res_full.beta_1_intervals) == 1
    assert res_full.beta_1_intervals[0].death is not None
    assert np.isclose(res_full.beta_1_intervals[0].death, np.sqrt(2.0), atol=1e-4)


# 5. Distance-matrix validation
def test_distance_matrix_validation() -> None:
    valid_dm = np.array([[0.0, 1.0], [1.0, 0.0]])
    validated = validate_distance_matrix(valid_dm)
    assert validated.shape == (2, 2)

    # Asymmetric
    asym = np.array([[0.0, 1.0], [2.0, 0.0]])
    with pytest.raises(ValueError, match="not symmetric"):
        validate_distance_matrix(asym)

    # Non-zero diagonal
    bad_diag = np.array([[0.5, 1.0], [1.0, 0.0]])
    with pytest.raises(ValueError, match="diagonal must be 0"):
        validate_distance_matrix(bad_diag)

    # Negative distance
    neg_dist = np.array([[0.0, -1.0], [-1.0, 0.0]])
    with pytest.raises(ValueError, match="negative entries"):
        validate_distance_matrix(neg_dist)

    # Non-square
    non_sq = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 3.0]])
    with pytest.raises(ValueError, match="must be square"):
        validate_distance_matrix(non_sq)


# 6. Backend absence and capabilities
def test_backend_absence_and_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = get_all_capabilities()
    assert BackendName.FALLBACK.value in caps
    assert caps[BackendName.FALLBACK.value].status == BackendCapabilityStatus.AVAILABLE

    # Requesting non-existent backend raises KeyError
    with pytest.raises(KeyError, match="Unknown TDA backend"):
        get_backend("non-existent-backend-xyz")

    # If backend is disabled via env var, it reports DISABLED_OFFLINE
    monkeypatch.setenv("NEUROTOPO_DISABLE_RIPSER", "1")
    caps_disabled = get_all_capabilities()
    assert caps_disabled[BackendName.RIPSER.value].status == BackendCapabilityStatus.DISABLED_OFFLINE

    with pytest.raises(RuntimeError, match="not available"):
        get_backend("ripser")


# 7. Fallback behavior and scientific status
def test_fallback_behavior_and_scientific_status(circle_points: np.ndarray) -> None:
    backend = DeterministicFallbackBackend()
    assert backend.scientific_status == ScientificStatus.APPROXIMATE_FIXTURE_ONLY

    res = backend.compute(circle_points, InputKind.POINT_CLOUD)
    assert res.scientific_status == ScientificStatus.APPROXIMATE_FIXTURE_ONLY
    assert len(res.beta_1_intervals) == 1

    # Exceeding MAX_POINTS_BOUND raises ValueError
    too_large = np.zeros((150, 2))
    with pytest.raises(ValueError, match="restricted to bounded fixtures"):
        backend.compute(too_large, InputKind.POINT_CLOUD)


# 8. Deterministic output and checksum repeatability
def test_deterministic_output_and_checksum(circle_points: np.ndarray) -> None:
    res1 = compute_persistence(circle_points, backend="deterministic-fallback")
    res2 = compute_persistence(circle_points, backend="deterministic-fallback")

    assert res1.deterministic_checksum == res2.deterministic_checksum
    assert len(res1.beta_1_intervals) == len(res2.beta_1_intervals)
    assert res1.beta_1_intervals[0].birth == res2.beta_1_intervals[0].birth

    # Modified point cloud has different checksum
    modified = circle_points.copy()
    modified[0, 0] += 0.5
    res3 = compute_persistence(modified, backend="deterministic-fallback")
    assert res1.deterministic_checksum != res3.deterministic_checksum


# 9. Invalid dimensions and non-finite input
def test_invalid_dimensions_and_non_finite_input() -> None:
    # 1D array
    with pytest.raises(ValueError, match="2-dimensional"):
        validate_point_cloud(np.array([1.0, 2.0, 3.0]))

    # < 2 points
    with pytest.raises(ValueError, match="at least 2 points"):
        validate_point_cloud(np.array([[1.0, 2.0]]))

    # NaN in point cloud
    with pytest.raises(ValueError, match="non-finite"):
        validate_point_cloud(np.array([[1.0, np.nan], [2.0, 3.0]]))

    # Inf in point cloud
    with pytest.raises(ValueError, match="non-finite"):
        validate_point_cloud(np.array([[1.0, np.inf], [2.0, 3.0]]))


# 10. Memory-bounded windowed processing
def test_memory_bounded_window_processing() -> None:
    # Trajectory of 40 points in 2D
    trajectory = np.column_stack([np.linspace(0, 10, 40), np.sin(np.linspace(0, 10, 40))])
    cfg = StreamingWindowConfig(
        window_size=16,
        step_size=8,
        max_allowed_points_per_window=32,
        backend="deterministic-fallback",
    )

    streaming_res = stream_point_cloud_windows(trajectory, cfg)
    assert len(streaming_res.window_results) == 4
    assert streaming_res.total_runtime_seconds >= 0.0
    assert streaming_res.peak_memory_bytes is not None
    assert streaming_res.deterministic_checksum is not None

    # Exceeding memory bound
    bad_cfg = StreamingWindowConfig(window_size=50, max_allowed_points_per_window=32)
    with pytest.raises(ValueError, match="exceeds memory limit"):
        stream_point_cloud_windows(trajectory, bad_cfg)


# 11. Distinction between graph beta-1 and spatial topological charge
def test_distinction_between_graph_beta1_and_spatial_charge() -> None:
    # Scientific guardrail rejects spatial charge labels
    with pytest.raises(ValueError, match="Scientific semantics violation"):
        assert_not_spatial_charge("spatial_winding_charge")

    with pytest.raises(ValueError, match="Scientific semantics violation"):
        assert_not_spatial_charge("vortex_charge")

    # Mathematical demonstration of non-equivalence:
    # A single vortex in a 2D phase grid has spatial winding charge Q = 1 (contour integral over phase gradient = 2*pi).
    # Its graph beta-1 homology on the point cloud depends strictly on the metric/connectivity threshold and does not equal Q.
    theta = np.linspace(0, 2 * np.pi, 20, endpoint=False)
    pts = np.column_stack([np.cos(theta), np.sin(theta)])
    res = compute_persistence(pts, backend="deterministic-fallback")
    # TDA result must not expose or claim spatial topological charge
    out_dict = res.to_dict()
    assert "spatial_charge" not in out_dict
    assert "winding_number" not in out_dict
    assert res.scientific_status in (ScientificStatus.APPROXIMATE_FIXTURE_ONLY, ScientificStatus.STRICT_COHOMOLOGY)


# 12. Node reordering invariance
def test_node_reordering_invariance(circle_points: np.ndarray, unit_square_distances: np.ndarray) -> None:
    # Point cloud reordering invariance
    order = list(range(len(circle_points)))[::-1]
    assert verify_reordering_invariance(circle_points, input_kind="point_cloud", order=order, backend="deterministic-fallback")

    # Distance matrix reordering invariance
    order_dm = [2, 0, 3, 1]
    assert verify_reordering_invariance(unit_square_distances, input_kind="distance_matrix", order=order_dm, backend="deterministic-fallback")


# 13. Null serialization: No NaN or Infinity in outputs
def test_null_serialization_no_nan_or_inf(unit_square_distances: np.ndarray) -> None:
    # Compute with bounded threshold so death is None (unclosed feature)
    res = compute_persistence(
        unit_square_distances,
        backend="deterministic-fallback",
        config=TDAConfig(max_edge_length=1.2),
    )
    json_str = res.to_json()
    # Ensure standard JSON without NaN or Infinity
    data = json.loads(json_str)
    # Check that infinite death became null (Python None)
    b1 = data["beta_1_intervals"][0]
    assert b1["death"] is None
    assert "NaN" not in json_str
    assert "Infinity" not in json_str
