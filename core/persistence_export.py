"""JSON-serializable persistence diagram export and analysis."""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .topology import diagram_bottleneck_distance


def serialize_diagram(diagram: np.ndarray) -> list[list[float | None]]:
    """Convert a persistence diagram to JSON-safe pairs."""
    values = np.asarray(diagram, dtype=float)
    if values.size == 0:
        return []
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("diagram must have shape (n, 2)")
    result: list[list[float | None]] = []
    for birth, death in values:
        result.append([float(birth), None if not math.isfinite(death) else float(death)])
    return result


def deserialize_diagram(data: list) -> np.ndarray:
    """Reconstruct a persistence diagram from serialized pairs."""
    if not data:
        return np.empty((0, 2), dtype=float)
    pairs: list[list[float]] = []
    for birth, death in data:
        pairs.append([float(birth), np.inf if death is None else float(death)])
    return np.asarray(pairs, dtype=float)


def bottleneck_distance(dgm1: np.ndarray, dgm2: np.ndarray) -> float:
    """Delegate to the repo's canonical bottleneck implementation."""
    return diagram_bottleneck_distance(dgm1, dgm2)


def persistence_statistics(diagram: np.ndarray) -> dict[str, Any]:
    """Compute basic summary statistics for a persistence diagram."""
    values = np.asarray(diagram, dtype=float)
    if values.size == 0:
        return {
            "count": 0,
            "finite_pairs": 0,
            "max_lifetime": None,
            "mean_lifetime": None,
            "median_lifetime": None,
            "total_persistence": 0.0,
        }
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("diagram must have shape (n, 2)")
    lifetimes = values[:, 1] - values[:, 0]
    finite_mask = np.isfinite(lifetimes)
    finite_lifetimes = lifetimes[finite_mask]
    return {
        "count": int(len(values)),
        "finite_pairs": int(np.sum(finite_mask)),
        "max_lifetime": float(np.max(finite_lifetimes)) if finite_lifetimes.size else None,
        "mean_lifetime": float(np.mean(finite_lifetimes)) if finite_lifetimes.size else None,
        "median_lifetime": float(np.median(finite_lifetimes)) if finite_lifetimes.size else None,
        "total_persistence": float(np.sum(finite_lifetimes)),
    }


def persistence_to_dict(
    diagrams: dict[int, np.ndarray],
    betti_numbers: list[int] | None = None,
) -> dict[str, Any]:
    """Convert GUDHI persistence output to JSON-serializable data."""
    result: dict[str, Any] = {"diagrams": {}, "statistics": {}}
    for dim, dgm in diagrams.items():
        result["diagrams"][str(dim)] = serialize_diagram(dgm)
        result["statistics"][str(dim)] = persistence_statistics(dgm)
    if betti_numbers is not None:
        result["betti_numbers"] = betti_numbers
    return result


def dict_to_persistence(data: dict[str, Any]) -> tuple[dict[int, np.ndarray], list[int]]:
    """Reconstruct persistence diagrams from serialized persistence data."""
    diagrams: dict[int, np.ndarray] = {}
    for dim_str, dgm_data in data.get("diagrams", {}).items():
        diagrams[int(dim_str)] = deserialize_diagram(dgm_data)
    return diagrams, list(data.get("betti_numbers", []))


def persistence_json_roundtrip(data: dict[str, Any]) -> dict[str, Any]:
    """Round-trip a persistence payload through JSON serialization."""
    return persistence_to_dict(*dict_to_persistence(json.loads(json.dumps(data))))
