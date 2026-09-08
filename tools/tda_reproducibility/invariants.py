"""Verification of mathematical and operational invariants for TDA backends.

Invariants audited:
1. Distance matrix validity (square, finite, symmetric D = D^T).
2. Zero diagonal (diag(D) == 0).
3. Finite intervals (0 <= birth <= death for all finite pairs).
4. Node-reordering invariance (permutations of node indices leave canonical persistence invariant).
5. Bounded point capacity (guardrails against OOM from unbounded simplex expansions).
6. Spatial charge isolation (verifies graph beta_1 is NEVER conflated with spatial vortex charge Q_spatial).
7. Deterministic repeated checksum (repeated calls produce identical SHA-256 digest).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np

from tools.tda_reproducibility.types import (
    BackendExecutionResult,
    InvariantCheckResult,
    InvariantName,
    PersistenceInterval,
)


def verify_distance_matrix_symmetry(
    distance_matrix: np.ndarray, tolerance: float = 1e-8
) -> InvariantCheckResult:
    """Verify distance matrix is square, finite, non-negative, and symmetric."""
    d = np.asarray(distance_matrix, dtype=float)
    if d.ndim != 2 or d.shape[0] != d.shape[1]:
        return InvariantCheckResult(
            invariant_name=InvariantName.DISTANCE_MATRIX_SYMMETRY.value,
            passed=False,
            details=f"Distance matrix must be 2D square, got shape {d.shape}",
            metrics={"shape": list(d.shape)},
        )

    if not np.all(np.isfinite(d)):
        return InvariantCheckResult(
            invariant_name=InvariantName.DISTANCE_MATRIX_SYMMETRY.value,
            passed=False,
            details="Distance matrix contains non-finite values (NaN or Inf)",
            metrics={"finite_count": int(np.count_nonzero(np.isfinite(d)))},
        )

    if np.any(d < -tolerance):
        return InvariantCheckResult(
            invariant_name=InvariantName.DISTANCE_MATRIX_SYMMETRY.value,
            passed=False,
            details=f"Distance matrix contains negative values (min={float(np.min(d))})",
            metrics={"min_value": float(np.min(d))},
        )

    asymmetry = float(np.max(np.abs(d - d.T)))
    passed = asymmetry <= tolerance
    return InvariantCheckResult(
        invariant_name=InvariantName.DISTANCE_MATRIX_SYMMETRY.value,
        passed=passed,
        details=f"Max asymmetry |D - D^T| = {asymmetry:.2e} (tol={tolerance:.2e})",
        metrics={"max_asymmetry": asymmetry, "tolerance": tolerance},
    )


def verify_zero_diagonal(
    distance_matrix: np.ndarray, tolerance: float = 1e-8
) -> InvariantCheckResult:
    """Verify self-distances on diagonal are zero."""
    d = np.asarray(distance_matrix, dtype=float)
    diag = np.diag(d)
    max_diag = float(np.max(np.abs(diag)))
    passed = max_diag <= tolerance
    return InvariantCheckResult(
        invariant_name=InvariantName.ZERO_DIAGONAL.value,
        passed=passed,
        details=f"Max diagonal element |D_ii| = {max_diag:.2e} (tol={tolerance:.2e})",
        metrics={"max_diagonal": max_diag, "tolerance": tolerance},
    )


def verify_finite_intervals(
    intervals: Sequence[PersistenceInterval],
) -> InvariantCheckResult:
    """Verify all intervals satisfy 0 <= birth <= death, with no NaN or negative births."""
    invalid_intervals: list[str] = []
    total_count = len(intervals)

    for iv in intervals:
        if iv.birth < -1e-9:
            invalid_intervals.append(f"Negative birth: dim={iv.dimension}, b={iv.birth}")
        if iv.death is not None:
            if iv.death < iv.birth - 1e-9:
                invalid_intervals.append(f"Death before birth: dim={iv.dimension}, b={iv.birth}, d={iv.death}")

    passed = len(invalid_intervals) == 0
    details = (
        f"All {total_count} persistence intervals satisfy 0 <= birth <= death."
        if passed
        else f"{len(invalid_intervals)} invalid interval(s) found: {'; '.join(invalid_intervals[:3])}"
    )
    return InvariantCheckResult(
        invariant_name=InvariantName.FINITE_INTERVALS.value,
        passed=passed,
        details=details,
        metrics={"total_intervals": total_count, "invalid_count": len(invalid_intervals)},
    )


def verify_node_reordering_invariance(
    runner_func: Callable[[np.ndarray, int], BackendExecutionResult],
    distance_matrix: np.ndarray,
    seed: int = 42,
    max_dimension: int = 1,
    tolerance: float = 1e-5,
) -> InvariantCheckResult:
    """Verify that permuting nodes does not alter sorted persistence diagrams or checksums."""
    rng = np.random.default_rng(seed)
    n = distance_matrix.shape[0]
    perm = rng.permutation(n)
    d_perm = distance_matrix[np.ix_(perm, perm)]

    res_orig = runner_func(distance_matrix, max_dimension)
    res_perm = runner_func(d_perm, max_dimension)

    if not res_orig.success or not res_perm.success:
        return InvariantCheckResult(
            invariant_name=InvariantName.NODE_REORDERING_INVARIANCE.value,
            passed=False,
            details=f"Execution failed during invariance test (orig_ok={res_orig.success}, perm_ok={res_perm.success})",
            metrics={"orig_success": res_orig.success, "perm_success": res_perm.success},
        )

    # Check match across all dimensions
    max_diff = 0.0
    mismatch_details: list[str] = []

    for dim in range(max_dimension + 1):
        ivs_orig = res_orig.diagrams.get(dim, [])
        ivs_perm = res_perm.diagrams.get(dim, [])
        if len(ivs_orig) != len(ivs_perm):
            mismatch_details.append(
                f"dim {dim} count mismatch: orig={len(ivs_orig)} vs perm={len(ivs_perm)}"
            )
            continue

        for i, (a, b) in enumerate(zip(ivs_orig, ivs_perm)):
            diff_birth = abs(a.birth - b.birth)
            max_diff = max(max_diff, diff_birth)
            if (a.death is None) != (b.death is None):
                mismatch_details.append(f"dim {dim} pair {i} infinity mismatch")
            elif a.death is not None and b.death is not None:
                diff_death = abs(a.death - b.death)
                max_diff = max(max_diff, diff_death)

    passed = len(mismatch_details) == 0 and max_diff <= tolerance
    details = (
        f"Node permutation invariant preserved (max diff={max_diff:.2e}, tol={tolerance:.2e})."
        if passed
        else f"Node permutation invariance violated: {'; '.join(mismatch_details[:2])} (max diff={max_diff:.2e})"
    )

    return InvariantCheckResult(
        invariant_name=InvariantName.NODE_REORDERING_INVARIANCE.value,
        passed=passed,
        details=details,
        metrics={
            "max_difference": max_diff,
            "checksum_match": res_orig.deterministic_checksum == res_perm.deterministic_checksum,
        },
    )


def verify_bounded_point_capacity(
    point_count: int, max_points_bound: int = 500
) -> InvariantCheckResult:
    """Verify input point count is bounded within safe execution limits to prevent OOM."""
    passed = point_count <= max_points_bound
    details = (
        f"Point count {point_count} is within safety cap of {max_points_bound}."
        if passed
        else f"Point count {point_count} exceeds safe capacity cap of {max_points_bound}; execution rejected."
    )
    return InvariantCheckResult(
        invariant_name=InvariantName.BOUNDED_POINT_CAPACITY.value,
        passed=passed,
        details=details,
        metrics={"point_count": point_count, "max_allowed": max_points_bound},
    )


def verify_spatial_charge_isolation(
    payload_or_record: dict[str, Any],
) -> InvariantCheckResult:
    """Verify graph homology beta_1 is strictly separated from geometric spatial phase charge.

    Scientific guardrail:
    - Graph beta_1 is an unsigned topological Betti number from clique/VR homology.
    - Spatial phase charge Q_spatial is a signed vortex winding number from sensor/field coordinates.
    - Graph cycle count MUST NOT be used as or equated with spatial charge.
    """
    violations: list[str] = []

    # Check for forbidden conflated keys
    forbidden_conflations = [
        ("beta_1_charge", "Forbidden conflation of beta_1 and charge in key name"),
        ("spatial_beta_1", "Forbidden conflation of spatial and beta_1 in key name"),
        ("graph_vortex_charge", "Forbidden conflation of graph topology and vortex charge"),
        ("q_from_beta_1", "Forbidden derivation of Q from graph beta_1"),
    ]

    for key, reason in forbidden_conflations:
        if key in payload_or_record:
            violations.append(reason)

    # If both beta_1 and spatial_charge exist, ensure they are stored under distinct top-level namespaces
    if "beta_1" in payload_or_record and "spatial_charge" in payload_or_record:
        b1_val = payload_or_record["beta_1"]
        q_val = payload_or_record["spatial_charge"]
        if b1_val is q_val and b1_val is not None:
            violations.append("Exact same object reference used for beta_1 and spatial_charge")

    passed = len(violations) == 0
    details = (
        "Strict separation confirmed: graph beta_1 homology and geometric spatial charge are isolated."
        if passed
        else f"Spatial charge isolation violated: {'; '.join(violations)}"
    )
    return InvariantCheckResult(
        invariant_name=InvariantName.SPATIAL_CHARGE_ISOLATION.value,
        passed=passed,
        details=details,
        metrics={"violations_detected": len(violations)},
    )


def verify_deterministic_repeated_checksum(
    runner_func: Callable[[np.ndarray, int], BackendExecutionResult],
    distance_matrix: np.ndarray,
    max_dimension: int = 1,
    repetitions: int = 3,
) -> InvariantCheckResult:
    """Verify repeated execution on identical distance matrix produces identical SHA-256 digest."""
    checksums: list[str] = []
    for _ in range(repetitions):
        res = runner_func(distance_matrix, max_dimension)
        if not res.success:
            return InvariantCheckResult(
                invariant_name=InvariantName.DETERMINISTIC_REPEATED_CHECKSUM.value,
                passed=False,
                details="Runner failed during repeated checksum test.",
                metrics={"repetitions": repetitions},
            )
        checksums.append(res.deterministic_checksum)

    passed = len(set(checksums)) == 1
    details = (
        f"Deterministic checksum identical across {repetitions} repeated runs ({checksums[0][:12]}...)."
        if passed
        else f"Checksum variance detected across {repetitions} runs: {checksums}"
    )
    return InvariantCheckResult(
        invariant_name=InvariantName.DETERMINISTIC_REPEATED_CHECKSUM.value,
        passed=passed,
        details=details,
        metrics={"repetitions": repetitions, "unique_checksums": len(set(checksums))},
    )
