"""Pure-Python linear algebra primitives for whitening, covariance, and SPD projection.

Completely self-contained in standard library (no SciPy, no NumPy required).
Guarantees deterministic, machine-precision operations with explicit fail-closed checks.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from tools.whitening_audit.types import (
    EmptyDataError,
    FeatureDimensionMismatchError,
    InsufficientSamplesError,
    InvalidCovarianceError,
    NonFiniteValuesError,
    NonPositiveDefiniteError,
    SPDRepairReport,
    WhiteningAuditError,
)


def validate_eigenvalue_floor(eigenvalue_floor: float) -> None:
    """Fail closed when the SPD floor is non-positive or non-finite.

    A floor of 0 / negative values silently disables the SPD contract and can
    later crash Cholesky / ZCA with an untyped ZeroDivisionError.
    """
    if not math.isfinite(eigenvalue_floor) or eigenvalue_floor <= 0.0:
        raise WhiteningAuditError(
            f"eigenvalue_floor must be a finite positive float; got {eigenvalue_floor!r}."
        )


# -----------------------------------------------------------------------------
# Input Validation Primitives
# -----------------------------------------------------------------------------

def validate_finite_matrix(X: Sequence[Sequence[float]], name: str = "Matrix") -> None:
    """Ensure matrix is non-empty, rectangular, and contains only finite floats."""
    if not X:
        raise EmptyDataError(f"{name} is empty.")
    n_rows = len(X)
    if not X[0]:
        raise EmptyDataError(f"{name} has zero columns.")
    n_cols = len(X[0])

    for i, row in enumerate(X):
        if len(row) != n_cols:
            raise FeatureDimensionMismatchError(
                f"{name} row {i} has length {len(row)}, expected {n_cols}."
            )
        for j, val in enumerate(row):
            if not math.isfinite(val):
                raise NonFiniteValuesError(
                    f"{name} contains non-finite value ({val}) at position ({i}, {j})."
                )


def validate_square_symmetric(A: Sequence[Sequence[float]], tol: float = 1e-9) -> None:
    """Ensure matrix is square and symmetric within relative/local tolerance.

    Tolerance is relative to the local matrix scale (off-diagonal magnitudes and
    the two diagonal entries). An absolute ``1e-15`` floor is intentionally
    avoided: it previously accepted fully asymmetric micro-scale covariances
    (e.g. off-diagonals ``1e-16`` vs ``0``).
    """
    validate_finite_matrix(A, "Covariance matrix")
    n = len(A)
    for i in range(n):
        if len(A[i]) != n:
            raise InvalidCovarianceError(f"Matrix is not square: {n} rows, row {i} has {len(A[i])} cols.")
        for j in range(i + 1, n):
            a_ij = A[i][j]
            a_ji = A[j][i]
            diff = abs(a_ij - a_ji)
            if diff == 0.0:
                continue
            scale = max(abs(a_ij), abs(a_ji), abs(A[i][i]), abs(A[j][j]))
            eff_tol = tol * scale if scale > 0.0 else 0.0
            if diff > eff_tol:
                raise InvalidCovarianceError(
                    f"Matrix is asymmetric: A[{i}][{j}]={a_ij} vs A[{j}][{i}]={a_ji}."
                )


# -----------------------------------------------------------------------------
# Basic Linear Algebra Primitives
# -----------------------------------------------------------------------------

def matrix_transpose(A: Sequence[Sequence[float]]) -> List[List[float]]:
    """Compute transpose of matrix A."""
    n_rows = len(A)
    n_cols = len(A[0])
    return [[A[r][c] for r in range(n_rows)] for c in range(n_cols)]


def matrix_multiply(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> List[List[float]]:
    """Multiply matrices A (m x k) and B (k x n) -> (m x n)."""
    m = len(A)
    k = len(A[0])
    if len(B) != k:
        raise FeatureDimensionMismatchError(f"Inner dimensions mismatch: A has {k} cols, B has {len(B)} rows.")
    n = len(B[0])

    C = [[0.0] * n for _ in range(m)]
    for i in range(m):
        row_a = A[i]
        for p in range(k):
            a_ip = row_a[p]
            if a_ip != 0.0:
                row_b = B[p]
                for j in range(n):
                    C[i][j] += a_ip * row_b[j]
    return C


def matrix_subtract(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> List[List[float]]:
    """Elementwise subtraction A - B."""
    m = len(A)
    n = len(A[0])
    return [[A[i][j] - B[i][j] for j in range(n)] for i in range(m)]


def matrix_add(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> List[List[float]]:
    """Elementwise addition A + B."""
    m = len(A)
    n = len(A[0])
    return [[A[i][j] + B[i][j] for j in range(n)] for i in range(m)]


def matrix_frobenius_norm(A: Sequence[Sequence[float]]) -> float:
    """Compute Frobenius norm ||A||_F."""
    s = sum(val * val for row in A for val in row)
    return math.sqrt(s)


def identity_matrix(n: int) -> List[List[float]]:
    """Construct n x n identity matrix."""
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


# -----------------------------------------------------------------------------
# Sample Statistics (Train-Only)
# -----------------------------------------------------------------------------

def compute_mean(X: Sequence[Sequence[float]]) -> Tuple[float, ...]:
    """Compute sample mean vector across rows."""
    validate_finite_matrix(X, "Training features")
    n = len(X)
    d = len(X[0])
    means = [0.0] * d
    for row in X:
        for j in range(d):
            means[j] += row[j]
    return tuple(m / n for m in means)


def compute_covariance(
    X: Sequence[Sequence[float]],
    mean: Optional[Sequence[float]] = None,
) -> List[List[float]]:
    """Compute sample covariance matrix with Bessel's correction (n - 1 DOF)."""
    validate_finite_matrix(X, "Features")
    n = len(X)
    if n <= 1:
        raise InsufficientSamplesError(
            f"Cannot compute sample covariance with n = {n} samples (requires n >= 2)."
        )
    d = len(X[0])
    mu = mean if mean is not None else compute_mean(X)
    if len(mu) != d:
        raise FeatureDimensionMismatchError(
            f"Mean vector dimension {len(mu)} does not match feature dimension {d}."
        )

    # Accumulate (x - mu)(x - mu)^T
    cov = [[0.0] * d for _ in range(d)]
    for row in X:
        diff = [row[j] - mu[j] for j in range(d)]
        for i in range(d):
            diff_i = diff[i]
            for j in range(i, d):
                cov[i][j] += diff_i * diff[j]

    scale = 1.0 / (n - 1)
    for i in range(d):
        for j in range(i, d):
            val = cov[i][j] * scale
            cov[i][j] = val
            cov[j][i] = val

    return cov


# -----------------------------------------------------------------------------
# Cholesky Decomposition & Triangular Inversion
# -----------------------------------------------------------------------------

def cholesky_decomposition(A: Sequence[Sequence[float]]) -> List[List[float]]:
    """Compute lower-triangular Cholesky factor L such that A = L * L^T.

    Raises NonPositiveDefiniteError if matrix is not strictly positive definite.
    """
    validate_square_symmetric(A)
    n = len(A)
    L = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = A[i][i] - s
                if val <= 0.0:
                    raise NonPositiveDefiniteError(
                        f"Matrix is not positive definite: diagonal minor at index {i} is {val:.6e} <= 0."
                    )
                L[i][j] = math.sqrt(val)
            else:
                L[i][j] = (A[i][j] - s) / L[j][j]
    return L


def invert_lower_triangular(L: Sequence[Sequence[float]]) -> List[List[float]]:
    """Compute inverse of lower-triangular matrix L via forward substitution."""
    n = len(L)
    inv = [[0.0] * n for _ in range(n)]
    for j in range(n):
        if L[j][j] == 0.0:
            raise NonPositiveDefiniteError(f"Singular triangular matrix: zero diagonal at index {j}.")
        inv[j][j] = 1.0 / L[j][j]
        for i in range(j + 1, n):
            s = sum(L[i][k] * inv[k][j] for k in range(j, i))
            inv[i][j] = -s / L[i][i]
    return inv


# -----------------------------------------------------------------------------
# Jacobi Eigendecomposition for Symmetric Matrices
# -----------------------------------------------------------------------------

def jacobi_eigh(
    A: Sequence[Sequence[float]],
    max_sweeps: int = 60,
    tol: float = 1e-13,
) -> Tuple[List[float], List[List[float]]]:
    """Compute eigenvalues and eigenvectors of real symmetric matrix A.

    Returns (sorted_eigenvalues, sorted_eigenvectors_V) such that A = V * diag(evals) * V^T.
    Eigenvalues are sorted in descending order; V columns are corresponding orthonormal eigenvectors.
    """
    validate_square_symmetric(A)
    n = len(A)
    a = [list(row) for row in A]
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    diags = [abs(A[i][i]) for i in range(n) if abs(A[i][i]) > 0.0]
    diag_min = min(diags) if diags else 1.0
    eff_tol = min(tol, tol * diag_min)

    for sweep in range(max_sweeps):
        max_off = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) > max_off:
                    max_off = abs(a[p][q])

        if max_off < eff_tol:
            break

        for p in range(n):
            for q in range(p + 1, n):
                apq = a[p][q]
                app = a[p][p]
                aqq = a[q][q]
                eps_scale = 1e-16 * max(abs(app), abs(aqq))
                if abs(apq) <= eps_scale:
                    continue
                tau = (aqq - app) / (2.0 * apq)
                t = (1.0 if tau >= 0 else -1.0) / (abs(tau) + math.sqrt(1.0 + tau * tau))
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c

                for i in range(n):
                    if i != p and i != q:
                        a_ip = a[i][p]
                        a_iq = a[i][q]
                        a[i][p] = a[p][i] = c * a_ip - s * a_iq
                        a[i][q] = a[q][i] = s * a_ip + c * a_iq
                a[p][p] = c * c * app - 2.0 * s * c * apq + s * s * aqq
                a[q][q] = s * s * app + 2.0 * s * c * apq + c * c * aqq
                a[p][q] = a[q][p] = 0.0

                for i in range(n):
                    v_ip = V[i][p]
                    v_iq = V[i][q]
                    V[i][p] = c * v_ip - s * v_iq
                    V[i][q] = s * v_ip + c * v_iq

    eigenvals = [a[i][i] for i in range(n)]
    idx = sorted(range(n), key=lambda i: eigenvals[i], reverse=True)
    sorted_evals = [eigenvals[i] for i in idx]
    sorted_V = [[V[r][c] for c in idx] for r in range(n)]
    return sorted_evals, sorted_V


# -----------------------------------------------------------------------------
# SPD Covariance Regularization and Projection
# -----------------------------------------------------------------------------

def project_spd_covariance(
    cov: Sequence[Sequence[float]],
    eigenvalue_floor: float = 1e-6,
) -> Tuple[List[List[float]], SPDRepairReport]:
    """Project symmetric covariance to strictly positive definite (SPD) cone.

    Floors eigenvalues at eigenvalue_floor and reconstructs:
    Sigma_spd = V * diag(max(lambda, floor)) * V^T.
    Returns (Sigma_spd, SPDRepairReport).
    """
    validate_eigenvalue_floor(eigenvalue_floor)
    validate_square_symmetric(cov)
    n = len(cov)
    evals, V = jacobi_eigh(cov)

    raw_min = evals[-1]
    raw_max = evals[0]
    # Condition number is scale-invariant: only non-positive / non-finite minima
    # (or overflowed ratios) are infinite — never an absolute 1e-15 cutoff.
    if raw_min > 0.0 and math.isfinite(raw_min) and math.isfinite(raw_max):
        raw_cond = raw_max / raw_min
        if not math.isfinite(raw_cond):
            raw_cond = float("inf")
    else:
        raw_cond = float("inf")

    n_floored = sum(1 for ev in evals if ev < eigenvalue_floor)
    repaired_evals = [max(ev, eigenvalue_floor) for ev in evals]
    repaired_min = repaired_evals[-1]
    repaired_max = repaired_evals[0]
    if repaired_min > 0.0 and math.isfinite(repaired_min) and math.isfinite(repaired_max):
        repaired_cond = repaired_max / repaired_min
        if not math.isfinite(repaired_cond):
            repaired_cond = float("inf")
    else:
        repaired_cond = float("inf")

    # Reconstruct V * diag(repaired_evals) * V^T
    repaired_cov: List[List[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            val = sum(V[i][k] * repaired_evals[k] * V[j][k] for k in range(n))
            repaired_cov[i][j] = val
            repaired_cov[j][i] = val

    # Compute correction norm
    diff = matrix_subtract(repaired_cov, cov)
    corr_norm = matrix_frobenius_norm(diff)
    cov_norm = matrix_frobenius_norm(cov)
    if cov_norm > 0.0 and math.isfinite(cov_norm):
        rel_norm = corr_norm / cov_norm
        if not math.isfinite(rel_norm):
            rel_norm = float("inf")
    else:
        # Do not force 0.0 for micro-scale covariances — that hid real floors.
        rel_norm = 0.0 if corr_norm == 0.0 else float("inf")

    # Material if eigenvalues were floored and either absolute or relative
    # correction exceeds numerical noise (relative path covers micro-scale SPD).
    is_material = (n_floored > 0) and (corr_norm > 1e-10 or rel_norm > 1e-6)


    report = SPDRepairReport(
        raw_min_eigenvalue=raw_min,
        raw_max_eigenvalue=raw_max,
        raw_condition_number=raw_cond,
        applied_floor=eigenvalue_floor,
        repaired_min_eigenvalue=repaired_min,
        repaired_condition_number=repaired_cond,
        correction_frobenius_norm=corr_norm,
        relative_correction_norm=rel_norm,
        is_correction_material=is_material,
        n_floored_eigenvalues=n_floored,
    )

    return repaired_cov, report
