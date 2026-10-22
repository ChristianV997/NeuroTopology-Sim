"""Machine-readable audit reports (finite JSON, SYNTHETIC_ONLY)."""
from __future__ import annotations

import json
import math
from typing import Any, Dict, Optional

import numpy as np

from .errors import SurrogateAuditError
from .metrics import (
    SPECTRAL_GATE_1E3,
    marginal_sorted_error,
    relative_autospectral_error,
    relative_cross_spectral_error,
    validate_array,
)
from .mv_fpr import generate_mv_fpr
from .mv_iaaft import generate_mv_iaaft
from .status import AuditStatus, EvidenceClass


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    return value


def dumps_report(report: Dict[str, Any], *, indent: int = 2) -> str:
    return json.dumps(_json_safe(report), indent=indent, sort_keys=True, allow_nan=False)


def audit_surrogate(
    x: np.ndarray,
    *,
    method: str,
    seed: int = 0,
    max_iter: int = 50,
    spectral_gate: float = SPECTRAL_GATE_1E3,
    fpr_spectral_atol: float = 1e-10,
) -> Dict[str, Any]:
    """Run one synthetic surrogate audit for ``mv_fpr`` or ``mv_iaaft``.

    Never sets scientific VALIDATED. Status fields are engineering audit only.
    """
    method_key = str(method).strip().lower()
    if not isinstance(fpr_spectral_atol, (int, float)) or not math.isfinite(fpr_spectral_atol) or fpr_spectral_atol <= 0:
        raise SurrogateAuditError("fpr_spectral_atol must be a finite positive number")
    if not isinstance(spectral_gate, (int, float)) or not math.isfinite(spectral_gate) or spectral_gate <= 0:
        raise SurrogateAuditError("spectral_gate must be a finite positive number")
    if not isinstance(max_iter, int) or max_iter < 1:
        raise SurrogateAuditError("max_iter must be an integer >= 1")

    try:
        arr = validate_array(x, min_channels=1, min_time=2)
    except SurrogateAuditError as exc:
        return {
            "evidence_class": EvidenceClass.SYNTHETIC_ONLY.value,
            "scientific_validated": False,
            "method": method_key,
            "status": AuditStatus.INVALID_INPUT.value,
            "error": str(exc),
            "hold": True,
        }

    if method_key == "mv_fpr":
        surr, meta = generate_mv_fpr(arr, seed=seed)
        cs_err = relative_cross_spectral_error(arr, surr)
        as_err = relative_autospectral_error(arr, surr)
        marg_err = marginal_sorted_error(arr, surr)
        # Algebraic preservation: cross-spectrum must meet a tight numerical tol.
        spectral_status = (
            AuditStatus.MET.value if cs_err <= fpr_spectral_atol else AuditStatus.UNMET.value
        )
        # Quantile restoration is NOT part of this null.
        quantile_status = AuditStatus.NOT_APPLICABLE.value
        report = {
            "evidence_class": EvidenceClass.SYNTHETIC_ONLY.value,
            "scientific_validated": False,
            "hold": True,
            "method": "mv_fpr",
            "status": spectral_status,
            "cross_spectral_error": float(cs_err),
            "autospectral_error": float(as_err),
            "marginal_sorted_error": float(marg_err),
            "spectral_gate": float(fpr_spectral_atol),
            "spectral_gate_status": spectral_status,
            "quantile_gate_status": quantile_status,
            "null_assumption": meta["null_assumption"],
            "randomized_bins": meta["randomized_bins"],
            "fixed_real_bins": meta["fixed_real_bins"],
            "meta": meta,
            "definitions": {
                "cross_spectral_error": (
                    "||C_surr - C_orig||_F / ||C_orig||_F over the full "
                    "complex (n_freq, n_ch, n_ch) cross-spectral tensor"
                ),
                "marginal_sorted_error": (
                    "max_c max_t |sort(surr[c]) - sort(orig[c])|; not restored by MV-FPR"
                ),
            },
            "limitations": [
                "MV-FPR does not restore amplitude quantiles.",
                "MV-FPR is not interchangeable with MV-IAAFT.",
                "Independent audit API: expected values come from audit metrics/generators, not production nulls helpers.",
                "Production nulls on main are exercised only via the separate hard-import bridge tests.",
                "SYNTHETIC_ONLY — not scientific VALIDATED.",
            ],
        }
        return _json_safe(report)

    if method_key == "mv_iaaft":
        surr, meta = generate_mv_iaaft(
            arr, seed=seed, max_iter=max_iter, spectral_gate=spectral_gate
        )
        # Exact marginal restoration expected after rank adjustment.
        quantile_status = (
            AuditStatus.MET.value
            if meta["marginal_sorted_error"] <= 1e-12
            else AuditStatus.UNMET.value
        )
        report = {
            "evidence_class": EvidenceClass.SYNTHETIC_ONLY.value,
            "scientific_validated": False,
            "hold": True,
            "method": "mv_iaaft",
            "status": meta["spectral_gate_status"],
            "pre_rank_cross_spectral_error": meta["pre_rank_cross_spectral_error"],
            "post_rank_cross_spectral_error": meta["post_rank_cross_spectral_error"],
            "marginal_sorted_error": meta["marginal_sorted_error"],
            "spectral_gate": float(spectral_gate),
            "spectral_gate_status": meta["spectral_gate_status"],
            "quantile_gate_status": quantile_status,
            "returned_signal": "post_rank",
            "null_assumption": meta["null_assumption"],
            "strict_1e3_post_rank_gate_guaranteed": False,
            "meta": meta,
            "definitions": {
                "pre_rank_cross_spectral_error": (
                    "full complex cross-spectral relative Frobenius error after the "
                    "spectrum-imposition step, before rank/quantile restoration"
                ),
                "post_rank_cross_spectral_error": (
                    "same error after per-channel sorted-value restoration; this is "
                    "the quantity compared to the strict 1e-3 gate"
                ),
                "marginal_sorted_error": (
                    "max_c max_t |sort(surr[c]) - sort(orig[c])|; exact after rank step"
                ),
            },
            "limitations": [
                "The strict 1e-3 post-rank spectral gate is NOT guaranteed by IAAFT.",
                "UNMET is reported honestly; the returned signal remains post-rank.",
                "Auto-spectra alone are insufficient; full cross-spectral error is required.",
                "MV-IAAFT is not interchangeable with MV-FPR.",
                "Independent audit API: expected values come from audit metrics/generators, not production nulls helpers.",
                "Production nulls on main are exercised only via the separate hard-import bridge tests.",
                "SYNTHETIC_ONLY — not scientific VALIDATED.",
            ],
        }
        return _json_safe(report)

    raise SurrogateAuditError(f"unknown method {method!r}; use 'mv_fpr' or 'mv_iaaft'")
