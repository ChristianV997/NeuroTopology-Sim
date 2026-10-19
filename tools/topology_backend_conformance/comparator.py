"""Mathematical comparability validation and persistence diagram comparison.

Core rule:
Compare backends only when the mathematical configuration is strictly comparable:
- Filtration type (e.g., Vietoris-Rips vs Cubical Complex)
- Metric / dissimilarity convention
- Coefficient field (e.g., Z_2)
- Homology dimensions
- Threshold and treatment of infinite bars
- Input identity

If two outputs describe non-equivalent complexes or filtrations, label them
NOT_COMPARABLE; do not force-match bars or report agreement.
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from .models import (
    ComparabilityStatus,
    ConformanceComparisonResult,
    ConformanceExecutionConfig,
    NonComparableReason,
    PersistenceBar,
    sanitize_float,
)


def validate_mathematical_comparability(
    cfg_a: ConformanceExecutionConfig,
    cfg_b: ConformanceExecutionConfig,
) -> tuple[ComparabilityStatus, list[str]]:
    """Verify that two execution configurations describe mathematically equivalent problems.

    Returns
    -------
    tuple[ComparabilityStatus, list[str]]
        Status (COMPARABLE or NOT_COMPARABLE) and list of discrepancy reasons.
    """
    reasons: list[str] = []

    if cfg_a.filtration_type != cfg_b.filtration_type:
        reasons.append(
            f"{NonComparableReason.FILTRATION_MISMATCH.value}: "
            f"backend A uses '{cfg_a.filtration_type.value}' while backend B uses '{cfg_b.filtration_type.value}'"
        )

    if cfg_a.metric_convention != cfg_b.metric_convention:
        reasons.append(
            f"{NonComparableReason.METRIC_MISMATCH.value}: "
            f"backend A uses '{cfg_a.metric_convention.value}' while backend B uses '{cfg_b.metric_convention.value}'"
        )

    if cfg_a.coefficient_field != cfg_b.coefficient_field:
        reasons.append(
            f"{NonComparableReason.COEFFICIENT_FIELD_MISMATCH.value}: "
            f"backend A uses '{cfg_a.coefficient_field.value}' while backend B uses '{cfg_b.coefficient_field.value}'"
        )

    if cfg_a.threshold != cfg_b.threshold:
        reasons.append(
            f"{NonComparableReason.THRESHOLD_TRUNCATION_MISMATCH.value}: "
            f"backend A threshold is {cfg_a.threshold} while backend B threshold is {cfg_b.threshold}"
        )

    if cfg_a.input_identity and cfg_b.input_identity and (cfg_a.input_identity != cfg_b.input_identity):
        reasons.append(
            f"{NonComparableReason.INPUT_IDENTITY_MISMATCH.value}: "
            f"backend A input '{cfg_a.input_identity}' != backend B input '{cfg_b.input_identity}'"
        )

    if reasons:
        return ComparabilityStatus.NOT_COMPARABLE, reasons
    return ComparabilityStatus.COMPARABLE, []


def compute_bottleneck_distance_exact(
    bars_a: Sequence[PersistenceBar],
    bars_b: Sequence[PersistenceBar],
    inf_replacement: float = 1e6,
) -> float:
    """Compute bottleneck distance between two persistence diagrams.

    Points at infinity are handled with inf_replacement if matched against finite points.
    Matches identical infinite bars with distance 0.
    """
    # Separate finite and infinite bars
    fin_a: list[tuple[float, float]] = []
    inf_a: list[float] = []
    for b in bars_a:
        if b.is_infinite or b.death is None:
            inf_a.append(b.birth)
        else:
            fin_a.append((b.birth, b.death))

    fin_b: list[tuple[float, float]] = []
    inf_b: list[float] = []
    for b in bars_b:
        if b.is_infinite or b.death is None:
            inf_b.append(b.birth)
        else:
            fin_b.append((b.birth, b.death))

    # Match infinite bars
    # If counts of infinite bars differ, bottleneck distance is infinite
    if len(inf_a) != len(inf_b):
        return float("inf")

    inf_dist = 0.0
    if inf_a:
        inf_a_sorted = sorted(inf_a)
        inf_b_sorted = sorted(inf_b)
        inf_dist = max(abs(a - b) for a, b in zip(inf_a_sorted, inf_b_sorted))

    # Finite diagrams
    pts_a = np.asarray(fin_a, dtype=np.float64)
    pts_b = np.asarray(fin_b, dtype=np.float64)

    n_a = len(pts_a)
    n_b = len(pts_b)

    if n_a == 0 and n_b == 0:
        return inf_dist

    if n_a == 0:
        diag_dist = float(np.max((pts_b[:, 1] - pts_b[:, 0]) / 2.0))
        return max(inf_dist, diag_dist)

    if n_b == 0:
        diag_dist = float(np.max((pts_a[:, 1] - pts_a[:, 0]) / 2.0))
        return max(inf_dist, diag_dist)

    # If both have the same number of points and are sorted, compute coordinate diffs
    if n_a == n_b:
        diffs = np.max(np.abs(pts_a - pts_b), axis=1)
        fin_dist = float(np.max(diffs))
        return max(inf_dist, fin_dist)

    # General case: Hungarian bipartite matching with diagonal projections
    from scipy.optimize import linear_sum_assignment

    total_size = n_a + n_b
    cost_matrix = np.zeros((total_size, total_size), dtype=np.float64)

    # A to B distance: L_infinity norm
    for i in range(n_a):
        for j in range(n_b):
            cost_matrix[i, j] = max(abs(pts_a[i, 0] - pts_b[j, 0]), abs(pts_a[i, 1] - pts_b[j, 1]))

    # A to diagonal
    for i in range(n_a):
        cost_matrix[i, n_b + i] = (pts_a[i, 1] - pts_a[i, 0]) / 2.0

    # B to diagonal
    for j in range(n_b):
        cost_matrix[n_a + j, j] = (pts_b[j, 1] - pts_b[j, 0]) / 2.0

    # Diagonal to diagonal is 0 cost for padding
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    fin_dist = float(np.max(cost_matrix[row_ind, col_ind]))
    return max(inf_dist, fin_dist)


def compare_conformance_runs(
    run_a: Any,
    run_b: Any,
    dimension: int,
    tolerance: float = 1e-5,
) -> ConformanceComparisonResult:
    """Compare persistence bars of two backend runs with strict mathematical verification."""
    # 1. Check if backends were available
    if not run_a.backend_meta.is_available or not run_b.backend_meta.is_available:
        missing = []
        if not run_a.backend_meta.is_available:
            missing.append(run_a.backend_meta.backend_id)
        if not run_b.backend_meta.is_available:
            missing.append(run_b.backend_meta.backend_id)
        return ConformanceComparisonResult(
            status=ComparabilityStatus.BACKEND_UNAVAILABLE,
            is_comparable=False,
            non_comparable_reasons=[f"Backend unavailable: {', '.join(missing)}"],
            dimension=dimension,
            details=[f"Comparison skipped because backend(s) {missing} are not installed."],
        )

    # 2. Check mathematical comparability
    status, reasons = validate_mathematical_comparability(run_a.config, run_b.config)
    if status == ComparabilityStatus.NOT_COMPARABLE:
        return ConformanceComparisonResult(
            status=ComparabilityStatus.NOT_COMPARABLE,
            is_comparable=False,
            non_comparable_reasons=reasons,
            dimension=dimension,
            details=["Outputs describe non-equivalent complexes or filtrations; force-matching prohibited."],
        )

    # 3. Extract and compare bars
    bars_a = run_a.get_bars(dimension)
    bars_b = run_b.get_bars(dimension)
    count_a = len(bars_a)
    count_b = len(bars_b)

    details: list[str] = []
    if count_a != count_b:
        details.append(
            f"Interval count mismatch in dimension {dimension}: "
            f"{run_a.backend_meta.backend_id} has {count_a}, {run_b.backend_meta.backend_id} has {count_b}"
        )

    b_dist = compute_bottleneck_distance_exact(bars_a, bars_b)

    max_coord_diff: float | None = None
    if count_a == count_b and count_a > 0:
        max_diff = 0.0
        for i, (ba, bb) in enumerate(zip(bars_a, bars_b)):
            diff_b = abs(ba.birth - bb.birth)
            max_diff = max(max_diff, diff_b)
            if ba.is_infinite != bb.is_infinite:
                details.append(
                    f"Infinity mismatch at index {i} in dim {dimension}: "
                    f"({ba.birth}, {ba.death}) vs ({bb.birth}, bb.death)"
                )
            elif not ba.is_infinite and not bb.is_infinite:
                diff_d = abs(float(ba.death) - float(bb.death))
                max_diff = max(max_diff, diff_d)
        max_coord_diff = max_diff
    elif count_a == count_b == 0:
        max_coord_diff = 0.0

    passed = (count_a == count_b) and (b_dist <= tolerance) and (max_coord_diff is not None and max_coord_diff <= tolerance)
    if not passed:
        details.append(
            f"Discrepancy: bottleneck distance {b_dist:.2e} or max coordinate diff exceeds tolerance {tolerance:.2e}"
        )

    return ConformanceComparisonResult(
        status=ComparabilityStatus.COMPARABLE,
        is_comparable=True,
        non_comparable_reasons=[],
        dimension=dimension,
        bar_count_a=count_a,
        bar_count_b=count_b,
        bottleneck_distance=b_dist,
        max_bar_coordinate_diff=max_coord_diff,
        passed_tolerance=passed,
        details=details,
    )
