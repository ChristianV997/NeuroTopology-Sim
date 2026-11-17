"""Data types, enums, and exceptions for Round 6 train/test whitening audit.

Defines:
- WhiteningMethod enum (CHOLESKY vs ZCA)
- AuditStatus enum
- Custom fail-closed exceptions
- SPDRepairReport dataclass
- WhiteningAuditResult dataclass
- LeakageCheckResult dataclass
- MethodComparisonResult dataclass
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple


# -----------------------------------------------------------------------------
# Fail-Closed Exceptions
# -----------------------------------------------------------------------------

class WhiteningAuditError(ValueError):
    """Base exception for whitening audit contract failures."""


class InsufficientSamplesError(WhiteningAuditError):
    """Raised when sample count n <= 1 is insufficient to compute sample covariance."""


class EmptyDataError(WhiteningAuditError):
    """Raised when input feature matrix is empty."""


class NonFiniteValuesError(WhiteningAuditError):
    """Raised when input data contains NaN, +Inf, or -Inf."""


class FeatureDimensionMismatchError(WhiteningAuditError):
    """Raised when test feature dimension d_test != d_train."""


class NonPositiveDefiniteError(WhiteningAuditError):
    """Raised when an unregularized covariance matrix fails positive definiteness."""


class InvalidCovarianceError(WhiteningAuditError):
    """Raised when covariance matrix is malformed, non-square, or asymmetric."""


class ModelNotFittedError(WhiteningAuditError, RuntimeError):
    """Raised when transform or properties are accessed on an unfitted model."""


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class WhiteningMethod(str, Enum):
    """Whitening transformation method."""
    CHOLESKY = "cholesky"  # Lower-triangular L^-1 (x - mu), coordinate-dependent rotation
    ZCA = "zca"            # Symmetric Sigma^-1/2 (x - mu), zero-phase minimal rotation


class AuditStatus(str, Enum):
    """Audit evaluation outcomes."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    LEAKAGE_DETECTED = "LEAKAGE_DETECTED"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    HOLD = "HOLD"


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SPDRepairReport:
    """Detailed disclosure of covariance regularization / SPD projection."""
    raw_min_eigenvalue: float
    raw_max_eigenvalue: float
    raw_condition_number: float
    applied_floor: float
    repaired_min_eigenvalue: float
    repaired_condition_number: float
    correction_frobenius_norm: float
    relative_correction_norm: float
    is_correction_material: bool
    n_floored_eigenvalues: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WhiteningTransformResult:
    """Fitted whitening model parameters."""
    method: WhiteningMethod
    mean: Tuple[float, ...]
    transform_matrix: Tuple[Tuple[float, ...], ...]  # W of shape (d, d)
    spd_report: SPDRepairReport
    in_sample_error: float                           # ||Cov(Z_train) - I||_F
    n_train_samples: int
    n_features: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method.value,
            "mean": list(self.mean),
            "transform_matrix": [list(row) for row in self.transform_matrix],
            "spd_report": self.spd_report.to_dict(),
            "in_sample_error": self.in_sample_error,
            "n_train_samples": self.n_train_samples,
            "n_features": self.n_features,
        }


@dataclass(frozen=True)
class MethodComparisonResult:
    """Comparison between Cholesky whitening and Symmetric ZCA whitening."""
    covariance_in_sample_chol_error: float          # ||Cov(Z_chol) - I||_F
    covariance_in_sample_zca_error: float           # ||Cov(Z_zca) - I||_F
    transform_matrix_frobenius_difference: float    # ||W_chol - W_zca||_F
    relative_transform_difference: float            # ||W_chol - W_zca||_F / ||W_zca||_F
    rotation_matrix: Tuple[Tuple[float, ...], ...]  # R = W_chol * W_zca^-1
    rotation_deviation_from_identity: float         # ||R - I||_F
    are_methods_equivalent: bool                    # True only if rel gap < 1e-9 and no SPD flooring
    cholesky_is_lower_triangular: bool
    zca_is_symmetric: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "covariance_in_sample_chol_error": self.covariance_in_sample_chol_error,
            "covariance_in_sample_zca_error": self.covariance_in_sample_zca_error,
            "transform_matrix_frobenius_difference": self.transform_matrix_frobenius_difference,
            "relative_transform_difference": self.relative_transform_difference,
            "rotation_matrix": [list(row) for row in self.rotation_matrix],
            "rotation_deviation_from_identity": self.rotation_deviation_from_identity,
            "are_methods_equivalent": self.are_methods_equivalent,
            "cholesky_is_lower_triangular": self.cholesky_is_lower_triangular,
            "zca_is_symmetric": self.zca_is_symmetric,
        }


@dataclass(frozen=True)
class LeakageCheckResult:
    """Outcome of train-only vs leaky pipeline comparison."""
    leakage_detected: bool
    mean_difference_norm: float
    covariance_difference_norm: float
    transform_difference_norm: float
    out_of_sample_error_strict: float
    out_of_sample_error_leaky: float
    error_discrepancy: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WhiteningAuditResult:
    """Comprehensive artifact summarizing Round 6 whitening audit."""
    status: AuditStatus
    candidate_code_present: bool
    whitening_method: WhiteningMethod
    n_train_samples: int
    n_test_samples: int
    n_features: int
    in_sample_error: float
    out_of_sample_error: float
    spd_report: SPDRepairReport
    method_comparison: Optional[MethodComparisonResult] = None
    leakage_check: Optional[LeakageCheckResult] = None
    warnings: Tuple[str, ...] = ()
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "candidate_code_present": self.candidate_code_present,
            "whitening_method": self.whitening_method.value,
            "n_train_samples": self.n_train_samples,
            "n_test_samples": self.n_test_samples,
            "n_features": self.n_features,
            "in_sample_error": self.in_sample_error,
            "out_of_sample_error": self.out_of_sample_error,
            "spd_report": self.spd_report.to_dict(),
            "method_comparison": self.method_comparison.to_dict() if self.method_comparison else None,
            "leakage_check": self.leakage_check.to_dict() if self.leakage_check else None,
            "warnings": list(self.warnings),
            "provenance": self.provenance,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)
