"""Builds the reference-audit report: constants, operator comparisons, levels executed.

Pure NumPy. Never imports MNE. Status is HOLD / SYNTHETIC_ONLY by construction.
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from . import pin
from .kkt import (
    apply_csd,
    csd_operator,
    csd_operator_regularised_after_inverse,
    csd_operator_without_sum_constraint,
    kkt_coefficients,
    legendre_matrices,
    regularise,
    unit_vectors,
    centering_matrix,
)
from .legendre import PROPOSAL_CONSTANTS, g_function, h_function
from .montages import MONTAGES

REPORT_SCHEMA = "NTS.MNECSDReferenceAudit.v1"
STATUS = "HOLD"
EVIDENCE = "SYNTHETIC_ONLY"
SPHERE_RADIUS_M = 0.095
LAMBDA2 = 1e-5
STIFFNESS = 4.0
N_TERMS = 50
N_TERMS_PROXY_INFINITE = 4000

LIMITATIONS = (
    "Reference is pure NumPy from the stated formulas; MNE was not executed in this environment.",
    "The Round 6 proposal's custom KKT code is not present in the repository, so it was not compared.",
    "Coefficient parity holds only for the 50-term truncation that MNE uses by default.",
    "Synthetic sensor montages only; no empirical EEG data, no participant data, no scientific claim.",
    "Output units are 1/length^2 times the input unit (V/m^2 when positions are in metres); not validated against any recording.",
)


def _rel(a: float, b: float) -> float:
    scale = max(abs(a), abs(b), 1e-300)
    return abs(a - b) / scale


def legendre_report() -> dict[str, Any]:
    rows = []
    for name, (x, shift, claimed) in PROPOSAL_CONSTANTS.items():
        xa = np.array([x])
        fn = g_function if shift == 0 else h_function
        truncated = float(fn(xa, STIFFNESS, N_TERMS)[0])
        proxy = float(fn(xa, STIFFNESS, N_TERMS_PROXY_INFINITE)[0])
        rows.append({
            "name": name,
            "claimed": claimed,
            "computed_n50": truncated,
            "abs_diff_n50": abs(truncated - claimed),
            "rel_diff_n50": _rel(truncated, claimed),
            "proxy_infinite_n4000": proxy,
            "truncation_shift_abs": abs(proxy - truncated),
        })
    return {"rows": rows, "convention": "n = 1..N inclusive, factor 1/(4*pi), no minus sign, no P_0 term"}


def _operator_checks(name: str, positions_unit: np.ndarray) -> dict[str, Any]:
    radius = SPHERE_RADIUS_M
    positions = radius * positions_unit
    n = positions_unit.shape[0]

    M_kkt = csd_operator(positions, radius=radius, lambda2=LAMBDA2, method="kkt")
    M_proj = csd_operator(positions, radius=radius, lambda2=LAMBDA2, method="projection")
    scale = float(np.max(np.abs(M_kkt)))

    unit = unit_vectors(positions)
    G, H = legendre_matrices(unit, stiffness=STIFFNESS, n_terms=N_TERMS)
    G_reg = regularise(G, LAMBDA2)
    C = kkt_coefficients(G_reg, centering_matrix(n))
    column_sum_residual = float(np.max(np.abs(C.sum(axis=0))))

    ones = np.ones(n)
    annihilation = float(np.max(np.abs(apply_csd(M_kkt, ones))))
    M_unit = csd_operator(positions_unit, radius=1.0, lambda2=LAMBDA2, method="kkt")
    sphere_scaling = float(np.max(np.abs(M_kkt * radius**2 - M_unit)) / np.max(np.abs(M_unit)))
    permutation = np.random.default_rng(7).permutation(n)
    M_perm = csd_operator(positions[permutation], radius=radius, lambda2=LAMBDA2, method="kkt")
    perm_residual = float(np.max(np.abs(M_perm - M_kkt[np.ix_(permutation, permutation)])))

    M_after = csd_operator_regularised_after_inverse(positions, radius=radius, lambda2=LAMBDA2)
    M_nosum = csd_operator_without_sum_constraint(positions, radius=radius, lambda2=LAMBDA2)

    return {
        "name": name,
        "n_channels": n,
        "cond_G_reg": float(np.linalg.cond(G_reg)),
        "kkt_vs_projection_max_abs": float(np.max(np.abs(M_kkt - M_proj))),
        "kkt_vs_projection_rel_to_max": float(np.max(np.abs(M_kkt - M_proj)) / scale),
        "column_sum_constraint_residual": column_sum_residual,
        "constant_potential_residual_rel": annihilation / scale,
        "sphere_scaling_rel_error": sphere_scaling,
        "channel_permutation_residual_rel": perm_residual / scale,
        "discriminant_lambda_after_inverse_rel": float(np.max(np.abs(M_after - M_kkt)) / scale),
        "discriminant_no_sum_constraint_rel": float(np.max(np.abs(M_nosum - M_kkt)) / scale),
        "finite": bool(np.all(np.isfinite(M_kkt))),
        "shape": list(M_kkt.shape),
        "max_abs_M": scale,
    }


def operator_report() -> dict[str, Any]:
    rows = [_operator_checks(name, builder()) for name, builder in MONTAGES.items()]
    degenerate = np.vstack([MONTAGES["seeded_cap_7"](), MONTAGES["seeded_cap_7"]()[:1]])
    try:
        csd_operator(SPHERE_RADIUS_M * degenerate, radius=SPHERE_RADIUS_M, lambda2=0.0)
        unregularised = {"outcome": "finite_result", "note": "duplicate sensors with lambda2=0 did not raise"}
    except np.linalg.LinAlgError:
        unregularised = {"outcome": "LinAlgError"}
    regularised = csd_operator(SPHERE_RADIUS_M * degenerate, radius=SPHERE_RADIUS_M, lambda2=LAMBDA2)
    return {
        "montages": rows,
        "duplicate_sensor_lambda2_zero": unregularised,
        "duplicate_sensor_lambda2_default_finite": bool(np.all(np.isfinite(regularised))),
    }


def build_report() -> dict[str, Any]:
    legendre = legendre_report()
    operator = operator_report()
    return {
        "schema_version": REPORT_SCHEMA,
        "status": STATUS,
        "evidence_class": EVIDENCE,
        "pinned_mne": {
            "version": pin.MNE_VERSION,
            "tag": pin.MNE_TAG,
            "tag_commit": pin.MNE_TAG_COMMIT,
            "sdist": pin.MNE_SDIST_FILENAME,
            "sdist_sha256": pin.MNE_SDIST_SHA256,
            "license": pin.MNE_LICENSE,
            "repository": pin.MNE_SOURCE_REPOSITORY,
            "source_file_sha256": dict(pin.MNE_SOURCE_FILES),
            "defaults": dict(pin.MNE_DEFAULTS),
        },
        "levels": {
            "L1_legendre_constants": "executed: pure NumPy, 4 proposal constants",
            "L2_operator_algebra": "executed: pure NumPy, KKT vs projection and property checks",
            "L3_mne_execution_parity": "not executed: MNE not importable and not installed by instruction; the live "
                                       "comparison in tests/optional_live_mne/ skips without MNE 1.13.2 and is not evidence",
        },
        "legendre": legendre,
        "operator": operator,
        "sphere_radius_m": SPHERE_RADIUS_M,
        "lambda2": LAMBDA2,
        "stiffness": STIFFNESS,
        "n_legendre_terms": N_TERMS,
        "units": "output = input unit / length^2; with positions in metres, V -> V/m^2",
        "limitations": list(LIMITATIONS),
    }


def to_json(report: dict[str, Any]) -> str:
    def _check(obj: Any) -> None:
        if isinstance(obj, float) and not math.isfinite(obj):
            raise ValueError(f"non-finite value in report: {obj!r}")
        if isinstance(obj, dict):
            for value in obj.values():
                _check(value)
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                _check(value)

    _check(report)
    return json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
