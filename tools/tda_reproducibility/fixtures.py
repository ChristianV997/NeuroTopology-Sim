"""Deterministic synthetic test fixtures for TDA reproducibility and equivalence auditing.

All fixtures are synthetic, deterministic, and bounded.
Guardrail: Synthetic benchmark fixtures represent mathematical test harnesses,
never empirical biological evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.spatial.distance import cdist, pdist, squareform


@dataclass(frozen=True)
class TDAFixture:
    fixture_id: str
    description: str
    distance_matrix: np.ndarray
    expected_beta_0_infinite: int = 1
    expected_beta_1_prominent: int | None = None
    max_dimension: int = 1


def make_circle_fixture(n_points: int = 12, radius: float = 1.0) -> TDAFixture:
    """Generate points evenly spaced on a 2D circle S^1. Exhibits exactly one prominent H1 loop."""
    theta = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
    coords = np.column_stack([radius * np.cos(theta), radius * np.sin(theta)])
    dist_mat = squareform(pdist(coords, metric="euclidean"))
    return TDAFixture(
        fixture_id="circle_s1_12",
        description=f"Synthetic circle S^1 with {n_points} evenly spaced points (prominent beta_1=1)",
        distance_matrix=dist_mat,
        expected_beta_0_infinite=1,
        expected_beta_1_prominent=1,
        max_dimension=1,
    )


def make_two_clusters_fixture(points_per_cluster: int = 5, separation: float = 8.0) -> TDAFixture:
    """Generate two well-separated compact clusters in 2D. No 1-cycles, late H0 merger."""
    c1 = np.array([[0.0, 0.0], [0.1, 0.0], [0.0, 0.1], [-0.1, 0.0], [0.0, -0.1]])[:points_per_cluster]
    c2 = c1 + np.array([separation, 0.0])
    coords = np.vstack([c1, c2])
    dist_mat = squareform(pdist(coords, metric="euclidean"))
    return TDAFixture(
        fixture_id="two_clusters_10",
        description="Two well-separated 5-point clusters (H0 late merger, beta_1=0)",
        distance_matrix=dist_mat,
        expected_beta_0_infinite=1,
        expected_beta_1_prominent=0,
        max_dimension=1,
    )


def make_line_segment_fixture(n_points: int = 8) -> TDAFixture:
    """Generate uniformly spaced points along a 1D line embedded in 2D. Contractible space."""
    x = np.linspace(0.0, 1.0, n_points)
    coords = np.column_stack([x, np.zeros_like(x)])
    dist_mat = squareform(pdist(coords, metric="euclidean"))
    return TDAFixture(
        fixture_id="line_segment_8",
        description="Collinear 8-point line segment in R^2 (contractible, beta_1=0)",
        distance_matrix=dist_mat,
        expected_beta_0_infinite=1,
        expected_beta_1_prominent=0,
        max_dimension=1,
    )


def make_random_symmetric_fixture(n_points: int = 14, seed: int = 42) -> TDAFixture:
    """Generate deterministic random 2D point cloud using a fixed seed."""
    rng = np.random.default_rng(seed)
    coords = rng.uniform(0.0, 1.0, size=(n_points, 2))
    dist_mat = squareform(pdist(coords, metric="euclidean"))
    return TDAFixture(
        fixture_id=f"random_euclidean_{n_points}_s{seed}",
        description=f"Deterministic random 2D point cloud (N={n_points}, seed={seed})",
        distance_matrix=dist_mat,
        expected_beta_0_infinite=1,
        expected_beta_1_prominent=None,
        max_dimension=1,
    )


def make_triangle_fixture() -> TDAFixture:
    """Equilateral 3-point triangle."""
    coords = np.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [0.5, np.sqrt(3.0) / 2.0],
    ])
    dist_mat = squareform(pdist(coords, metric="euclidean"))
    return TDAFixture(
        fixture_id="triangle_equilateral_3",
        description="Equilateral 3-vertex triangle (N=3)",
        distance_matrix=dist_mat,
        expected_beta_0_infinite=1,
        expected_beta_1_prominent=0,
        max_dimension=1,
    )


def get_standard_fixtures() -> list[TDAFixture]:
    """Return comprehensive suite of deterministic test fixtures."""
    return [
        make_circle_fixture(n_points=12),
        make_two_clusters_fixture(points_per_cluster=5),
        make_line_segment_fixture(n_points=8),
        make_triangle_fixture(),
        make_random_symmetric_fixture(n_points=14, seed=42),
    ]
