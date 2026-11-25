"""Input validation and scientific semantics guardrails for TDA adapters.

Enforces:
- Strict shape and finiteness validation for point clouds (N, D) and distance matrices (N, N).
- Non-negative, symmetric, zero-diagonal distance matrix verification.
- Preservation and permutation tracking of node orderings.
- Strict scientific separation: graph beta-1 cycle ranks are never labeled as spatial topological charge.
"""
from __future__ import annotations

from typing import Sequence
import numpy as np

from .types import InputKind


FORBIDDEN_SPATIAL_LABELS = {
    "spatial_charge",
    "spatial_topological_charge",
    "winding_charge",
    "vortex_charge",
    "phase_winding",
    "winding_number",
    "topological_charge",
    "spatial_winding",
    "phase_vortex_charge",
    "spatial_vortex",
}


def assert_not_spatial_charge(label: str, context: str = "") -> None:
    """Enforce strict scientific separation between graph beta-1 and spatial topological charge.

    Graph beta-1 represents cycle rank in topological homology (H1).
    Spatial topological charge represents phase winding over physical coordinate space.
    Conflating them is mathematically and scientifically invalid.
    """
    normalized = label.strip().lower().replace("-", "_").replace(" ", "_")
    for forbidden in FORBIDDEN_SPATIAL_LABELS:
        if forbidden in normalized:
            ctx_msg = f" in context '{context}'" if context else ""
            raise ValueError(
                f"Scientific semantics violation{ctx_msg}: Label '{label}' refers to spatial topological charge. "
                "Graph beta-1 cycle counts must never be labeled or treated as spatial topological charge or winding number."
            )


def validate_point_cloud(points: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    """Validate that points form a finite, real-valued (N, D) point cloud with N >= 2, D >= 1."""
    if np.iscomplexobj(points):
        raise ValueError("Point cloud must be real-valued, got complex input")
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"Point cloud must be 2-dimensional (samples, dimensions), got ndim={arr.ndim}")
    n, d = arr.shape
    if n < 2:
        raise ValueError(f"Point cloud must contain at least 2 points, got {n}")
    if d < 1:
        raise ValueError(f"Point cloud must have at least 1 dimension, got {d}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Point cloud contains non-finite values (NaN or Inf)")
    return arr


def validate_distance_matrix(matrix: np.ndarray | Sequence[Sequence[float]], atol: float = 1e-6) -> np.ndarray:
    """Validate that matrix is a finite, real, symmetric, non-negative square distance matrix with zero diagonal."""
    if atol < 0:
        raise ValueError(f"atol must be non-negative, got {atol}")
    if np.iscomplexobj(matrix):
        raise ValueError("Distance matrix must be real-valued, got complex input")
    arr = np.asarray(matrix, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"Distance matrix must be 2-dimensional, got ndim={arr.ndim}")
    n, m = arr.shape
    if n != m:
        raise ValueError(f"Distance matrix must be square (N, N), got shape ({n}, {m})")
    if n < 2:
        raise ValueError(f"Distance matrix must have size at least (2, 2), got ({n}, {n})")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Distance matrix contains non-finite values (NaN or Inf)")
    if np.any(arr < -atol):
        raise ValueError(f"Distance matrix contains negative entries (min={np.min(arr)})")

    # Verify symmetry
    diff = np.abs(arr - arr.T)
    if np.max(diff) > atol:
        raise ValueError(f"Distance matrix is not symmetric (max asymmetry={np.max(diff):.6e})")

    # Verify zero diagonal
    diag = np.abs(np.diag(arr))
    if np.max(diag) > atol:
        raise ValueError(f"Distance matrix diagonal must be 0, got max diagonal={np.max(diag):.6e}")

    # Canonicalize: enforce exact symmetry and zero diagonal
    canonical = (arr + arr.T) / 2.0
    np.fill_diagonal(canonical, 0.0)
    canonical = np.maximum(canonical, 0.0)
    return canonical


def validate_input(
    data: np.ndarray | Sequence[Any],
    input_kind: InputKind | str | None = None,
) -> tuple[np.ndarray, InputKind]:
    """Validate input data as either a point cloud or a distance matrix.

    If input_kind is None, infers kind based on shape and properties.
    """
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"Input must be a 2D array, got ndim={arr.ndim}")

    if input_kind is not None:
        if isinstance(input_kind, str):
            input_kind = InputKind(input_kind)
        if input_kind == InputKind.POINT_CLOUD:
            return validate_point_cloud(arr), InputKind.POINT_CLOUD
        elif input_kind == InputKind.DISTANCE_MATRIX:
            return validate_distance_matrix(arr), InputKind.DISTANCE_MATRIX
        else:
            raise ValueError(f"Unsupported input kind: {input_kind}")

    # Infer kind
    n, m = arr.shape
    if n == m and n >= 2:
        # Check if it looks like a valid distance matrix
        diag_zero = np.allclose(np.diag(arr), 0.0, atol=1e-6)
        symmetric = np.allclose(arr, arr.T, atol=1e-6)
        non_neg = np.all(arr >= -1e-6)
        if diag_zero and symmetric and non_neg:
            return validate_distance_matrix(arr), InputKind.DISTANCE_MATRIX

    return validate_point_cloud(arr), InputKind.POINT_CLOUD


def reorder_input(data: np.ndarray, input_kind: InputKind, order: Sequence[int]) -> np.ndarray:
    """Permute the nodes/points in data according to order."""
    order_arr = np.asarray(order, dtype=np.int64)
    n = data.shape[0]
    if len(order_arr) != n or set(order_arr) != set(range(n)):
        raise ValueError(f"order must be a permutation of 0..{n - 1}, got {order_arr}")

    if input_kind == InputKind.POINT_CLOUD:
        return data[order_arr, :]
    elif input_kind == InputKind.DISTANCE_MATRIX:
        return data[np.ix_(order_arr, order_arr)]
    else:
        raise ValueError(f"Unsupported input kind: {input_kind}")
