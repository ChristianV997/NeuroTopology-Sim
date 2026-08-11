"""JSON-safe persistence diagram export backed by the canonical topology code."""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .topology import diagram_bottleneck_distance


def serialize_diagram(diagram: np.ndarray) -> list[list[float | None]]:
    """Convert an ``(n, 2)`` persistence diagram to JSON-safe pairs."""
    values = np.asarray(diagram, dtype=float)
    if values.size == 0:
        return []
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("diagram must have shape (n, 2)")
    return [
        [float(birth), None if not math.isfinite(death) else float(death)]
        for birth, death in values
    ]


def deserialize_diagram(data: list) -> np.ndarray:
    """Reconstruct an ``(n, 2)`` diagram from serialized pairs."""
    if not data:
        return np.empty((0, 2), dtype=float)
    values = np.asarray(
        [[float(birth), np.inf if death is None else float(death)] for birth, death in data],
        dtype=float,
    )
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("serialized diagram must contain pairs")
    return values


def bottleneck_distance(dgm1: np.ndarray, dgm2: np.ndarray) -> float:
    """Delegate to the repository's canonical GUDHI-backed implementation."""
    return diagram_bottleneck_distance(dgm1, dgm2)


def persistence_statistics(diagram: np.ndarray) -> dict[str, Any]:
    """Compute finite lifetime summaries without treating infinity as a value."""
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
    finite = lifetimes[np.isfinite(lifetimes)]
    return {
        "count": int(len(values)),
        "finite_pairs": int(finite.size),
        "max_lifetime": float(np.max(finite)) if finite.size else None,
        "mean_lifetime": float(np.mean(finite)) if finite.size else None,
        "median_lifetime": float(np.median(finite)) if finite.size else None,
        "total_persistence": float(np.sum(finite)),
    }


def persistence_to_dict(
    diagrams: dict[int, np.ndarray],
    betti_numbers: list[int] | None = None,
) -> dict[str, Any]:
    """Convert GUDHI persistence output to a JSON-serializable mapping."""
    result: dict[str, Any] = {"diagrams": {}, "statistics": {}}
    for dimension, diagram in diagrams.items():
        key = str(dimension)
        result["diagrams"][key] = serialize_diagram(diagram)
        result["statistics"][key] = persistence_statistics(diagram)
    if betti_numbers is not None:
        result["betti_numbers"] = list(betti_numbers)
    return result


def dict_to_persistence(data: dict[str, Any]) -> tuple[dict[int, np.ndarray], list[int]]:
    """Reconstruct diagrams and Betti numbers from a serialized mapping."""
    diagrams = {
        int(dimension): deserialize_diagram(diagram)
        for dimension, diagram in data.get("diagrams", {}).items()
    }
    return diagrams, list(data.get("betti_numbers", []))


def persistence_json_roundtrip(data: dict[str, Any]) -> dict[str, Any]:
    """Round-trip a persistence payload through the JSON encoder."""
    diagrams, betti_numbers = dict_to_persistence(json.loads(json.dumps(data)))
    return persistence_to_dict(diagrams, betti_numbers)
