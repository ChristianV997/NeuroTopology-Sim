"""Invalid / nonfinite inputs fail closed (engineering errors, not VALIDATED)."""
from __future__ import annotations

import numpy as np
import pytest

from tools.surrogate_audit.errors import SurrogateAuditError
from tools.surrogate_audit.mv_fpr import generate_mv_fpr
from tools.surrogate_audit.mv_iaaft import generate_mv_iaaft
from tools.surrogate_audit.report import audit_surrogate


def test_nonfinite_rejected():
    x = np.ones((2, 32))
    x[0, 3] = np.nan
    with pytest.raises(SurrogateAuditError, match="non-finite"):
        generate_mv_fpr(x, seed=0)
    with pytest.raises(SurrogateAuditError, match="non-finite"):
        generate_mv_iaaft(x, seed=0)


def test_wrong_rank_rejected():
    with pytest.raises(SurrogateAuditError):
        generate_mv_fpr(np.zeros(32), seed=0)


def test_too_short_rejected():
    with pytest.raises(SurrogateAuditError):
        generate_mv_iaaft(np.zeros((2, 1)), seed=0)


def test_audit_invalid_input_status():
    report = audit_surrogate(np.array([1.0, np.inf]), method="mv_fpr", seed=0)
    assert report["status"] == "INVALID_INPUT"
    assert report["scientific_validated"] is False
    assert report["evidence_class"] == "SYNTHETIC_ONLY"


def test_unknown_method_raises():
    with pytest.raises(SurrogateAuditError, match="unknown method"):
        audit_surrogate(np.zeros((2, 32)), method="phase_magic", seed=0)
