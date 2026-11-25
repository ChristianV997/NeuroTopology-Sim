"""Schema / claim labels for the Round-6 Hodge decomposition numerical audit."""
from __future__ import annotations

from enum import Enum
from typing import Tuple

SCHEMA_VERSION = "NeuroTopology.HodgeDecompositionAudit.v1"
EVIDENCE_CLASS = "SYNTHETIC_ONLY"
AUDIT_STATUS = "HOLD"
CLAIM_SCOPE = (
    "Independent synthetic numerical audit of 2D cochain/Hodge identities. "
    "Not a scientific VALIDATED claim. Not a mesh/Delaunay geometry audit."
)

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/hodge_decomposition_audit/",
    "tests/tools/hodge_decomposition_audit/",
    "docs/tools/hodge_decomposition_audit.md",
)

# Adjacent ownership (do not edit):
# experimental/phase_cochain_reference/** — open PR #385 (proposal reference)
# mesh generation / winding-charge metric lanes — out of scope

# Algebraic identities (exact over R/Z for incidence construction).
ALGEBRAIC_IDENTITIES: Tuple[str, ...] = (
    "d1 @ d0 == 0 (coboundary exactness)",
    "dimension equations: d0.shape == (|E|, |V|), d1.shape == (|T|, |E|)",
    "raw integer face charges from d1 @ omega_phase are independent of Hodge edge weights W1",
    "exact/coexact weighted orthogonality follows from d1 @ d0 == 0 when normal equations are solved exactly",
)

# Numerical tolerances that depend on conditioning / scale.
NUMERICAL_TOLERANCE_DEPENDENCIES: Tuple[str, ...] = (
    "weighted orthogonality residuals after floating-point lstsq",
    "energy closure |E - sum E_k| / E",
    "reconstruction residual ||omega - (exact+coexact+harmonic)||_W1",
    "harmonic-component magnitude thresholds on near-singular W1",
    "condition-number diagnostics for L0 = d0.T W1 d0 and M = d1 W1^{-1} d1.T",
)

COND_REJECT_THRESHOLD = 1e12
DEFAULT_ATOL = 1e-10
DEFAULT_RTOL = 1e-9


class BoundaryClass(str, Enum):
    DISK_WITH_BOUNDARY = "disk_with_boundary"
    CLOSED_CYCLE_COMPLEX = "closed_cycle_complex"
    ANNULUS_LIKE = "annulus_like"


class AuditVerdict(str, Enum):
    PASS_SYNTHETIC = "PASS_SYNTHETIC"
    FAIL = "FAIL"
    REJECTED_ILL_CONDITIONED = "REJECTED_ILL_CONDITIONED"
    HOLD = "HOLD"
