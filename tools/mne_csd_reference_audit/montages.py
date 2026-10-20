"""Deterministic small sensor montages on the unit sphere (unit vectors).

Scale by the sphere radius (metres) and add the origin to get positions.
Seeded generators use numpy's default_rng, so montages are reproducible.
"""
from __future__ import annotations

import math

import numpy as np


def _normalise(points: np.ndarray) -> np.ndarray:
    return points / np.linalg.norm(points, axis=1, keepdims=True)


def tetrahedron() -> np.ndarray:
    return _normalise(np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=float))


def octahedron() -> np.ndarray:
    return np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=float)


def ring_with_apex(n_ring: int = 8, elevation_deg: float = 30.0) -> np.ndarray:
    z = math.sin(math.radians(elevation_deg))
    r = math.cos(math.radians(elevation_deg))
    angles = np.linspace(0.0, 2.0 * math.pi, n_ring, endpoint=False)
    ring = np.column_stack([r * np.cos(angles), r * np.sin(angles), np.full(n_ring, z)])
    return np.vstack([ring, [[0.0, 0.0, 1.0]]])


def seeded_cap(n: int, seed: int, min_z: float = 0.15, min_separation_deg: float = 8.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    points: list[np.ndarray] = []
    cos_limit = math.cos(math.radians(min_separation_deg))
    while len(points) < n:
        candidate = _normalise(rng.normal(size=(1, 3)))[0]
        if candidate[2] < min_z:
            continue
        if any(float(candidate @ p) > cos_limit for p in points):
            continue
        points.append(candidate)
    return np.vstack(points)


def near_coincident_pair(seed: int = 11, angle_deg: float = 2.0) -> np.ndarray:
    base = seeded_cap(5, seed)
    anchor = base[0]
    offset = np.cross(anchor, [0.0, 0.0, 1.0])
    if np.linalg.norm(offset) < 1e-9:
        offset = np.cross(anchor, [0.0, 1.0, 0.0])
    offset = offset / np.linalg.norm(offset)
    angle = math.radians(angle_deg)
    neighbour = math.cos(angle) * anchor + math.sin(angle) * offset
    return np.vstack([base, neighbour])


MONTAGES = {
    "tetrahedron_4": tetrahedron,
    "octahedron_6": octahedron,
    "ring_apex_9": ring_with_apex,
    "seeded_cap_7": lambda: seeded_cap(7, seed=3),
    "seeded_cap_12": lambda: seeded_cap(12, seed=5),
    "near_coincident_6": near_coincident_pair,
}
