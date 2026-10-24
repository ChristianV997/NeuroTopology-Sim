"""Leakage regression fixtures and detection tests for train/test whitening.

Verifies that held-out test data never influences:
1. Fitted training mean
2. Fitted training covariance
3. SPD projection / eigenvalue flooring
4. Whitening transform matrix W

Demonstrates that leaking test data into the fitting step visibly shifts parameters
and distorts out-of-sample covariance evaluations.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

from tools.whitening_audit.matrix_ops import (
    compute_covariance,
    compute_mean,
    matrix_frobenius_norm,
    matrix_subtract,
    project_spd_covariance,
    validate_finite_matrix,
)
from tools.whitening_audit.types import (
    LeakageCheckResult,
    WhiteningMethod,
)
from tools.whitening_audit.whitening_verifier import TrainOnlyWhiteningModel


def run_leakage_regression_fixture(
    X_train: Sequence[Sequence[float]],
    X_test: Sequence[Sequence[float]],
    method: WhiteningMethod = WhiteningMethod.CHOLESKY,
    eigenvalue_floor: float = 1e-6,
) -> LeakageCheckResult:
    """Execute a controlled leakage regression fixture.

    Compares:
    A) Strict Train-Only Fitting: fit strictly on X_train, then evaluate on X_test.
    B) Leaky Pooled Fitting: fit on [X_train; X_test], then evaluate on X_test.

    When X_test has distribution shift (mean shift, variance scaling, or rotation),
    the leaky model's parameters diverge visibly from the strict train-only model.
    """
    validate_finite_matrix(X_train, "X_train")
    validate_finite_matrix(X_test, "X_test")

    # 1. Strict Train-Only Pipeline
    strict_model = TrainOnlyWhiteningModel(method=method, eigenvalue_floor=eigenvalue_floor)
    strict_model.fit(X_train)
    strict_mu = strict_model.mean
    strict_W = strict_model.transform_matrix
    strict_out_err = strict_model.evaluate_out_of_sample_error(X_test)

    # Training covariance
    strict_cov = compute_covariance(X_train)

    # 2. Leaky Pooled Pipeline (Contaminated)
    X_pooled = list(X_train) + list(X_test)
    leaky_model = TrainOnlyWhiteningModel(method=method, eigenvalue_floor=eigenvalue_floor)
    leaky_model.fit(X_pooled)
    leaky_mu = leaky_model.mean
    leaky_W = leaky_model.transform_matrix
    leaky_out_err = leaky_model.evaluate_out_of_sample_error(X_test)

    # Leaky pooled covariance
    leaky_cov = compute_covariance(X_pooled)

    # 3. Compute parameter divergence
    d = len(X_train[0])

    # Mean difference norm
    mean_diff = math.sqrt(sum((strict_mu[i] - leaky_mu[i]) ** 2 for i in range(d)))

    # Covariance difference norm
    cov_diff_mat = matrix_subtract(strict_cov, leaky_cov)
    cov_diff_norm = matrix_frobenius_norm(cov_diff_mat)

    # Whitening matrix difference norm
    W_diff_mat = matrix_subtract(strict_W, leaky_W)
    W_diff_norm = matrix_frobenius_norm(W_diff_mat)

    # Discrepancy in out-of-sample whitening error
    err_discrepancy = abs(strict_out_err - leaky_out_err)

    # Leakage is detected if training parameters or errors differ materially
    leakage_detected = (mean_diff > 1e-6) or (cov_diff_norm > 1e-6) or (W_diff_norm > 1e-6)

    desc = (
        f"Leakage comparison: ||mu_strict - mu_leaky|| = {mean_diff:.4e}, "
        f"||Cov_strict - Cov_leaky||_F = {cov_diff_norm:.4e}, "
        f"||W_strict - W_leaky||_F = {W_diff_norm:.4e}, "
        f"Out-of-sample error difference: {err_discrepancy:.4e}."
    )

    return LeakageCheckResult(
        leakage_detected=leakage_detected,
        mean_difference_norm=mean_diff,
        covariance_difference_norm=cov_diff_norm,
        transform_difference_norm=W_diff_norm,
        out_of_sample_error_strict=strict_out_err,
        out_of_sample_error_leaky=leaky_out_err,
        error_discrepancy=err_discrepancy,
        description=desc,
    )
