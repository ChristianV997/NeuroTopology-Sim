"""Independent Round 6 winding / charge-moment conformance oracle.

HOLD / SYNTHETIC_ONLY. This package is a specification oracle for discrete
algebraic identities. It does not import or execute Gemini's
``experimental/phase_cochain_reference`` candidate engine (PR #385), and a
passing discrete check is not a scientific VALIDATED/PASS claim.
"""

from __future__ import annotations

from tools.experimental_audits.winding_charge_round6.audit import (
    AuditReport,
    run_conformance_audit,
)
from tools.experimental_audits.winding_charge_round6.oracle import (
    BRANCH_AT_PLUS_PI,
    WRAP_INTERVAL,
    ChargeMomentResult,
    IndependentComplex,
    apply_confidence_weights,
    charge_moments,
    net_charge,
    topological_charges_from_phases,
    triangle_loop_winding,
    wrap_principal,
)

__all__ = [
    "BRANCH_AT_PLUS_PI",
    "WRAP_INTERVAL",
    "AuditReport",
    "ChargeMomentResult",
    "IndependentComplex",
    "apply_confidence_weights",
    "charge_moments",
    "net_charge",
    "run_conformance_audit",
    "topological_charges_from_phases",
    "triangle_loop_winding",
    "wrap_principal",
]

PROJECT_STATUS = "HOLD"
DATA_POLICY = "SYNTHETIC_ONLY"
CLAIM_SCOPE = "discrete_identity_only"
