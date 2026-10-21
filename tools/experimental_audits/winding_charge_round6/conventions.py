"""Explicit branch-cut and origin-shift conventions for the Round 6 oracle.

Unresolved ambiguities between documents are recorded here rather than silently
resolved toward a biological interpretation.
"""

from __future__ import annotations

# Principal interval for wrapped edge phase differences.
# Formula: wrap(φ) = ((φ + π) mod 2π) − π, with exact +π forced to −π.
WRAP_INTERVAL = "[-pi, pi)"
BRANCH_AT_PLUS_PI = "maps_to_minus_pi"
BRANCH_AT_MINUS_PI = "stays_minus_pi"

# Branch index recovery: n = rint((Δθ − wrap(Δθ)) / 2π).
# This avoids the half-integer ambiguity of rint(Δθ / 2π) at Δθ = ±π
# (where Δθ/(2π)=±0.5 and IEEE banker's rounding would yield n=0 while
# leaving ω=±π outside or on the wrong edge of the principal interval).
BRANCH_INDEX_METHOD = "recover_from_wrap"

# Origin-shift identity (mission statement):
#   If the coordinate origin moves by vector a (equivalently r' = r − a),
#   the signed first moment transforms as
#       p_q(r − a) = p_q(r) − Q_net * a
# Coordinate-translation form (PR #385 §4.3):
#   If points are translated by v (r' = r + v),
#       m(r + v) = m(r) + Q_net * v
# These are algebraically equivalent with a = −v.
ORIGIN_SHIFT_IDENTITY = "p_q(r - a) = p_q(r) - Q_net * a"
COORDINATE_TRANSLATION_IDENTITY = "m(r + v) = m(r) + Q_net * v"

# Missing-sign charge separation must be explicitly undefined.
MISSING_SIGN_SEPARATION = "undefined_nan_plus_boolean"

# Project posture for this auditor.
PROJECT_STATUS = "HOLD"
DATA_POLICY = "SYNTHETIC_ONLY"
SCIENTIFIC_VALIDATED_FORBIDDEN = True

AMBIGUITIES = (
    (
        "Exact ±π edge differences: rint(Δθ/2π) at ±0.5 is banker's-rounding "
        "ambiguous; this oracle recovers n from wrap(Δθ) instead."
    ),
    (
        "PR #385 documents m'=m+Q_net*v under point translation; the Batch 2 "
        "mission states p_q shifts by −Q_net*a under origin shift a. Both are "
        "checked; they agree when a=−v."
    ),
    (
        "PR #385 returns None for undefined separation; this independent oracle "
        "returns NaN values plus charge_separation_defined=False as requested "
        "by the audit mission (not a silent 0.0)."
    ),
    (
        "Algebraic integer winding / moment identities do not establish a "
        "biological, clinical, or consciousness interpretation."
    ),
)
