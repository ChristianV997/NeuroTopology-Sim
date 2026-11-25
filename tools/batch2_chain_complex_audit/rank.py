"""Exact rational matrix rank and float SVD rank comparison.

Stdlib ``fractions.Fraction`` Gaussian elimination only — no SciPy.
Numpy is used solely for optional SVD sensitivity reporting.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Sequence

import numpy as np


def exact_rank(matrix: Sequence[Sequence[Fraction | int]]) -> int:
    """Row-reduce over Q and return matrix rank (number of nonzero pivots)."""
    if not matrix:
        return 0
    rows = len(matrix)
    cols = len(matrix[0])
    if cols == 0:
        return 0
    a: list[list[Fraction]] = [
        [Fraction(x) for x in row] for row in matrix
    ]
    if any(len(row) != cols for row in a):
        raise ValueError("ragged matrix")

    rank = 0
    row = 0
    for col in range(cols):
        pivot = None
        for r in range(row, rows):
            if a[r][col] != 0:
                pivot = r
                break
        if pivot is None:
            continue
        a[row], a[pivot] = a[pivot], a[row]
        piv = a[row][col]
        a[row] = [v / piv for v in a[row]]
        for r in range(rows):
            if r == row:
                continue
            factor = a[r][col]
            if factor == 0:
                continue
            a[r] = [a[r][c] - factor * a[row][c] for c in range(cols)]
        rank += 1
        row += 1
        if row == rows:
            break
    return rank


def float_svd_rank(
    matrix: Sequence[Sequence[Fraction | int | float]],
    *,
    tol: float,
) -> int:
    """Numerical rank via numpy SVD with an explicit singular-value tolerance.

    Callers must supply ``tol``; this helper never silently picks one.
    """
    if tol < 0:
        raise ValueError("tol must be non-negative")
    if not matrix:
        return 0
    arr = np.asarray([[float(x) for x in row] for row in matrix], dtype=float)
    if arr.size == 0:
        return 0
    if arr.ndim != 2:
        raise ValueError("matrix must be 2-D")
    # Empty dimension
    if 0 in arr.shape:
        return 0
    singular = np.linalg.svd(arr, compute_uv=False)
    return int(np.sum(singular > tol))


def svd_rank_sensitivity(
    matrix: Sequence[Sequence[Fraction | int | float]],
    tolerances: Sequence[float],
) -> dict:
    """Compare exact rational rank to SVD ranks across declared tolerances.

    Returns a report dict; does **not** select a preferred tolerance.
    When SVD ranks disagree across the supplied tolerances, ``unstable`` is True.
    """
    exact = exact_rank(matrix)
    by_tol: dict[str, int] = {}
    for tol in tolerances:
        by_tol[repr(tol)] = float_svd_rank(matrix, tol=tol)
    values = list(by_tol.values())
    unstable = len(set(values)) > 1
    mismatches = {k: v for k, v in by_tol.items() if v != exact}
    return {
        "exact_rank": exact,
        "svd_ranks_by_tol": by_tol,
        "unstable": unstable,
        "mismatches_vs_exact": mismatches,
        "agrees_all_tols": not mismatches and not unstable,
    }
