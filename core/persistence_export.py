"""JSON-serializable persistence diagram export and analysis."""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np


def serialize_diagram(diagram: np.ndarray) -> list[list[float]]:
    """Convert persistence diagram (n, 2) array to JSON-safe list.

    Infinite death values are converted to None, which JSON-encodes as null
    and can be reconstructed later.
    """
    if diagram.size == 0:
        return []
    result = []
    for birth, death in diagram:
        death_val = death if math.isfinite(death) else None
        result.append([float(birth), death_val])
    return result


def deserialize_diagram(data: list) -> np.ndarray:
    """Reconstruct persistence diagram from JSON-serialized format."""
    if not data:
        return np.empty((0, 2), dtype=float)
    pairs = []
    for birth, death in data:
        death_val = np.inf if death is None else float(death)
        pairs.append([float(birth), death_val])
    return np.array(pairs, dtype=float)


def bottleneck_distance(dgm1: np.ndarray, dgm2: np.ndarray) -> float:
    """Bottleneck distance between two persistence diagrams.

    The bottleneck distance is the supremum of the minimum distances between
    matched points, plus contributions from unmatched points (each unmatched
    point contributes its distance to the diagonal).

    For unmatched points in diagram dgm1, distance to diagonal is
    |birth - death| / 2 (projection onto y=x line).
    """
    if dgm1.size == 0 and dgm2.size == 0:
        return 0.0
    if dgm1.size == 0:
        deaths = np.where(np.isfinite(dgm2[:, 1]), dgm2[:, 1], np.inf)
        diag_dists = np.abs(dgm2[:, 0] - deaths) / 2.0
        return float(np.max(diag_dists)) if diag_dists.size > 0 else 0.0
    if dgm2.size == 0:
        deaths = np.where(np.isfinite(dgm1[:, 1]), dgm1[:, 1], np.inf)
        diag_dists = np.abs(dgm1[:, 0] - deaths) / 2.0
        return float(np.max(diag_dists)) if diag_dists.size > 0 else 0.0

    max_dist = 0.0

    for birth1, death1 in dgm1:
        if not math.isfinite(death1):
            continue
        min_match_dist = float("inf")
        for birth2, death2 in dgm2:
            if not math.isfinite(death2):
                continue
            dist = max(abs(birth1 - birth2), abs(death1 - death2))
            min_match_dist = min(min_match_dist, dist)

        diag_dist = abs(birth1 - death1) / 2.0
        point_contrib = min(min_match_dist, diag_dist)
        max_dist = max(max_dist, point_contrib)

    for birth2, death2 in dgm2:
        if not math.isfinite(death2):
            continue
        min_match_dist = float("inf")
        for birth1, death1 in dgm1:
            if not math.isfinite(death1):
                continue
            dist = max(abs(birth1 - birth2), abs(death1 - death2))
            min_match_dist = min(min_match_dist, dist)

        diag_dist = abs(birth2 - death2) / 2.0
        point_contrib = min(min_match_dist, diag_dist)
        max_dist = max(max_dist, point_contrib)

    return float(max_dist)


def persistence_statistics(diagram: np.ndarray) -> dict[str, Any]:
    """Compute summary statistics for a persistence diagram.

    Returns: lifetimes, finite_pairs, max_lifetime, mean_lifetime, count.
    """
    if diagram.size == 0:
        return {
            "count": 0,
            "finite_pairs": 0,
            "max_lifetime": None,
            "mean_lifetime": None,
            "median_lifetime": None,
            "total_persistence": 0.0,
        }

    births = diagram[:, 0]
    deaths = diagram[:, 1]
    lifetimes = deaths - births

    finite_mask = np.isfinite(lifetimes)
    finite_lifetimes = lifetimes[finite_mask]

    return {
        "count": int(len(diagram)),
        "finite_pairs": int(np.sum(finite_mask)),
        "max_lifetime": float(np.max(finite_lifetimes)) if finite_lifetimes.size > 0 else None,
        "mean_lifetime": float(np.mean(finite_lifetimes)) if finite_lifetimes.size > 0 else None,
        "median_lifetime": float(np.median(finite_lifetimes)) if finite_lifetimes.size > 0 else None,
        "total_persistence": float(np.sum(finite_lifetimes)),
    }


def persistence_to_dict(
    diagrams: dict[int, np.ndarray],
    betti_numbers: list[int] | None = None,
) -> dict[str, Any]:
    """Convert GUDHI persistence output to JSON-serializable dict.

    Args:
        diagrams: {dimension: (n, 2) ndarray of (birth, death)}
        betti_numbers: [b0, b1, ...] (optional)

    Returns: dict with "diagrams", "statistics", "betti_numbers" keys.
    """
    result: dict[str, Any] = {
        "diagrams": {},
        "statistics": {},
    }

    for dim, dgm in diagrams.items():
        result["diagrams"][str(dim)] = serialize_diagram(dgm)
        result["statistics"][str(dim)] = persistence_statistics(dgm)

    if betti_numbers is not None:
        result["betti_numbers"] = betti_numbers

    return result


def dict_to_persistence(data: dict[str, Any]) -> tuple[dict[int, np.ndarray], list[int]]:
    """Reconstruct persistence diagrams from JSON-serialized dict.

    Returns: (diagrams, betti_numbers)
    """
    diagrams = {}
    for dim_str, dgm_data in data.get("diagrams", {}).items():
        dim = int(dim_str)
        diagrams[dim] = deserialize_diagram(dgm_data)

    betti_numbers = data.get("betti_numbers", [])

    return diagrams, betti_numbers


def persistence_json_roundtrip(data: dict[str, Any]) -> dict[str, Any]:
    """Verify JSON serialization/deserialization roundtrip."""
    json_str = json.dumps(data)
    deserialized = json.loads(json_str)
    diagrams, betti = dict_to_persistence(deserialized)
    return persistence_to_dict(diagrams, betti)
