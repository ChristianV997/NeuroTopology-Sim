"""Allocation-bounded topology aggregation for the PITNN LLG path.

``TopologicalInvariantTracker.audit_snapshot`` computes the chirality density
once for charge/extrema and then computes it a second time for the beta-1
proxy.  ``audit_snapshot_reuse`` keeps the same equations, units, threshold,
and dictionary contract while reusing that one density array.  The tracker is
passed in so validation and metric definitions remain owned by the existing
topology implementation.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def audit_snapshot_reuse(
    tracker: Any,
    spins: np.ndarray,
    threshold: float = 0.3,
) -> dict[str, Any]:
    """Return one topology snapshot without recomputing chirality density.

    The call order intentionally matches the existing method: spin validation
    occurs before threshold validation, and the returned keys/values use the
    existing tracker methods and equations.  No state is retained between
    snapshots, so deterministic behavior and the public tracker API are
    unchanged.
    """
    density = tracker.compute_chirality_density(spins)
    winding = tracker.compute_winding_number(spins)
    if threshold < 0.0 or not np.isfinite(threshold):
        raise ValueError("threshold must be finite and non-negative")
    return {
        "winding_number": winding,
        "topological_charge": float(np.sum(density) / (4.0 * np.pi)),
        "beta1_loops": int(np.count_nonzero(np.abs(density) > threshold)),
        "max_chirality": float(np.max(np.abs(density))),
        "mean_chirality": float(np.mean(density)),
    }
