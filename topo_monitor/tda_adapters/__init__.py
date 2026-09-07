"""Backend-neutral persistent-homology adapter layer for NeuroTopology-Sim.

Provides unified, lazily-imported adapters for:
- Ripser (ripser)
- Ripser++ (ripserplusplus)
- GUDHI (gudhi)
- Giotto-tda (gtda)
- Deterministic NumPy/SciPy fallback for bounded low-dimensional fixtures

Strict scientific separation:
- Graph beta-1 cycle rank is never conflated with spatial topological winding charge.
- Fallback results are marked as approximate/fixture-only.
- All outputs are typed and guaranteed to serialize to null rather than NaN or Infinity.
"""
from __future__ import annotations

from typing import Any, Sequence
import numpy as np

from .base import BaseTDABackend
from .backends import (
    GiottoTDABackend,
    GudhiBackend,
    RipserBackend,
    RipserPlusPlusBackend,
)
from .fallback import DeterministicFallbackBackend
from .landscape import compute_persistence_landscape
from .registry import get_all_capabilities, get_backend, list_available_backends
from .streaming import stream_point_cloud_generator, stream_point_cloud_windows
from .types import (
    BackendCapability,
    BackendCapabilityStatus,
    BackendName,
    InputKind,
    PersistenceInterval,
    PersistencePair,
    ScientificStatus,
    StreamingTDAResult,
    StreamingWindowConfig,
    TDAConfig,
    TDAPersistenceResult,
)
from .validation import (
    assert_not_spatial_charge,
    reorder_input,
    validate_distance_matrix,
    validate_input,
    validate_point_cloud,
)


def compute_persistence(
    data: np.ndarray | Sequence[Any],
    input_kind: InputKind | str | None = None,
    backend: str | None = None,
    config: TDAConfig | None = None,
) -> TDAPersistenceResult:
    """High-level facade to compute persistent homology on point clouds or distance matrices.

    Args:
        data: (N, D) point cloud or (N, N) distance matrix.
        input_kind: Optional InputKind or string ("point_cloud", "distance_matrix"). Inferred if None.
        backend: Optional backend name ("ripser", "gudhi", "deterministic-fallback", etc.).
        config: Optional TDAConfig.

    Returns:
        TDAPersistenceResult with intervals, pairs, landscape, telemetry, and checksum.
    """
    valid_data, inferred_kind = validate_input(data, input_kind)
    adapter = get_backend(backend)
    return adapter.compute(valid_data, inferred_kind, config)


def verify_reordering_invariance(
    data: np.ndarray | Sequence[Any],
    input_kind: InputKind | str | None = None,
    order: Sequence[int] | None = None,
    backend: str | None = None,
    config: TDAConfig | None = None,
) -> bool:
    """Verify that node/point permutation leaves persistence intervals invariant."""
    valid_data, kind = validate_input(data, input_kind)
    n = valid_data.shape[0]
    if order is None:
        order = list(range(n))[::-1]
    reordered = reorder_input(valid_data, kind, order)

    adapter = get_backend(backend)
    res_orig = adapter.compute(valid_data, kind, config)
    res_reord = adapter.compute(reordered, kind, config)

    def _to_comparable(intervals: Sequence[PersistenceInterval]) -> list[tuple[float, float | None]]:
        res = []
        for iv in intervals:
            b = round(float(iv.birth), 6)
            d = round(float(iv.death), 6) if iv.death is not None else None
            res.append((b, d))
        # Sort by birth, then None-last for death
        res.sort(key=lambda item: (item[0], item[1] if item[1] is not None else float("inf")))
        return res

    orig_b0 = _to_comparable(res_orig.beta_0_intervals)
    reord_b0 = _to_comparable(res_reord.beta_0_intervals)
    orig_b1 = _to_comparable(res_orig.beta_1_intervals)
    reord_b1 = _to_comparable(res_reord.beta_1_intervals)

    if len(orig_b0) != len(reord_b0) or len(orig_b1) != len(reord_b1):
        return False

    for (b1, d1), (b2, d2) in zip(orig_b0, reord_b0):
        if not np.isclose(b1, b2, atol=1e-5):
            return False
        if (d1 is None) != (d2 is None):
            return False
        if d1 is not None and not np.isclose(d1, d2, atol=1e-5):
            return False

    for (b1, d1), (b2, d2) in zip(orig_b1, reord_b1):
        if not np.isclose(b1, b2, atol=1e-5):
            return False
        if (d1 is None) != (d2 is None):
            return False
        if d1 is not None and not np.isclose(d1, d2, atol=1e-5):
            return False

    # Also verify landscape area invariance if computed
    if res_orig.landscape_integrated_area is not None and res_reord.landscape_integrated_area is not None:
        if not np.isclose(res_orig.landscape_integrated_area, res_reord.landscape_integrated_area, atol=1e-4):
            return False

    return True


verify_reordering_invariance.__test__ = False  # type: ignore[attr-defined]
test_reordering_invariance = verify_reordering_invariance
test_reordering_invariance.__test__ = False  # type: ignore[attr-defined]


__all__ = [
    "compute_persistence",
    "verify_reordering_invariance",
    "test_reordering_invariance",
    "get_backend",
    "get_all_capabilities",
    "list_available_backends",
    "stream_point_cloud_windows",
    "stream_point_cloud_generator",
    "compute_persistence_landscape",
    "assert_not_spatial_charge",
    "validate_input",
    "validate_point_cloud",
    "validate_distance_matrix",
    "reorder_input",
    "BaseTDABackend",
    "RipserBackend",
    "GudhiBackend",
    "RipserPlusPlusBackend",
    "GiottoTDABackend",
    "DeterministicFallbackBackend",
    "BackendName",
    "BackendCapabilityStatus",
    "InputKind",
    "ScientificStatus",
    "PersistenceInterval",
    "PersistencePair",
    "BackendCapability",
    "TDAConfig",
    "TDAPersistenceResult",
    "StreamingWindowConfig",
    "StreamingTDAResult",
]
