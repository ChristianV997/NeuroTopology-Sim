"""Independent weighted Hodge–Helmholtz oracle (numpy only).

Decomposes omega = exact + coexact + harmonic under <u,v>_W1 = sum_e w_e u_e v_e.

Ill-conditioned / non-positive weights are rejected with diagnostics rather than
silently inverted. This oracle does not import proposal code and does not claim
that any external proposal passed.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Sequence

import numpy as np

from tools.hodge_decomposition_audit.incidence import OrientedComplex
from tools.hodge_decomposition_audit.schema import (
    AUDIT_STATUS,
    COND_REJECT_THRESHOLD,
    DEFAULT_ATOL,
    EVIDENCE_CLASS,
    AuditVerdict,
)


@dataclass(frozen=True)
class HodgeOracleResult:
    accepted: bool
    verdict: str
    exact: np.ndarray
    coexact: np.ndarray
    harmonic: np.ndarray
    potential: np.ndarray
    stream_gamma: np.ndarray
    energy_total: float
    energy_exact: float
    energy_coexact: float
    energy_harmonic: float
    ortho_exact_coexact: float
    ortho_exact_harmonic: float
    ortho_coexact_harmonic: float
    reconstruction_residual_w1: float
    relative_reconstruction_error: float
    relative_energy_error: float
    cond_L0: float
    cond_M: Optional[float]
    diagnostics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key in ("exact", "coexact", "harmonic", "potential", "stream_gamma"):
            payload[key] = [float(x) for x in np.asarray(payload[key], dtype=float).ravel()]
        payload["evidence_class"] = EVIDENCE_CLASS
        payload["audit_status"] = AUDIT_STATUS
        return payload


class IllConditionedError(ValueError):
    """Raised when normal matrices / weights are rejected."""


def _positive_weights(values: Optional[Sequence[float]], n: int, name: str) -> np.ndarray:
    if values is None:
        return np.ones(n, dtype=float)
    raw = np.asarray(values)
    if np.iscomplexobj(raw):
        raise IllConditionedError(f"{name}_complex")
    try:
        arr = raw.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} cannot be converted to float: {exc}") from exc
    if arr.shape != (n,):
        raise ValueError(f"{name} shape {arr.shape} != ({n},)")
    if not np.all(np.isfinite(arr)):
        raise IllConditionedError(f"{name}_nonfinite")
    if np.any(arr <= 0.0):
        raise IllConditionedError(f"{name}_nonpositive")
    return arr


def _effective_cond(mat: np.ndarray, *, relative_floor: float = 1e-14) -> tuple[float, int]:
    """Condition number over singular values above a relative floor.

    Graph Laplacians L0 = d0.T W1 d0 are singular by gauge invariance (kernel
    contains constants on a connected complex). Absolute singularity is therefore
    expected and is not by itself a rejection reason; we report the condition of
    the positive part of the spectrum.
    """
    if mat.size == 0:
        return 0.0, 0
    singular = np.linalg.svd(mat, compute_uv=False)
    if singular.size == 0:
        return 0.0, 0
    smax = float(np.max(singular))
    if smax == 0.0:
        return float("inf"), 0
    floor = smax * relative_floor
    positive = singular[singular > floor]
    if positive.size == 0:
        return float("inf"), 0
    return float(smax / float(np.min(positive))), int(positive.size)


def weighted_inner(w_e: np.ndarray, u: np.ndarray, v: np.ndarray) -> float:
    return float(np.sum(w_e * u * v))


def weighted_norm_sq(w_e: np.ndarray, u: np.ndarray) -> float:
    return float(np.sum(w_e * u * u))


def decompose(
    complex_: OrientedComplex,
    omega: Sequence[float],
    *,
    weights_edges: Optional[Sequence[float]] = None,
    weights_faces: Optional[Sequence[float]] = None,
    cond_reject: float = COND_REJECT_THRESHOLD,
    atol: float = DEFAULT_ATOL,
) -> HodgeOracleResult:
    """Weighted Hodge decomposition with explicit conditioning rejection."""
    raw_omega = np.asarray(omega)
    if np.iscomplexobj(raw_omega):
        raise ValueError("omega complex values not supported")
    try:
        omega_arr = raw_omega.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"omega cannot be converted to float: {exc}") from exc
    if omega_arr.shape != (complex_.num_edges,):
        raise ValueError("omega shape mismatch")
    if not np.all(np.isfinite(omega_arr)):
        raise ValueError("omega nonfinite")

    diagnostics: Dict[str, Any] = {
        "complex": complex_.name,
        "boundary_class": complex_.boundary_class,
        "proposal_imported": False,
        "proposal_claimed_passed": False,
        "scientific_validated_claimed": False,
    }

    try:
        w_e = _positive_weights(weights_edges, complex_.num_edges, "weights_edges")
        w_t = _positive_weights(weights_faces, complex_.num_triangles, "weights_faces")
    except IllConditionedError as exc:
        zeros_e = np.zeros(complex_.num_edges, dtype=float)
        return HodgeOracleResult(
            accepted=False,
            verdict=AuditVerdict.REJECTED_ILL_CONDITIONED.value,
            exact=zeros_e,
            coexact=zeros_e,
            harmonic=zeros_e,
            potential=np.zeros(complex_.num_vertices, dtype=float),
            stream_gamma=np.zeros(complex_.num_triangles, dtype=float),
            energy_total=0.0,
            energy_exact=0.0,
            energy_coexact=0.0,
            energy_harmonic=0.0,
            ortho_exact_coexact=0.0,
            ortho_exact_harmonic=0.0,
            ortho_coexact_harmonic=0.0,
            reconstruction_residual_w1=0.0,
            relative_reconstruction_error=0.0,
            relative_energy_error=0.0,
            cond_L0=float("inf"),
            cond_M=None,
            diagnostics={**diagnostics, "reject_reason": str(exc)},
        )

    d0 = complex_.d0()
    d1 = complex_.d1()
    W1 = np.diag(w_e)
    W1_inv = np.diag(1.0 / w_e)

    L0 = d0.T @ W1 @ d0
    cond_L0, rank_L0 = _effective_cond(L0)
    weight_ratio = float(np.max(w_e) / np.min(w_e))
    diagnostics["cond_L0"] = cond_L0
    diagnostics["rank_L0_effective"] = rank_L0
    diagnostics["weight_ratio"] = weight_ratio

    cond_M: Optional[float] = None
    rank_M = 0
    if complex_.num_triangles > 0:
        M = d1 @ W1_inv @ d1.T
        cond_M, rank_M = _effective_cond(M)
        diagnostics["cond_M"] = cond_M
        diagnostics["rank_M_effective"] = rank_M
    else:
        M = np.zeros((0, 0), dtype=float)
        diagnostics["cond_M"] = None

    # Reject extreme metric scale separation or pathological effective conditioning.
    weight_ratio_reject = math.sqrt(cond_reject)  # e.g. 1e6 when cond_reject=1e12
    reject_reason = None
    if weight_ratio > weight_ratio_reject:
        reject_reason = "weight_ratio_exceeds_threshold"
    elif cond_L0 > cond_reject:
        reject_reason = "cond_L0_exceeds_threshold"
    elif cond_M is not None and cond_M > cond_reject:
        reject_reason = "cond_M_exceeds_threshold"

    if reject_reason is not None:
        zeros_e = np.zeros(complex_.num_edges, dtype=float)
        return HodgeOracleResult(
            accepted=False,
            verdict=AuditVerdict.REJECTED_ILL_CONDITIONED.value,
            exact=zeros_e,
            coexact=zeros_e,
            harmonic=zeros_e,
            potential=np.zeros(complex_.num_vertices, dtype=float),
            stream_gamma=np.zeros(complex_.num_triangles, dtype=float),
            energy_total=weighted_norm_sq(w_e, omega_arr),
            energy_exact=0.0,
            energy_coexact=0.0,
            energy_harmonic=0.0,
            ortho_exact_coexact=0.0,
            ortho_exact_harmonic=0.0,
            ortho_coexact_harmonic=0.0,
            reconstruction_residual_w1=0.0,
            relative_reconstruction_error=0.0,
            relative_energy_error=0.0,
            cond_L0=cond_L0,
            cond_M=cond_M,
            diagnostics={
                **diagnostics,
                "reject_reason": reject_reason,
                "cond_reject_threshold": cond_reject,
                "weight_ratio_reject_threshold": weight_ratio_reject,
            },
        )

    rhs_alpha = d0.T @ (w_e * omega_arr)
    alpha, *_ = np.linalg.lstsq(L0, rhs_alpha, rcond=None)
    omega_exact = d0 @ alpha

    if complex_.num_triangles > 0:
        rhs_gamma = d1 @ omega_arr
        gamma, *_ = np.linalg.lstsq(M, rhs_gamma, rcond=None)
        omega_coexact = (1.0 / w_e) * (d1.T @ gamma)
    else:
        gamma = np.zeros(0, dtype=float)
        omega_coexact = np.zeros(complex_.num_edges, dtype=float)

    harmonic = omega_arr - omega_exact - omega_coexact

    e_tot = weighted_norm_sq(w_e, omega_arr)
    e_ex = weighted_norm_sq(w_e, omega_exact)
    e_co = weighted_norm_sq(w_e, omega_coexact)
    e_h = weighted_norm_sq(w_e, harmonic)
    o_ec = weighted_inner(w_e, omega_exact, omega_coexact)
    o_eh = weighted_inner(w_e, omega_exact, harmonic)
    o_ch = weighted_inner(w_e, omega_coexact, harmonic)
    residual = omega_arr - (omega_exact + omega_coexact + harmonic)
    # By construction residual is ~0; keep W1 residual for closure diagnostics.
    res_norm = float(np.sqrt(max(weighted_norm_sq(w_e, residual), 0.0)))
    tot_norm = float(np.sqrt(max(e_tot, 0.0)))
    rel_rec = res_norm / (tot_norm + 1e-12)
    rel_energy = abs(e_tot - (e_ex + e_co + e_h)) / (e_tot + 1e-12)

    diagnostics["atol"] = atol
    diagnostics["orthogonality_class"] = (
        "algebraic_when_exact; numerical_residual_depends_on_conditioning"
    )

    return HodgeOracleResult(
        accepted=True,
        verdict=AuditVerdict.PASS_SYNTHETIC.value,
        exact=omega_exact,
        coexact=omega_coexact,
        harmonic=harmonic,
        potential=alpha,
        stream_gamma=gamma,
        energy_total=e_tot,
        energy_exact=e_ex,
        energy_coexact=e_co,
        energy_harmonic=e_h,
        ortho_exact_coexact=o_ec,
        ortho_exact_harmonic=o_eh,
        ortho_coexact_harmonic=o_ch,
        reconstruction_residual_w1=res_norm,
        relative_reconstruction_error=rel_rec,
        relative_energy_error=rel_energy,
        cond_L0=cond_L0,
        cond_M=cond_M,
        diagnostics=diagnostics,
    )
