"""Round 6 train/test whitening audit package.

Exposes:
- TrainOnlyWhiteningModel: Strict train-only whitening fitting and transformation.
- compare_whitening_methods: Discloses rotation and structural differences between
  Cholesky and Symmetric ZCA whitening.
- audit_whitening_pipeline: Complete independent audit coordinator.
- run_leakage_regression_fixture: Demonstrates parameter divergence under test leakage.
- Types, reports, and fail-closed exceptions.
"""

from __future__ import annotations

from tools.whitening_audit.leakage_detector import (
    run_leakage_regression_fixture,
)
from tools.whitening_audit.matrix_ops import (
    cholesky_decomposition,
    compute_covariance,
    compute_mean,
    invert_lower_triangular,
    jacobi_eigh,
    project_spd_covariance,
)
from tools.whitening_audit.types import (
    AuditStatus,
    EmptyDataError,
    FeatureDimensionMismatchError,
    InsufficientSamplesError,
    InvalidCovarianceError,
    LeakageCheckResult,
    MethodComparisonResult,
    NonFiniteValuesError,
    NonPositiveDefiniteError,
    SPDRepairReport,
    WhiteningAuditError,
    WhiteningAuditResult,
    WhiteningMethod,
    WhiteningTransformResult,
)
from tools.whitening_audit.whitening_verifier import (
    TrainOnlyWhiteningModel,
    audit_whitening_pipeline,
    compare_whitening_methods,
)

__all__ = [
    "AuditStatus",
    "EmptyDataError",
    "FeatureDimensionMismatchError",
    "InsufficientSamplesError",
    "InvalidCovarianceError",
    "LeakageCheckResult",
    "MethodComparisonResult",
    "NonFiniteValuesError",
    "NonPositiveDefiniteError",
    "SPDRepairReport",
    "TrainOnlyWhiteningModel",
    "WhiteningAuditError",
    "WhiteningAuditResult",
    "WhiteningMethod",
    "WhiteningTransformResult",
    "audit_whitening_pipeline",
    "cholesky_decomposition",
    "compare_whitening_methods",
    "compute_covariance",
    "compute_mean",
    "invert_lower_triangular",
    "jacobi_eigh",
    "project_spd_covariance",
    "run_leakage_regression_fixture",
]
