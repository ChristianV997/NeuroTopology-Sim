"""Deterministic synthetic ground-truth fixtures for TDA backend semantic conformance.

Provides standard mathematical fixtures covering:
1. Empty and degenerate inputs (N=0, N=1)
2. Disconnected components (clusters with known merger scales)
3. Known loop (unit square S^1 with analytical birth=1.0, death=sqrt(2))
4. Filled triangle / 2-simplex (equilateral 3-vertex triangle with immediate cycle filling)
5. Reordered vertices (permutation invariance)
6. Duplicate / coincident points (distance 0 edges)
7. Threshold boundary (filtration cutoff where loop birth < threshold < loop death)
8. Cubical grid fixtures (flat field and circular sublevel ring)

Guardrail: All fixtures are purely mathematical synthetic test harnesses;
they do not represent biological data or empirical neural evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .models import (
    CoefficientField,
    ConformanceExecutionConfig,
    FiltrationType,
    MetricConvention,
    PersistenceBar,
)


@dataclass(frozen=True)
class ConformanceFixture:
    """A deterministic synthetic fixture with analytical ground-truth expectations."""
    fixture_id: str
    description: str
    data: np.ndarray
    filtration_type: FiltrationType
    metric_convention: MetricConvention
    expected_bars: dict[int, list[PersistenceBar]]
    threshold: float | None = None
    expected_h0_count: int | None = None
    expected_h1_count: int | None = None
    expected_h2_count: int | None = None
    is_degenerate: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    def get_config(self, max_dimension: int = 1, tolerance: float = 1e-5) -> ConformanceExecutionConfig:
        return ConformanceExecutionConfig(
            filtration_type=self.filtration_type,
            metric_convention=self.metric_convention,
            coefficient_field=CoefficientField.Z2,
            max_dimension=max_dimension,
            threshold=self.threshold,
            tolerance=tolerance,
            input_identity=self.fixture_id,
        )


def make_empty_fixture() -> ConformanceFixture:
    """Fixture 1a: Empty point set (N=0)."""
    dm = np.empty((0, 0), dtype=np.float64)
    return ConformanceFixture(
        fixture_id="degenerate_empty_n0",
        description="Empty distance matrix (N=0)",
        data=dm,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        expected_bars={0: [], 1: []},
        expected_h0_count=0,
        expected_h1_count=0,
        is_degenerate=True,
    )


def make_single_point_fixture() -> ConformanceFixture:
    """Fixture 1b: Single isolated point (N=1)."""
    dm = np.zeros((1, 1), dtype=np.float64)
    return ConformanceFixture(
        fixture_id="degenerate_single_point_n1",
        description="Single isolated point (N=1, H0=[0, inf))",
        data=dm,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        expected_bars={
            0: [PersistenceBar.from_pair(0, 0.0, None)],
            1: [],
        },
        expected_h0_count=1,
        expected_h1_count=0,
        is_degenerate=True,
    )


def make_disconnected_components_fixture() -> ConformanceFixture:
    """Fixture 2: Disconnected components / clusters.

    4 points arranged as two well-separated pairs:
    Pair A: (0,0)-(1,0) at distance 1.0.
    Pair B: (10,0)-(11,0) at distance 1.0.
    Cross-pair distance = 10.0.
    Expected H0: two bars dying at 1.0, one bar dying at 10.0, one surviving [0, inf).
    Expected H1: empty.
    """
    pts = np.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [11.0, 0.0],
        [12.0, 0.0],
    ], dtype=np.float64)
    from .reference_engine import compute_euclidean_distance_matrix
    dm = compute_euclidean_distance_matrix(pts)
    return ConformanceFixture(
        fixture_id="disconnected_pairs_n4",
        description="Two well-separated point pairs with known merger scales at 1.0 and 10.0",
        data=dm,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        expected_bars={
            0: [
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 10.0),
                PersistenceBar.from_pair(0, 0.0, None),
            ],
            1: [],
        },
        expected_h0_count=4,
        expected_h1_count=0,
    )


def make_known_loop_fixture() -> ConformanceFixture:
    """Fixture 3: Known loop on unit square S^1.

    4 vertices forming a unit square:
    (0,0), (1,0), (1,1), (0,1).
    Edges of length 1.0; diagonals of length sqrt(2) ≈ 1.41421356.
    In Vietoris-Rips:
    - 4 edges enter at t=1.0, forming a 1-cycle and merging 4 H0 components into 1.
    - 2 diagonals enter at t=sqrt(2), adding 2-simplices that fill the 1-cycle.
    Expected H0: 3 bars [0.0, 1.0), 1 bar [0.0, inf).
    Expected H1: exactly 1 bar [1.0, sqrt(2)).
    """
    pts = np.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [1.0, 1.0],
        [0.0, 1.0],
    ], dtype=np.float64)
    from .reference_engine import compute_euclidean_distance_matrix
    dm = compute_euclidean_distance_matrix(pts)
    s2 = float(np.sqrt(2.0))
    return ConformanceFixture(
        fixture_id="known_loop_unit_square_n4",
        description="Unit square with 1 persistent loop born at 1.0 and dying at sqrt(2)",
        data=dm,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        expected_bars={
            0: [
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, None),
            ],
            1: [
                PersistenceBar.from_pair(1, 1.0, s2),
            ],
        },
        expected_h0_count=4,
        expected_h1_count=1,
    )


def make_filled_triangle_fixture() -> ConformanceFixture:
    """Fixture 4: Filled triangle / 2-simplex.

    3 vertices forming an equilateral triangle of side length 1.0.
    In Vietoris-Rips:
    - 3 edges enter at t=1.0.
    - The 2-simplex [0, 1, 2] has diameter max(1, 1, 1) = 1.0, entering at t=1.0 simultaneously.
    - The 1-cycle is filled at the exact moment of birth (lifetime = 0.0).
    Expected H0: 2 bars [0.0, 1.0), 1 bar [0.0, inf).
    Expected H1: empty (no persistent 1-cycles).
    """
    pts = np.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [0.5, np.sqrt(3.0) / 2.0],
    ], dtype=np.float64)
    from .reference_engine import compute_euclidean_distance_matrix
    dm = compute_euclidean_distance_matrix(pts)
    return ConformanceFixture(
        fixture_id="filled_triangle_n3",
        description="Equilateral 3-vertex triangle: 2-simplex fills cycle at 1.0 with 0 persistence",
        data=dm,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        expected_bars={
            0: [
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, None),
            ],
            1: [],
        },
        expected_h0_count=3,
        expected_h1_count=0,
    )


def make_reordered_fixture(
    base_fixture: ConformanceFixture,
    permutation: list[int] | None = None,
) -> ConformanceFixture:
    """Fixture 5: Reordered vertices (Permutation Invariance).

    Permutes rows and columns of the distance matrix by a non-trivial permutation.
    Persistence barcodes must remain strictly invariant.
    """
    n = base_fixture.data.shape[0]
    if permutation is None:
        permutation = list(reversed(range(n)))
    perm = np.asarray(permutation, dtype=int)
    permuted_data = base_fixture.data[np.ix_(perm, perm)]

    return ConformanceFixture(
        fixture_id=f"{base_fixture.fixture_id}_reordered",
        description=f"Permutation of {base_fixture.fixture_id} with permutation {permutation}",
        data=permuted_data,
        filtration_type=base_fixture.filtration_type,
        metric_convention=base_fixture.metric_convention,
        expected_bars=base_fixture.expected_bars,
        expected_h0_count=base_fixture.expected_h0_count,
        expected_h1_count=base_fixture.expected_h1_count,
        metadata={"base_fixture_id": base_fixture.fixture_id, "permutation": permutation},
    )


def make_duplicate_points_fixture() -> ConformanceFixture:
    """Fixture 6: Duplicate / coincident points.

    3 points where point 0 and point 1 are coincident (distance 0.0).
    Point 2 is at distance 1.0 from both.
    Distance matrix:
    [[0, 0, 1],
     [0, 0, 1],
     [1, 1, 0]]
    Expected H0: 1 finite bar [0.0, 1.0), 1 infinite bar [0.0, inf).
    (Distance 0 merger is instantaneous and dropped from canonical diagrams).
    Expected H1: empty.
    """
    dm = np.array([
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0],
        [1.0, 1.0, 0.0],
    ], dtype=np.float64)
    return ConformanceFixture(
        fixture_id="duplicate_coincident_points_n3",
        description="Coincident points at distance 0: handles instantaneous merger without crashing or NaNs",
        data=dm,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        expected_bars={
            0: [
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, None),
            ],
            1: [],
        },
        expected_h0_count=2,
        expected_h1_count=0,
    )


def make_threshold_boundary_fixture(threshold: float = 1.2) -> ConformanceFixture:
    """Fixture 7: Threshold boundary.

    Unit square with max filtration threshold T_max = 1.2.
    The loop is born at 1.0, but the filling 2-simplex appears at sqrt(2) ≈ 1.414 > 1.2.
    In the threshold-truncated filtration:
    - Loop forms at 1.0 and does NOT die within the filtration [1.0, threshold].
    - Reported with death=None (or threshold).
    """
    square = make_known_loop_fixture()
    return ConformanceFixture(
        fixture_id=f"threshold_boundary_t{threshold}",
        description=f"Unit square with filtration threshold {threshold} < sqrt(2): loop persists to threshold boundary",
        data=square.data,
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        threshold=threshold,
        expected_bars={
            0: [
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, 1.0),
                PersistenceBar.from_pair(0, 0.0, None),
            ],
            1: [
                PersistenceBar.from_pair(1, 1.0, None),
            ],
        },
        expected_h0_count=4,
        expected_h1_count=1,
    )


def make_cubical_flat_grid_fixture(size: int = 8) -> ConformanceFixture:
    """Fixture 8: Flat 2D scalar field for cubical persistence."""
    grid = np.zeros((size, size), dtype=np.float64)
    return ConformanceFixture(
        fixture_id=f"cubical_flat_grid_{size}x{size}",
        description="Flat 2D grid: 1 connected component in H0, 0 features in H1",
        data=grid,
        filtration_type=FiltrationType.CUBICAL_SUBLEVEL,
        metric_convention=MetricConvention.GRID_SCALAR_SUBLEVEL,
        expected_bars={
            0: [PersistenceBar.from_pair(0, 0.0, None)],
            1: [],
        },
        expected_h0_count=1,
        expected_h1_count=0,
    )


def make_cubical_annulus_loop_fixture(size: int = 12, radius: float = 4.0) -> ConformanceFixture:
    """Fixture 9: 2D Annulus / ring dip for cubical persistence."""
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.sqrt((xx - size / 2.0) ** 2 + (yy - size / 2.0) ** 2)
    grid = np.abs(r - radius).astype(np.float64)
    return ConformanceFixture(
        fixture_id=f"cubical_annulus_{size}x{size}_r{radius}",
        description="2D ring dip: exactly 1 prominent H1 loop in cubical sublevel persistence",
        data=grid,
        filtration_type=FiltrationType.CUBICAL_SUBLEVEL,
        metric_convention=MetricConvention.GRID_SCALAR_SUBLEVEL,
        expected_bars={0: [], 1: []},
        expected_h1_count=1,
    )


def get_all_conformance_fixtures() -> list[ConformanceFixture]:
    """Return all deterministic synthetic fixtures for the conformance test suite."""
    loop_fixture = make_known_loop_fixture()
    return [
        make_empty_fixture(),
        make_single_point_fixture(),
        make_disconnected_components_fixture(),
        loop_fixture,
        make_filled_triangle_fixture(),
        make_reordered_fixture(loop_fixture, [2, 0, 3, 1]),
        make_duplicate_points_fixture(),
        make_threshold_boundary_fixture(threshold=1.2),
        make_cubical_flat_grid_fixture(size=8),
        make_cubical_annulus_loop_fixture(size=12, radius=4.0),
    ]
