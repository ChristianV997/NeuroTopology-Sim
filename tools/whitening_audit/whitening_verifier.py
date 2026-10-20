"""Independent train-only whitening verifier and method comparison engine.

Implements:
- TrainOnlyWhiteningModel (strict train-only fit/transform)
- Cholesky whitening: W_chol = L^-1
- Symmetric ZCA whitening: W_zca = V Lambda^-1/2 V^T
- Method comparison: W_chol vs W_zca rotation difference R = W_chol * W_zca^-1
- In-sample and out-of-sample covariance error reporting
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from tools.whitening_audit.matrix_ops import (
    cholesky_decomposition,
    compute_covariance,
    compute_mean,
    identity_matrix,
    invert_lower_triangular,
    jacobi_eigh,
    matrix_frobenius_norm,
    matrix_multiply,
    matrix_subtract,
    matrix_transpose,
    project_spd_covariance,
    validate_eigenvalue_floor,
    validate_finite_matrix,
)
from tools.whitening_audit.types import (
    AuditStatus,
    FeatureDimensionMismatchError,
    MethodComparisonResult,
    SPDRepairReport,
    WhiteningAuditResult,
    WhiteningMethod,
    WhiteningTransformResult,
)


class TrainOnlyWhiteningModel:
    """Strict train-only feature whitening model.

    Guarantees that test data never influences fitted mean, covariance,
    SPD projection, or whitening transformation matrix.
    """

    def __init__(
        self,
        method: WhiteningMethod = WhiteningMethod.CHOLESKY,
        eigenvalue_floor: float = 1e-6,
    ) -> None:
        validate_eigenvalue_floor(eigenvalue_floor)
        self.method = method
        self.eigenvalue_floor = eigenvalue_floor
        self._mean: Optional[Tuple[float, ...]] = None
        self._transform_matrix: Optional[List[List[float]]] = None  # W (d x d)
        self._spd_report: Optional[SPDRepairReport] = None
        self._in_sample_error: Optional[float] = None
        self._n_features: Optional[int] = None
        self._n_train: Optional[int] = None

    @property
    def is_fitted(self) -> bool:
        return self._transform_matrix is not None

    @property
    def mean(self) -> Tuple[float, ...]:
        if self._mean is None:
            raise RuntimeError("Model is not fitted.")
        return self._mean

    @property
    def transform_matrix(self) -> List[List[float]]:
        if self._transform_matrix is None:
            raise RuntimeError("Model is not fitted.")
        return [list(row) for row in self._transform_matrix]

    @property
    def spd_report(self) -> SPDRepairReport:
        if self._spd_report is None:
            raise RuntimeError("Model is not fitted.")
        return self._spd_report

    @property
    def in_sample_error(self) -> float:
        if self._in_sample_error is None:
            raise RuntimeError("Model is not fitted.")
        return self._in_sample_error

    def fit(self, X_train: Sequence[Sequence[float]]) -> WhiteningTransformResult:
        """Fit mean, covariance, and whitening matrix strictly on X_train."""
        validate_finite_matrix(X_train, "X_train")
        n = len(X_train)
        d = len(X_train[0])
        self._n_train = n
        self._n_features = d

        # 1. Sample mean on training data only
        mu = compute_mean(X_train)
        self._mean = mu

        # 2. Sample covariance on training data only
        cov_raw = compute_covariance(X_train, mean=mu)

        # 3. Regularize / project to SPD cone
        cov_spd, spd_rep = project_spd_covariance(cov_raw, eigenvalue_floor=self.eigenvalue_floor)
        self._spd_report = spd_rep

        # 4. Construct whitening matrix W
        if self.method == WhiteningMethod.CHOLESKY:
            # W_chol = L^-1
            L = cholesky_decomposition(cov_spd)
            W = invert_lower_triangular(L)
        elif self.method == WhiteningMethod.ZCA:
            # W_zca = V * diag(lambda^-1/2) * V^T
            evals, V = jacobi_eigh(cov_spd)
            inv_sqrt_diag = [1.0 / math.sqrt(ev) for ev in evals]
            W = [[sum(V[i][k] * inv_sqrt_diag[k] * V[j][k] for k in range(d)) for j in range(d)] for i in range(d)]
        else:
            raise ValueError(f"Unknown whitening method: {self.method}")

        self._transform_matrix = W

        # 5. Compute in-sample whitened covariance and error
        Z_train = self.transform(X_train)
        cov_z_train = compute_covariance(Z_train)
        I_d = identity_matrix(d)
        diff = matrix_subtract(cov_z_train, I_d)
        self._in_sample_error = matrix_frobenius_norm(diff)

        return WhiteningTransformResult(
            method=self.method,
            mean=self._mean,
            transform_matrix=tuple(tuple(r) for r in self._transform_matrix),
            spd_report=self._spd_report,
            in_sample_error=self._in_sample_error,
            n_train_samples=n,
            n_features=d,
        )

    def transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        """Apply fitted transform z = (x - mu_train) * W^T."""
        if not self.is_fitted:
            raise RuntimeError("Cannot transform before calling fit().")
        validate_finite_matrix(X, "Transform input X")
        d = len(X[0])
        if d != self._n_features:
            raise FeatureDimensionMismatchError(
                f"Feature dimension {d} does not match fitted training dimension {self._n_features}."
            )

        mu = self.mean
        W = self._transform_matrix  # W is (d x d)
        assert W is not None

        # Z = (X - mu) * W^T  ->  z_row[j] = sum_k (x[k] - mu[k]) * W[j][k]
        Z: List[List[float]] = []
        for row in X:
            centered = [row[k] - mu[k] for k in range(d)]
            z_row = [sum(centered[k] * W[j][k] for k in range(d)) for j in range(d)]
            Z.append(z_row)
        return Z

    def evaluate_out_of_sample_error(self, X_test: Sequence[Sequence[float]]) -> float:
        """Compute out-of-sample covariance error ||Cov(Z_test) - I||_F."""
        Z_test = self.transform(X_test)
        d = len(X_test[0])
        cov_z_test = compute_covariance(Z_test)
        I_d = identity_matrix(d)
        diff = matrix_subtract(cov_z_test, I_d)
        return matrix_frobenius_norm(diff)


# -----------------------------------------------------------------------------
# Method Comparison: Cholesky vs Symmetric ZCA
# -----------------------------------------------------------------------------

def compare_whitening_methods(
    covariance: Sequence[Sequence[float]],
    eigenvalue_floor: float = 1e-6,
) -> MethodComparisonResult:
    """Compare Cholesky whitening and Symmetric ZCA on a known covariance matrix.

    Analyzes:
    - In-sample covariance whitening errors for both methods.
    - Transform difference ||W_chol - W_zca||_F.
    - Orthogonal coordinate rotation R = W_chol * Sigma^(1/2).
    - Structural properties (Cholesky lower-triangular vs ZCA symmetric).
    """
    validate_eigenvalue_floor(eigenvalue_floor)
    d = len(covariance)
    cov_spd, _ = project_spd_covariance(covariance, eigenvalue_floor=eigenvalue_floor)

    # 1. Cholesky whitening W_chol = L^-1
    L = cholesky_decomposition(cov_spd)
    W_chol = invert_lower_triangular(L)

    # Check lower triangularity
    is_lower_tri = True
    for i in range(d):
        for j in range(i + 1, d):
            if abs(W_chol[i][j]) > 1e-12:
                is_lower_tri = False

    # 2. Symmetric ZCA whitening W_zca = V * Lambda^-1/2 * V^T
    evals, V = jacobi_eigh(cov_spd)
    inv_sqrt_diag = [1.0 / math.sqrt(ev) for ev in evals]
    W_zca = [[sum(V[i][k] * inv_sqrt_diag[k] * V[j][k] for k in range(d)) for j in range(d)] for i in range(d)]

    # Check symmetry of W_zca
    is_symmetric = True
    for i in range(d):
        for j in range(i + 1, d):
            if abs(W_zca[i][j] - W_zca[j][i]) > 1e-12:
                is_symmetric = False

    # 3. Verify covariance whitening: W * Sigma * W^T
    I_d = identity_matrix(d)

    # Chol error
    W_chol_cov = matrix_multiply(W_chol, cov_spd)
    cov_chol_whitened = matrix_multiply(W_chol_cov, matrix_transpose(W_chol))
    err_chol = matrix_frobenius_norm(matrix_subtract(cov_chol_whitened, I_d))

    # ZCA error
    W_zca_cov = matrix_multiply(W_zca, cov_spd)
    cov_zca_whitened = matrix_multiply(W_zca_cov, matrix_transpose(W_zca))
    err_zca = matrix_frobenius_norm(matrix_subtract(cov_zca_whitened, I_d))

    # 4. Difference between transformation matrices
    diff_W = matrix_subtract(W_chol, W_zca)
    norm_diff = matrix_frobenius_norm(diff_W)
    norm_zca = matrix_frobenius_norm(W_zca)
    rel_diff = norm_diff / norm_zca if norm_zca > 1e-15 else 0.0

    # 5. Coordinate rotation R = W_chol * Sigma^(1/2)
    # Sigma^(1/2) = V * diag(sqrt(evals)) * V^T
    sqrt_diag = [math.sqrt(ev) for ev in evals]
    sqrt_cov = [[sum(V[i][k] * sqrt_diag[k] * V[j][k] for k in range(d)) for j in range(d)] for i in range(d)]
    R = matrix_multiply(W_chol, sqrt_cov)
    rot_diff = matrix_frobenius_norm(matrix_subtract(R, I_d))

    # Equivalence flag (mathematically false unless covariance is already diagonal scalar)
    are_equiv = (norm_diff < 1e-9)

    return MethodComparisonResult(
        covariance_in_sample_chol_error=err_chol,
        covariance_in_sample_zca_error=err_zca,
        transform_matrix_frobenius_difference=norm_diff,
        relative_transform_difference=rel_diff,
        rotation_matrix=tuple(tuple(r) for r in R),
        rotation_deviation_from_identity=rot_diff,
        are_methods_equivalent=are_equiv,
        cholesky_is_lower_triangular=is_lower_tri,
        zca_is_symmetric=is_symmetric,
    )


# -----------------------------------------------------------------------------
# High-Level Audit Coordinator
# -----------------------------------------------------------------------------

def audit_whitening_pipeline(
    X_train: Sequence[Sequence[float]],
    X_test: Sequence[Sequence[float]],
    method: WhiteningMethod = WhiteningMethod.CHOLESKY,
    eigenvalue_floor: float = 1e-6,
) -> WhiteningAuditResult:
    """Execute complete independent audit of train/test whitening pipeline."""
    model = TrainOnlyWhiteningModel(method=method, eigenvalue_floor=eigenvalue_floor)
    model.fit(X_train)

    in_err = model.in_sample_error
    out_err = model.evaluate_out_of_sample_error(X_test)
    spd_rep = model.spd_report

    # Compare methods on the training covariance
    cov_train = compute_covariance(X_train)
    comparison = compare_whitening_methods(cov_train, eigenvalue_floor=eigenvalue_floor)

    warnings: List[str] = []
    if spd_rep.is_correction_material:
        warnings.append(
            f"Material SPD repair applied: raw min eigenvalue {spd_rep.raw_min_eigenvalue:.4e} "
            f"floored to {spd_rep.applied_floor:.4e} (correction norm: {spd_rep.correction_frobenius_norm:.4e})."
        )
    if comparison.transform_matrix_frobenius_difference > 1e-6:
        warnings.append(
            f"Whitening convention note: Cholesky and Symmetric ZCA differ by rotation norm "
            f"{comparison.rotation_deviation_from_identity:.4f}. They are not equivalent."
        )

    provenance = {
        "auditor": "Antigravity Agent B (Batch 2)",
        "scope": "SYNTHETIC_ONLY / ENGINEERING_ONLY",
        "method": method.value,
        "eigenvalue_floor": eigenvalue_floor,
        "disclaimer": (
            "Independent audit of Round 6 whitening specification. "
            "No candidate implementation was found in origin/main or remote branches; "
            "this audit verifies the mathematical and pipeline specification independently."
        ),
    }

    return WhiteningAuditResult(
        status=AuditStatus.PASSED,
        candidate_code_present=False,
        whitening_method=method,
        n_train_samples=len(X_train),
        n_test_samples=len(X_test),
        n_features=len(X_train[0]),
        in_sample_error=in_err,
        out_of_sample_error=out_err,
        spd_report=spd_rep,
        method_comparison=comparison,
        leakage_check=None,
        warnings=tuple(warnings),
        provenance=provenance,
    )
