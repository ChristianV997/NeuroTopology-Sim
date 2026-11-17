"""Spherical-spline scalp current-source-density (CSD) transform — NumPy API.

Production surface for Batch 2 / Cursor Agent C.

Status
------
HOLD / SYNTHETIC_ONLY. This is a **sensor-space** spatial transform (surface
Laplacian / CSD). It is **not** anatomical source localization and is not
evidence of cortical mechanism, consciousness, or clinical effect.

Pinned upstream (parity target)
-------------------------------
- MNE-Python **1.13.2** (tag ``v1.13.2``, commit
  ``bf67729b805865b5bb0f2f97621e416278efd1b2``)
- Algorithm sources (read, not copied wholesale):
  - ``mne/preprocessing/_csd.py`` — ``compute_current_source_density``,
    ``_prepare_G``, ``_compute_csd``
  - ``mne/channels/interpolation.py`` — ``_calc_g``, ``_calc_h``
- License: BSD-3-Clause (MNE-Python)
- Mathematical formulation: Perrin et al. spherical splines
  (Perrin et al. 1987; Perrin et al. 1989), as implemented in the pinned MNE
  release (also citing Cohen 2014; Kayser & Tenke 2015 in MNE docs).

Recorded defaults (MNE 1.13.2)
-----------------------------
- Legendre truncation ``n_legendre_terms`` = 50 (inclusive n = 1..50)
- Stiffness ``m`` (``stiffness``) = 4
- Regularization ``lambda2`` = 1e-5 (added to the diagonal of G before invert)
- Sphere: **must be supplied explicitly** as ``(x, y, z, r)`` in meters —
  this module never fits a sphere, never loads a montage, never mutates
  reference, and never invents channel units.
- Output scaling: ``1 / R^2`` with R the sphere radius in meters → when the
  input voltages are in volts and positions/radius are in meters, the CSD
  matrix maps to **V/m²**.

Average-reference constraint
----------------------------
Matches the pinned MNE path: the RHS is column-centered
(``Z = I - mean``) and coefficient columns are corrected so that
``1^T c = 0`` via the projection form in ``_prepare_G`` / ``_compute_csd``
(``TC = Gi.sum(0)``, not a separate ``Gi @ 1`` path). The resulting
transform annihilates constant potentials (null-vector check).

Float64 note: ``inv(G+λ²I)`` is only symmetric to roughly 1e-9 on larger
montages, so entrywise residuals versus a live-MNE identity-matrix fixture
can sit near 1e-12 relative Frobenius without indicating an algorithmic
mismatch. Production parity gates should use tolerances justified by that
conditioning (e.g. 1e-9), not assume bitwise identity.

Relationship to ``adapters/mne_csd``
-----------------------------------
``adapters/mne_csd`` (PR #378) wraps MNE's high-level instance API. This
module is the NumPy operator (full N×N matrix + apply) for explicit
positions/data. Parameter names and defaults are aligned; do not introduce
a second incompatible CSD API.

Bad-channel policy
------------------
Caller must exclude bad channels **before** calling. This module does not
drop, interpolate, or re-order channels. Channel order is exactly the row
order of ``positions`` / ``channel_names``.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np
from numpy.polynomial.legendre import legval

# ---------------------------------------------------------------------------
# Pin / attribution (verified against MNE tag + PyPI sdist metadata)
# ---------------------------------------------------------------------------

MNE_PIN: Mapping[str, Any] = {
    "version": "1.13.2",
    "tag": "v1.13.2",
    "commit": "bf67729b805865b5bb0f2f97621e416278efd1b2",
    "license": "BSD-3-Clause",
    "repository": "https://github.com/mne-tools/mne-python",
    "api_doc": (
        "https://mne.tools/stable/generated/"
        "mne.preprocessing.compute_current_source_density.html"
    ),
    "source_files": (
        "mne/preprocessing/_csd.py",
        "mne/channels/interpolation.py",
    ),
    "sdist_sha256": "729829e35010a7273cce8608d61d930c973fbead6edc1a70316c01e3a5551521",
    "defaults": {
        "lambda2": 1e-5,
        "stiffness": 4.0,
        "n_legendre_terms": 50,
    },
    "output_unit_when_si": "V/m^2",
    "not_source_localization": True,
}

DEFAULT_LAMBDA2 = float(MNE_PIN["defaults"]["lambda2"])
DEFAULT_STIFFNESS = float(MNE_PIN["defaults"]["stiffness"])
DEFAULT_N_LEGENDRE_TERMS = int(MNE_PIN["defaults"]["n_legendre_terms"])
OUTPUT_UNIT_SI = "V/m^2"

# Fail-closed thresholds (engineering; documented, not silent).
DEFAULT_COINCIDENT_COS_TOL = 1e-12
DEFAULT_CONDITION_MAX = 1e12
# Relative to ||M||_inf: the null residual of M @ 1 is rounding-level, about n * eps * ||M||_inf.
DEFAULT_AVG_REF_NULL_RTOL = 1e-8


class SphericalCSDError(ValueError):
    """Fail-closed input / numerical error for the spherical CSD transform."""


def _as_mne_numeric(value: Any, name: str) -> float:
    """Validate a numeric CSD parameter without accepting text or booleans."""
    if isinstance(value, (bool, np.bool_)):
        raise SphericalCSDError(f"{name} must be numeric")
    try:
        if isinstance(value, (float, np.floating)):
            return float(value)
        return float(operator.index(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise SphericalCSDError(f"{name} must be numeric") from exc


@dataclass(frozen=True)
class SphericalCSDConfig:
    """Explicit CSD configuration — no silent montage / sphere / unit inference.

    Parameters
    ----------
    sphere :
        ``(x, y, z, r)`` in **meters**. Center is subtracted from sensor
        positions; ``r`` is the radius used for the ``1/R^2`` scale.
        Strings such as ``\"auto\"`` are rejected.
    lambda2 :
        Diagonal regularization added to G before inversion (MNE default 1e-5).
        Must satisfy ``0 <= lambda2 < 1``.
    stiffness :
        Spline stiffness ``m`` (MNE default 4). Must be non-negative.
    n_legendre_terms :
        Truncation count N for Legendre series (MNE default 50). Must be >= 1.
    coincident_cos_tol :
        If ``i != j`` and ``cos(angle_ij) >= 1 - tol``, sensors are treated as
        nearly coincident and the call fails closed.
    condition_max :
        If ``cond(G + lambda2 I)`` exceeds this value, fail closed with a
        diagnostic (ill-conditioned / near-duplicate geometry).
    avg_ref_null_rtol :
        Relative tolerance for the constant-potential null check on the finished
        transform: ``||M @ 1||_∞ <= avg_ref_null_rtol * ||M||_∞``. Relative, so the
        check does not depend on the length unit of the positions.
    enforce_avg_ref_null :
        When True (default), refuse to return a transform that fails the
        average-reference null-vector check.
    """

    sphere: Tuple[float, float, float, float]
    lambda2: float = DEFAULT_LAMBDA2
    stiffness: float = DEFAULT_STIFFNESS
    n_legendre_terms: int = DEFAULT_N_LEGENDRE_TERMS
    coincident_cos_tol: float = DEFAULT_COINCIDENT_COS_TOL
    condition_max: float = DEFAULT_CONDITION_MAX
    avg_ref_null_rtol: float = DEFAULT_AVG_REF_NULL_RTOL
    enforce_avg_ref_null: bool = True

    def validated(self) -> "SphericalCSDConfig":
        if not isinstance(self.sphere, (tuple, list)) or len(self.sphere) != 4:
            raise SphericalCSDError(
                "sphere must be an explicit (x, y, z, r) tuple in meters; "
                "got "
                f"{self.sphere!r}. This API never infers sphere='auto'."
            )
        try:
            x, y, z, r = (float(v) for v in self.sphere)
        except (TypeError, ValueError, OverflowError) as exc:
            raise SphericalCSDError(
                "sphere components must be finite floats (meters)"
            ) from exc
        for name, val in (("x", x), ("y", y), ("z", z), ("r", r)):
            if not np.isfinite(val):
                raise SphericalCSDError(f"sphere {name} must be finite, got {val!r}")
        if r <= 0.0:
            raise SphericalCSDError(f"sphere radius must be > 0 meters, got {r!r}")
        lambda2 = _as_mne_numeric(self.lambda2, "lambda2")
        if not (0.0 <= lambda2 < 1.0):
            raise SphericalCSDError(
                f"lambda2 must satisfy 0 <= lambda2 < 1, got {lambda2!r}"
            )
        stiffness = _as_mne_numeric(self.stiffness, "stiffness")
        if not np.isfinite(stiffness):
            raise SphericalCSDError(
                f"stiffness must be finite, got {stiffness!r}"
            )
        if stiffness < 0.0:
            raise SphericalCSDError(
                f"stiffness must be non-negative, got {stiffness!r}"
            )
        # Only true integers are valid, matching the pinned MNE (operator.index in
        # mne/utils/check.py _ensure_int). Floats, bools, and strings are refused.
        if isinstance(self.n_legendre_terms, bool):
            raise SphericalCSDError(
                f"n_legendre_terms must be an integer, got {self.n_legendre_terms!r}"
            )
        try:
            n_terms = operator.index(self.n_legendre_terms)
        except TypeError as exc:
            raise SphericalCSDError(
                f"n_legendre_terms must be an integer, got {self.n_legendre_terms!r}"
            ) from exc
        if n_terms < 1:
            raise SphericalCSDError(
                f"n_legendre_terms must be >= 1, got {self.n_legendre_terms!r}"
            )
        cos_tol = float(self.coincident_cos_tol)
        cond_max = float(self.condition_max)
        null_rtol = float(self.avg_ref_null_rtol)
        # NaN/Inf must fail closed: IEEE comparisons against NaN never trip the
        # ill-conditioning / avg-ref null guards, which would silently bypass them.
        if not np.isfinite(cos_tol):
            raise SphericalCSDError(
                f"coincident_cos_tol must be finite, got {self.coincident_cos_tol!r}"
            )
        if cos_tol < 0.0:
            raise SphericalCSDError("coincident_cos_tol must be non-negative")
        if not np.isfinite(cond_max):
            raise SphericalCSDError(
                f"condition_max must be finite, got {self.condition_max!r}"
            )
        if cond_max <= 0.0:
            raise SphericalCSDError("condition_max must be positive")
        if not np.isfinite(null_rtol):
            raise SphericalCSDError(
                f"avg_ref_null_rtol must be finite, got {self.avg_ref_null_rtol!r}"
            )
        if null_rtol < 0.0:
            raise SphericalCSDError("avg_ref_null_rtol must be non-negative")
        return SphericalCSDConfig(
            sphere=(x, y, z, r),
            lambda2=lambda2,
            stiffness=stiffness,
            n_legendre_terms=n_terms,
            coincident_cos_tol=cos_tol,
            condition_max=cond_max,
            avg_ref_null_rtol=null_rtol,
            enforce_avg_ref_null=bool(self.enforce_avg_ref_null),
        )


@dataclass(frozen=True)
class SphericalCSDResult:
    """Full N×N CSD transform and provenance for an explicit channel order.

    ``transform`` is the complete operator ``M`` with shape ``(N, N)`` for
    full-matrix conformance (e.g. Antigravity PR #419 fixtures). Apply as
    ``M @ data`` with channels along the first axis of ``data``, or use
    :func:`apply_spherical_csd`. Parity must compare this full matrix — not
    only scalar G/H kernel endpoints.
    """

    transform: np.ndarray
    channel_names: Tuple[str, ...]
    positions_m: np.ndarray
    config: SphericalCSDConfig
    output_unit: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    mne_pin: Mapping[str, Any] = field(default_factory=lambda: dict(MNE_PIN))

    @property
    def n_channels(self) -> int:
        return int(self.transform.shape[0])

    @property
    def matrix(self) -> np.ndarray:
        """Alias for :attr:`transform` (full N×N CSD operator)."""
        return self.transform


# ---------------------------------------------------------------------------
# Legendre G / H (MNE 1.13.2 formulas; independent evaluation via numpy.legval)
# ---------------------------------------------------------------------------


def _calc_g(cosang: np.ndarray, *, stiffness: float, n_legendre_terms: int) -> np.ndarray:
    """Spherical-spline G kernel (Perrin / MNE ``_calc_g`` convention).

    ``g_m(x) = Σ_{n=1..N} (2n+1) / (n^m (n+1)^m 4π) P_n(x)``
    """
    factors = [
        (2 * n + 1)
        / (n**stiffness * (n + 1) ** stiffness * 4 * np.pi)
        for n in range(1, n_legendre_terms + 1)
    ]
    return legval(cosang, [0.0] + factors)


def _calc_h(cosang: np.ndarray, *, stiffness: float, n_legendre_terms: int) -> np.ndarray:
    """Spherical-spline H kernel (Perrin / MNE ``_calc_h`` convention).

    ``h_m(x) = Σ_{n=1..N} (2n+1) / (n^{m-1} (n+1)^{m-1} 4π) P_n(x)``
    """
    factors = [
        (2 * n + 1)
        / (n ** (stiffness - 1) * (n + 1) ** (stiffness - 1) * 4 * np.pi)
        for n in range(1, n_legendre_terms + 1)
    ]
    return legval(cosang, [0.0] + factors)


def _prepare_g(G: np.ndarray, lambda2: float) -> Tuple[np.ndarray, np.ndarray, float]:
    """MNE ``_prepare_G``: regularize diagonal, invert, accumulate TC / sgi."""
    G_reg = np.array(G, dtype=float, copy=True)
    G_reg.flat[:: len(G_reg) + 1] += lambda2
    try:
        Gi = np.linalg.inv(G_reg)
    except np.linalg.LinAlgError as exc:
        raise SphericalCSDError(
            "G + lambda2*I is singular (duplicate or degenerate sensor geometry)"
        ) from exc
    TC = Gi.sum(axis=0)
    sgi = float(np.sum(TC))
    if not np.isfinite(sgi) or abs(sgi) == 0.0:
        raise SphericalCSDError(
            f"average-reference normalizer sgi={sgi!r} is non-finite or zero"
        )
    return Gi, TC, sgi


def _compute_csd_matrix(
    Gi: np.ndarray, TC: np.ndarray, sgi: float, H: np.ndarray, radius: float
) -> np.ndarray:
    """MNE ``_compute_csd`` applied to the identity → full N×N transform."""
    n_channels = H.shape[0]
    data = np.eye(n_channels)
    Z = data - data.mean(axis=0)
    Cp2 = Gi @ Z
    c02 = np.sum(Cp2, axis=0) / sgi
    C2 = Cp2 - np.outer(TC, c02)
    # MNE: X = (C2.T @ H).T / R^2  ==  H.T @ C2 / R^2
    return (C2.T @ H).T / (radius**2)


def _validate_positions_and_names(
    positions: np.ndarray,
    channel_names: Optional[Sequence[str]],
) -> Tuple[np.ndarray, Tuple[str, ...]]:
    try:
        pos = np.asarray(positions, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SphericalCSDError(
            "positions must be a numeric array with shape (n_channels, 3) in meters"
        ) from exc
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise SphericalCSDError(
            f"positions must have shape (n_channels, 3) in meters, got {pos.shape}"
        )
    n = int(pos.shape[0])
    if n < 2:
        raise SphericalCSDError(
            "at least two channels are required for the average-reference CSD"
        )
    if not np.all(np.isfinite(pos)):
        raise SphericalCSDError("positions must be finite (reject NaN/Inf)")
    # MNE rejects any channel whose loc[:3] is all-close to zero (before
    # sphere subtraction in their path they check raw locs). We check raw
    # positions for the all-zero pattern and also post-centering elsewhere.
    if np.isclose(pos, 0.0).all(axis=1).any():
        raise SphericalCSDError(
            "zero (0,0,0) sensor coordinate(s) rejected; "
            "supply valid 3D positions in meters (no montage inference)"
        )
    if channel_names is None:
        names = tuple(f"ch{i:03d}" for i in range(n))
    else:
        names = tuple(str(c) for c in channel_names)
        if len(names) != n:
            raise SphericalCSDError(
                f"channel_names length {len(names)} != n_channels {n}"
            )
        if len(set(names)) != n:
            raise SphericalCSDError("channel_names must be unique (order is identity)")
    return pos, names


def _unit_vectors_and_cosines(
    positions: np.ndarray,
    origin: Tuple[float, float, float],
    *,
    coincident_cos_tol: float,
) -> Tuple[np.ndarray, np.ndarray]:
    centred = positions - np.asarray(origin, dtype=float)
    norms = np.linalg.norm(centred, axis=1)
    if np.any(~np.isfinite(norms)) or np.any(norms <= 0.0):
        raise SphericalCSDError(
            "a sensor coincides with the sphere origin or has non-finite offset; "
            "cannot project onto the unit sphere"
        )
    unit = centred / norms[:, None]
    cos = np.clip(unit @ unit.T, -1.0, 1.0)
    # Nearly coincident distinct sensors → fail closed.
    off = cos.copy()
    np.fill_diagonal(off, -np.inf)
    worst = float(np.max(off))
    if worst >= 1.0 - coincident_cos_tol:
        i, j = np.unravel_index(int(np.argmax(off)), off.shape)
        raise SphericalCSDError(
            f"nearly coincident sensors at indices ({i}, {j}): "
            f"cos={worst!r} >= 1 - {coincident_cos_tol}"
        )
    return unit, cos


def compute_spherical_csd_transform(
    positions: np.ndarray,
    config: SphericalCSDConfig,
    *,
    channel_names: Optional[Sequence[str]] = None,
) -> SphericalCSDResult:
    """Compute the full N×N spherical-spline CSD transform matrix.

    Parameters
    ----------
    positions :
        ``(n_channels, 3)`` sensor coordinates in **meters**, in the same
        order as the data rows that will be transformed.
    config :
        Explicit :class:`SphericalCSDConfig` (sphere required; no ``\"auto\"``).
    channel_names :
        Optional explicit names (length N). Order is preserved and recorded.
        If omitted, synthetic names ``ch000..`` are assigned (not a montage).

    Returns
    -------
    SphericalCSDResult
        ``transform`` has shape ``(N, N)``. Apply as ``transform @ data`` with
        ``data`` shaped ``(N, n_times)``. When positions/radius are meters and
        voltages are volts, ``output_unit`` is ``V/m^2``.
    """
    cfg = config.validated()
    pos, names = _validate_positions_and_names(positions, channel_names)
    x, y, z, radius = cfg.sphere
    _unit, cos = _unit_vectors_and_cosines(
        pos, (x, y, z), coincident_cos_tol=cfg.coincident_cos_tol
    )

    try:
        G = _calc_g(cos, stiffness=cfg.stiffness, n_legendre_terms=cfg.n_legendre_terms)
        H = _calc_h(cos, stiffness=cfg.stiffness, n_legendre_terms=cfg.n_legendre_terms)
    except OverflowError as exc:
        raise SphericalCSDError(
            f"stiffness {cfg.stiffness!r} overflows float64 in the Legendre kernel"
        ) from exc
    if not np.all(np.isfinite(G)) or not np.all(np.isfinite(H)):
        raise SphericalCSDError("non-finite G/H kernel values")

    G_reg = np.array(G, dtype=float, copy=True)
    G_reg.flat[:: len(G_reg) + 1] += cfg.lambda2
    try:
        cond = float(np.linalg.cond(G_reg))
    except np.linalg.LinAlgError as exc:
        raise SphericalCSDError("failed to estimate cond(G + lambda2*I)") from exc
    if not np.isfinite(cond) or cond > cfg.condition_max:
        raise SphericalCSDError(
            f"ill-conditioned G + lambda2*I: cond={cond!r} "
            f"(limit {cfg.condition_max}); check for near-duplicate sensors "
            "or increase lambda2 explicitly"
        )

    Gi, TC, sgi = _prepare_g(G, cfg.lambda2)
    transform = _compute_csd_matrix(Gi, TC, sgi, H, radius)
    if not np.all(np.isfinite(transform)):
        raise SphericalCSDError("non-finite CSD transform matrix")

    ones = np.ones(transform.shape[0])
    null_residual = transform @ ones
    null_inf = float(np.max(np.abs(null_residual)))
    row_sum_inf = float(np.max(np.abs(transform.sum(axis=1))))
    matrix_inf = float(np.linalg.norm(transform, ord=np.inf))
    if not all(np.isfinite(value) for value in (null_inf, row_sum_inf, matrix_inf)):
        raise SphericalCSDError("non-finite CSD transform norm diagnostic")
    # An identically zero operator passes any relative null check, so refuse it outright.
    if matrix_inf == 0.0:
        raise SphericalCSDError(
            "CSD transform is identically zero; the kernel or regularization is degenerate"
        )
    diagnostics = {
        "n_channels": int(transform.shape[0]),
        "sphere_m": cfg.sphere,
        "lambda2": cfg.lambda2,
        "stiffness": cfg.stiffness,
        "n_legendre_terms": cfg.n_legendre_terms,
        "cond_G_reg": cond,
        "sgi": sgi,
        "avg_ref_null_inf": null_inf,
        "avg_ref_null_rel": null_inf / matrix_inf,
        "matrix_inf": matrix_inf,
        "row_sum_inf": row_sum_inf,
        "scaling": "1/R^2",
        "channel_order": list(names),
        "mne_version_pin": MNE_PIN["version"],
        "mne_commit_pin": MNE_PIN["commit"],
        "bad_channel_policy": (
            "caller must exclude bad channels before invoke; "
            "no drop/interpolate/reorder"
        ),
        "status": "HOLD",
        "evidence_class": "SYNTHETIC_ONLY",
        "not_source_localization": True,
    }
    if cfg.enforce_avg_ref_null and null_inf > cfg.avg_ref_null_rtol * matrix_inf:
        raise SphericalCSDError(
            f"average-reference null-vector check failed: ||M @ 1||_∞ = {null_inf!r} "
            f"> rtol {cfg.avg_ref_null_rtol} * ||M||_∞ = {cfg.avg_ref_null_rtol * matrix_inf!r}"
        )

    return SphericalCSDResult(
        transform=transform,
        channel_names=names,
        positions_m=np.array(pos, dtype=float, copy=True),
        config=cfg,
        output_unit=OUTPUT_UNIT_SI,
        diagnostics=diagnostics,
        mne_pin=dict(MNE_PIN),
    )


def apply_spherical_csd(
    transform: np.ndarray,
    data: np.ndarray,
    *,
    channel_axis: int = 0,
) -> np.ndarray:
    """Apply an N×N CSD transform to sensor data.

    Parameters
    ----------
    transform :
        ``(N, N)`` matrix from :func:`compute_spherical_csd_transform`.
    data :
        Array with ``N`` channels along ``channel_axis`` (default 0).
        Common shapes: ``(N, n_times)`` or ``(n_epochs, N, n_times)`` with
        ``channel_axis=1``.
    channel_axis :
        Axis indexing channels; must match the transform's channel order.
    """
    T = np.asarray(transform, dtype=float)
    if T.ndim != 2 or T.shape[0] != T.shape[1]:
        raise SphericalCSDError("transform must be square (N, N)")
    if not np.all(np.isfinite(T)):
        raise SphericalCSDError("transform contains non-finite values")
    X = np.asarray(data, dtype=float)
    if not np.all(np.isfinite(X)):
        raise SphericalCSDError("data contains non-finite values")
    if channel_axis < 0:
        channel_axis += X.ndim
    if channel_axis < 0 or channel_axis >= X.ndim:
        raise SphericalCSDError(f"channel_axis {channel_axis} out of range for data.ndim={X.ndim}")
    if X.shape[channel_axis] != T.shape[0]:
        raise SphericalCSDError(
            f"data channel count {X.shape[channel_axis]} != transform N={T.shape[0]}"
        )
    # Move channels to axis 0, apply, move back.
    Xc = np.moveaxis(X, channel_axis, 0)
    flat = Xc.reshape(T.shape[0], -1)
    Y = T @ flat
    Yc = Y.reshape(Xc.shape)
    return np.moveaxis(Yc, 0, channel_axis)


__all__ = [
    "MNE_PIN",
    "DEFAULT_LAMBDA2",
    "DEFAULT_STIFFNESS",
    "DEFAULT_N_LEGENDRE_TERMS",
    "OUTPUT_UNIT_SI",
    "SphericalCSDError",
    "SphericalCSDConfig",
    "SphericalCSDResult",
    "compute_spherical_csd_transform",
    "apply_spherical_csd",
]
