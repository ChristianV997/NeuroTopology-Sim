"""Exact DMD estimator and non-normal / EP diagnostics.

Status
------
``HOLD / SYNTHETIC_ONLY``. Recovering a discrete operator or locating an
exceptional point in a synthetic matrix does **not** establish a biological
exceptional point, a clinical bound, or a theory-of-everything claim.

Schema coordination
-------------------
Result dataclasses use ``schema_version = NeuroTopology.DMDCrouzeix.v1``.
Independent regression tests (Antigravity Agent D) should import this module
and assert against these field names; this file is the sole production writer
path for the estimator.

Array orientation and units
---------------------------
* Each trajectory is a 2-D array with shape ``(n_state, n_time)``.
* **State vectors are columns** (exact-DMD / Schmid convention).
* State entry units are caller-defined (arbitrary engineering units).
* ``dt`` is the uniform sampling interval in **seconds** between adjacent
  columns *within* a trajectory.

Within-trajectory snapshot pairing
----------------------------------
Adjacent-time pairs ``(x_t, x_{t+1})`` are built **separately inside each
trajectory**. Trajectories are never concatenated before pairing, so the false
seam pair ``(last(traj_i), first(traj_{i+1}))`` cannot appear.

Discrete-time primary estimand
------------------------------
Exact DMD recovers the discrete operator ``A`` such that ``Y ≈ A X``, where
columns of ``X`` / ``Y`` are the left / right members of each within-trajectory
pair (Tu et al.; Schmid). ``A`` (plus diagnostics) is the primary estimand.

Continuous-time generator (optional)
------------------------------------
If requested, a principal-branch matrix logarithm is taken via
``scipy.linalg.logm`` (Schur / Parlett–Schur based; not a hand-rolled
iteration). The continuous generator is reported as
``L = logm(A) / dt`` under the convention

    x_{t+1} = A x_t ≈ exp(L dt) x_t .

Principal-branch assumptions, Nyquist / alias ambiguity, conditioning, and
unsupported cases are reported explicitly. A small
``expm(logm(A)) ≈ A`` residual is a **reconstruction check only** — it does
not prove correct frequency or generator recovery.

Oscillatory phase convention
----------------------------
Discrete eigenvalues relate to continuous frequencies by

    λ = exp(-i ω dt),   ω = 2 π f  (rad/s),  f in Hz.

Under this convention a 240 Hz oscillation sampled at 250 Hz shares the same
sampled discrete phase as an aliased −10 Hz branch. The estimator reports that
ambiguity; it does not claim unique frequency recovery from samples alone.

EP2 fixture
-----------
The exact 2×2 EP2 model (coupling equal to detuning) is

    H(ω, δ, γ, g) = [[ω+δ − iγ, −i g],
                     [−i g,     ω−δ − iγ]].

At ``g = δ`` the spectrum coalesces analytically. After subtracting
``(ω − iγ) I``, the remainder ``N`` is nonzero with ``N² = 0``. Diagnostics
distinguish theoretical coalescence from numerically split eigenvalues and
prioritize operator-entry / nilpotency checks over ill-conditioned eigenvector
claims.

Crouzeix bound
--------------
Crouzeix's theorem (numerical-range bound): for a square matrix ``A`` and a
function ``f`` holomorphic on a neighborhood of the numerical range ``W(A)``,

    ||f(A)|| ≤ C  max_{z ∈ W(A)} |f(z)| .

The peer-reviewed constant ``C = 1 + √2`` (Crouzeix–Palencia, 2017) is the
proven fallback used here. Lorist & Schwenninger, ``arXiv:2608.03841v2``
(2026), is a preprint that claims a proof of Crouzeix’s conjecture
(``C = 2``). That version is verified as the cited preprint artifact, but
it remains unrefereed; this module exposes ``C = 2`` only under the label
``PREPRINT_UNVERIFIED`` and does **not** adopt it as a settled peer-reviewed
production constant. Neither constant is a biological or clinical safety
certificate.

Hermitian dissipation sign is read from the supplied generator under
``ẋ = L x``: the Hermitian part ``(L + L†)/2`` is dissipative when its
eigenvalues are ≤ 0 (contractive continuous semigroup). Callers using a
different sign convention must rescale before interpreting the report.

References
----------
* Schmid, P. J. (2010). Dynamic mode decomposition of numerical and
  experimental data. *J. Fluid Mech.*
* Tu, J. H., et al. (2014). On dynamic mode decomposition: theory and
  applications. *J. Comput. Dyn.*
* Crouzeix, M. & Palencia, C. (2017). The numerical range is a
  (1+√2)-spectral set. *SIAM J. Matrix Anal. Appl.*
* Lorist, E. & Schwenninger, F. L. arXiv:2608.03841v2 (2026) — preprint
  claiming a proof of ``C=2``; unrefereed; not adopted as settled here.
* SciPy ``scipy.linalg.logm`` (Schur–Parlett algorithm).
"""

from __future__ import annotations

import numbers
from dataclasses import asdict, dataclass
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np

try:
    from scipy.linalg import expm, logm

    _HAS_SCIPY_LOGM = True
except ImportError:  # pragma: no cover - optional continuous path
    expm = None  # type: ignore[assignment]
    logm = None  # type: ignore[assignment]
    _HAS_SCIPY_LOGM = False


SCHEMA_VERSION = "NeuroTopology.DMDCrouzeix.v1"
PROJECT_STATUS = "HOLD_SYNTHETIC_ONLY"
CROUZEIX_PEER_REVIEWED_C = 1.0 + float(np.sqrt(2.0))
CROUZEIX_PREPRINT_C2_LABEL = "PREPRINT_UNVERIFIED"
CROUZEIX_PREPRINT_C2_ARXIV = "arXiv:2608.03841v2"
ARRAY_ORIENTATION = "state_columns"
DEFAULT_RCOND = 1e-10
BRANCH_CUT_MARGIN = 1e-6

TrajectoryLike = Union[np.ndarray, Sequence[Sequence[complex]]]
TrajectoryInput = Union[TrajectoryLike, Sequence[TrajectoryLike]]


class DMDValidationError(ValueError):
    """Invalid DMD / EP diagnostic input."""


def _require_real(name: str, value: Any) -> float:
    """Return a finite-capable real scalar without accepting bools or strings."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise DMDValidationError(f"{name} must be a real number, got {value!r}")
    try:
        out = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise DMDValidationError(
            f"{name} must be representable as a finite float, got {value!r}"
        ) from exc
    return out


def _require_integer(name: str, value: Any) -> int:
    """Return an integral scalar without accepting bools or floats."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise DMDValidationError(f"{name} must be an integer, got {value!r}")
    return int(value)


@dataclass(frozen=True)
class SnapshotPairMeta:
    """Metadata for within-trajectory snapshot pairs."""

    n_trajectories: int
    n_pairs: int
    n_state: int
    pairs_per_trajectory: Tuple[int, ...]
    orientation: str = ARRAY_ORIENTATION
    state_units: str = "caller_defined"
    dt_units: str = "seconds"
    pairing_rule: str = "within_trajectory_adjacent_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DMDDiagnostics:
    """Diagnostics for the discrete-time exact-DMD estimate."""

    rank: int
    singular_values: Tuple[float, ...]
    cond_x: float
    residual_fro: float
    dt: float
    n_pairs: int
    n_state: int
    sample_rate_hz: Optional[float] = None
    frequency_units: str = "Hz"
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GeneratorDiagnostics:
    """Principal-branch / Nyquist diagnostics for optional continuous recovery."""

    status: str
    principal_branch: bool
    near_branch_cut: bool
    nyquist_ambiguity: bool
    logm_condition_estimate: Optional[float]
    round_trip_residual: Optional[float]
    assumptions: Tuple[str, ...]
    failure_reason: Optional[str] = None
    note: str = (
        "expm(logm(A))≈A is a reconstruction check only; "
        "it does not prove correct frequency or generator recovery."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DMDResult:
    """Primary discrete-time DMD result (+ optional continuous generator)."""

    A: np.ndarray
    diagnostics: DMDDiagnostics
    snapshot_meta: SnapshotPairMeta
    generator: Optional[np.ndarray] = None
    generator_diagnostics: Optional[GeneratorDiagnostics] = None
    schema_version: str = SCHEMA_VERSION
    project_status: str = PROJECT_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_status": self.project_status,
            "A": self.A,
            "diagnostics": self.diagnostics.to_dict(),
            "snapshot_meta": self.snapshot_meta.to_dict(),
            "generator": self.generator,
            "generator_diagnostics": (
                None
                if self.generator_diagnostics is None
                else self.generator_diagnostics.to_dict()
            ),
        }


@dataclass(frozen=True)
class EP2Report:
    """Exact EP2 nilpotency / coalescence diagnostic (synthetic fixture)."""

    theoretical_coalesced: bool
    discriminant: complex
    nilpotent_norm: float
    nilpotent_square_norm: float
    numerical_eig_gap: float
    geometric_multiplicity: int
    algebraic_multiplicity: int
    operator_entry_ok: bool
    notes: Tuple[str, ...]
    schema_version: str = SCHEMA_VERSION
    project_status: str = PROJECT_STATUS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrouzeixReport:
    """Numerical-range bound report (not a biological safety certificate)."""

    constant: float
    constant_label: str
    theorem_statement: str
    scope: str
    numerical_range_max_abs: Optional[float]
    hermitian_dissipation_sign: str
    not_biological_safety_certificate: bool = True
    schema_version: str = SCHEMA_VERSION
    project_status: str = PROJECT_STATUS
    references: Tuple[str, ...] = (
        "Crouzeix & Palencia, SIAM J. Matrix Anal. Appl. 2017 (C=1+sqrt(2))",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AliasAmbiguityReport:
    """Documented Nyquist alias under λ = exp(-i ω dt)."""

    f_hz: float
    f_alias_hz: float
    fs_hz: float
    dt: float
    lambda_true: complex
    lambda_alias: complex
    phases_match: bool
    convention: str
    claim: str
    schema_version: str = SCHEMA_VERSION
    project_status: str = PROJECT_STATUS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_state_matrix(traj: TrajectoryLike, *, index: int) -> np.ndarray:
    arr = np.asarray(traj)
    if arr.ndim != 2:
        raise DMDValidationError(
            f"trajectory[{index}] must be 2-D (n_state, n_time); got shape {arr.shape}"
        )
    if arr.shape[0] < 1 or arr.shape[1] < 2:
        raise DMDValidationError(
            f"trajectory[{index}] needs n_state>=1 and n_time>=2; got {arr.shape}"
        )
    if not np.all(np.isfinite(arr)):
        raise DMDValidationError(f"trajectory[{index}] contains non-finite values")
    return np.asarray(arr, dtype=np.complex128)


def _normalize_trajectories(trajectories: TrajectoryInput) -> List[np.ndarray]:
    """Accept one trajectory or a sequence of trajectories."""
    if isinstance(trajectories, np.ndarray) and trajectories.ndim == 2:
        return [_as_state_matrix(trajectories, index=0)]
    if not isinstance(trajectories, (list, tuple)):
        raise DMDValidationError(
            "trajectories must be a 2-D array or a sequence of 2-D arrays"
        )
    if len(trajectories) == 0:
        raise DMDValidationError("trajectories must be non-empty")
    # Ambiguous: a bare list of 1-D rows is rejected; require explicit 2-D blocks.
    out: List[np.ndarray] = []
    for i, traj in enumerate(trajectories):
        out.append(_as_state_matrix(traj, index=i))
    n_state = out[0].shape[0]
    for i, traj in enumerate(out):
        if traj.shape[0] != n_state:
            raise DMDValidationError(
                f"all trajectories must share n_state; traj[0]={n_state}, traj[{i}]={traj.shape[0]}"
            )
    return out


def build_snapshot_matrices(
    trajectories: TrajectoryInput,
) -> Tuple[np.ndarray, np.ndarray, SnapshotPairMeta]:
    """Build exact-DMD snapshot matrices with within-trajectory pairing only.

    Returns
    -------
    X, Y :
        Arrays of shape ``(n_state, n_pairs)`` with columns ``x_t`` and
        ``x_{t+1}`` drawn from the same trajectory.
    meta :
        Pairing metadata (never includes cross-trajectory seams).
    """
    trajs = _normalize_trajectories(trajectories)
    xs: List[np.ndarray] = []
    ys: List[np.ndarray] = []
    pairs_per: List[int] = []
    for traj in trajs:
        n_time = traj.shape[1]
        n_pairs = n_time - 1
        pairs_per.append(n_pairs)
        xs.append(traj[:, :-1])
        ys.append(traj[:, 1:])
    X = np.concatenate(xs, axis=1)
    Y = np.concatenate(ys, axis=1)
    meta = SnapshotPairMeta(
        n_trajectories=len(trajs),
        n_pairs=int(X.shape[1]),
        n_state=int(X.shape[0]),
        pairs_per_trajectory=tuple(pairs_per),
    )
    return X, Y, meta


def _select_rank(singular_values: np.ndarray, rank: Optional[int], rcond: float) -> int:
    if singular_values.size == 0:
        raise DMDValidationError("snapshot matrix X has no singular values")
    smax = float(singular_values[0])
    if not np.isfinite(smax) or smax <= 0.0:
        raise DMDValidationError("snapshot matrix X is rank-deficient (σ_max ≤ 0)")
    auto = int(np.sum(singular_values > rcond * smax))
    if auto < 1:
        raise DMDValidationError(
            "snapshot matrix X is numerically rank-deficient under the requested rcond"
        )
    if rank is None:
        return auto
    rank_i = _require_integer("rank", rank)
    if rank_i < 1:
        raise DMDValidationError("rank must be >= 1")
    return min(rank_i, auto, int(singular_values.size))


def _principal_branch_diagnostics(
    eigenvalues: np.ndarray,
    *,
    margin: float = BRANCH_CUT_MARGIN,
) -> Tuple[bool, float]:
    """Return (near_cut, min_phase_margin_to_±π)."""
    phases = []
    for z in eigenvalues:
        if z == 0:
            continue
        phases.append(abs(np.pi - abs(np.angle(z))))
    if not phases:
        return True, 0.0
    d = float(min(phases))
    return d <= margin, d


def _generator_from_A(
    A: np.ndarray,
    dt: float,
    *,
    sample_rate_hz: Optional[float] = None,
) -> Tuple[Optional[np.ndarray], GeneratorDiagnostics]:
    assumptions = (
        "principal_branch_matrix_logarithm",
        "L = logm(A) / dt",
        "dynamics convention x_{t+1} = A x_t ≈ exp(L dt) x_t",
        "oscillatory convention λ = exp(-i ω dt)",
        "Nyquist aliases share discrete phase; samples alone do not select the branch",
    )
    if not _HAS_SCIPY_LOGM:
        return None, GeneratorDiagnostics(
            status="unsupported",
            principal_branch=False,
            near_branch_cut=False,
            nyquist_ambiguity=True,
            logm_condition_estimate=None,
            round_trip_residual=None,
            assumptions=assumptions,
            failure_reason="scipy.linalg.logm unavailable; continuous generator not estimated",
        )
    evals = np.linalg.eigvals(A)
    if np.any(np.abs(evals) < DEFAULT_RCOND):
        return None, GeneratorDiagnostics(
            status="failed",
            principal_branch=True,
            near_branch_cut=False,
            nyquist_ambiguity=True,
            logm_condition_estimate=None,
            round_trip_residual=None,
            assumptions=assumptions,
            failure_reason="A has eigenvalue(s) near zero; principal log undefined / unstable",
        )
    near_cut, phase_margin = _principal_branch_diagnostics(evals)
    try:
        log_A = logm(A)
    except Exception as exc:  # pragma: no cover - scipy failure modes
        return None, GeneratorDiagnostics(
            status="failed",
            principal_branch=True,
            near_branch_cut=near_cut,
            nyquist_ambiguity=True,
            logm_condition_estimate=None,
            round_trip_residual=None,
            assumptions=assumptions,
            failure_reason=f"scipy.linalg.logm failed: {exc}",
        )
    if not np.all(np.isfinite(log_A)):
        return None, GeneratorDiagnostics(
            status="failed",
            principal_branch=True,
            near_branch_cut=near_cut,
            nyquist_ambiguity=True,
            logm_condition_estimate=None,
            round_trip_residual=None,
            assumptions=assumptions,
            failure_reason="logm(A) produced non-finite entries",
        )
    L = log_A / dt
    try:
        recon = expm(log_A)
        round_trip = float(np.linalg.norm(recon - A, ord="fro"))
    except Exception:  # pragma: no cover
        round_trip = None
    # Conditioning proxy: spread of |log λ| relative to min |λ|
    abs_evals = np.abs(evals)
    cond_est = float(np.max(abs_evals) / np.min(abs_evals)) if abs_evals.size else None
    status = "ambiguous" if near_cut else "ok"
    extra = (
        f"min_phase_margin_to_pi={phase_margin:.3e}",
        "round_trip residual is not proof of frequency recovery",
    )
    if sample_rate_hz is not None:
        extra = extra + (f"sample_rate_hz={float(sample_rate_hz)}",)
    return L, GeneratorDiagnostics(
        status=status,
        principal_branch=True,
        near_branch_cut=near_cut,
        nyquist_ambiguity=True,  # always true under sampled discrete phase
        logm_condition_estimate=cond_est,
        round_trip_residual=round_trip,
        assumptions=assumptions + extra,
        failure_reason=None,
    )


def estimate_exact_dmd(
    trajectories: TrajectoryInput,
    *,
    dt: float,
    rank: Optional[int] = None,
    rcond: float = DEFAULT_RCOND,
    estimate_generator: bool = False,
    sample_rate_hz: Optional[float] = None,
) -> DMDResult:
    """Estimate the discrete-time exact-DMD operator ``A``.

    Parameters
    ----------
    trajectories :
        One ``(n_state, n_time)`` array or a sequence of such arrays.
    dt :
        Sampling interval in seconds (must be finite and ``> 0``).
    rank :
        Optional truncation rank. Defaults to numerical rank under ``rcond``.
    rcond :
        Relative singular-value cutoff for rank / pseudoinverse.
    estimate_generator :
        If True, attempt ``L = logm(A)/dt`` via SciPy and attach diagnostics.
    sample_rate_hz :
        Optional sampling rate metadata for generator diagnostics
        (``1/dt`` is implied when omitted).
    """
    dt = _require_real("dt", dt)
    if not np.isfinite(dt) or dt <= 0.0:
        raise DMDValidationError("dt must be a finite positive float (seconds)")
    rcond = _require_real("rcond", rcond)
    if not np.isfinite(rcond) or rcond <= 0.0:
        raise DMDValidationError("rcond must be a finite positive float")
    if rank is not None:
        # Validate type early so bool True is not silently truncated to rank 1.
        _require_integer("rank", rank)
    if sample_rate_hz is not None:
        sample_rate_hz = _require_real("sample_rate_hz", sample_rate_hz)
        if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
            raise DMDValidationError("sample_rate_hz must be finite and positive when provided")
        implied_fs = 1.0 / float(dt)
        # Fail closed on inconsistent sampling metadata (would mislabel Nyquist aliases).
        if abs(float(sample_rate_hz) - implied_fs) > 1e-9 * max(implied_fs, 1.0):
            raise DMDValidationError(
                f"sample_rate_hz={sample_rate_hz} inconsistent with dt={dt} "
                f"(implied fs=1/dt={implied_fs})"
            )

    X, Y, meta = build_snapshot_matrices(trajectories)
    if X.shape[1] < 1:
        raise DMDValidationError("need at least one within-trajectory snapshot pair")

    # Economy SVD of X
    U, s, Vh = np.linalg.svd(X, full_matrices=False)
    warnings: List[str] = []
    try:
        r = _select_rank(s, rank, rcond)
    except DMDValidationError as exc:
        # Surface rank deficiency with diagnostics-friendly message.
        raise DMDValidationError(str(exc)) from exc

    if r < s.size:
        warnings.append(f"truncated_svd_rank={r}_of_{s.size}")
    cond_x = float(s[0] / s[r - 1]) if s[r - 1] > 0 else float("inf")
    if cond_x > 1e8:
        warnings.append(f"ill_conditioned_snapshot_matrix_cond≈{cond_x:.3e}")

    Ur = U[:, :r]
    sr = s[:r]
    Vhr = Vh[:r, :]
    # A = Y V Σ^{-1} U*
    A = (Y @ Vhr.conj().T) @ (np.diag(1.0 / sr) @ Ur.conj().T)
    if not np.all(np.isfinite(A)):
        raise DMDValidationError("estimated A contains non-finite values")
    residual = float(np.linalg.norm(Y - A @ X, ord="fro"))

    fs_report = float(sample_rate_hz) if sample_rate_hz is not None else (1.0 / float(dt))
    diag = DMDDiagnostics(
        rank=r,
        singular_values=tuple(float(v) for v in s),
        cond_x=cond_x,
        residual_fro=residual,
        dt=float(dt),
        n_pairs=meta.n_pairs,
        n_state=meta.n_state,
        sample_rate_hz=fs_report,
        frequency_units="Hz",
        warnings=tuple(warnings),
    )

    generator = None
    gen_diag = None
    if estimate_generator:
        generator, gen_diag = _generator_from_A(A, dt, sample_rate_hz=fs_report)

    return DMDResult(
        A=A,
        diagnostics=diag,
        snapshot_meta=meta,
        generator=generator,
        generator_diagnostics=gen_diag,
    )


def ep2_hamiltonian(
    omega: float,
    delta: float,
    gamma: float,
    g: float,
) -> np.ndarray:
    """Return the exact 2×2 non-Hermitian EP model matrix."""
    omega = _require_real("omega", omega)
    delta = _require_real("delta", delta)
    gamma = _require_real("gamma", gamma)
    g = _require_real("g", g)
    vals = (omega, delta, gamma, g)
    if not all(np.isfinite(v) for v in vals):
        raise DMDValidationError("ep2_hamiltonian parameters must be finite")
    return np.array(
        [
            [complex(omega + delta, -gamma), complex(0.0, -g)],
            [complex(0.0, -g), complex(omega - delta, -gamma)],
        ],
        dtype=np.complex128,
    )


def diagnose_ep2(
    H: np.ndarray,
    *,
    omega: Optional[float] = None,
    gamma: Optional[float] = None,
    tol: float = 1e-10,
) -> EP2Report:
    """Diagnose EP2 nilpotency / coalescence for a 2×2 matrix.

    Prioritizes operator-entry recovery (nonzero ``N``, ``N²≈0``) over
    eigenvector-based claims. Distinguishes analytic coalescence
    (``discriminant ≈ 0``) from a merely small numerical eigenvalue gap.
    """
    H = np.asarray(H, dtype=np.complex128)
    if H.shape != (2, 2):
        raise DMDValidationError("diagnose_ep2 expects a 2×2 matrix")
    if not np.all(np.isfinite(H)):
        raise DMDValidationError("H contains non-finite values")
    tol = _require_real("tol", tol)
    if not np.isfinite(tol) or tol < 0.0:
        raise DMDValidationError("tol must be a finite non-negative float")

    # Infer center if not provided: mean of diagonal (ω − iγ for the fixture).
    if omega is None or gamma is None:
        center = 0.5 * (H[0, 0] + H[1, 1])
    else:
        omega = _require_real("omega", omega)
        gamma = _require_real("gamma", gamma)
        center = complex(omega, -gamma)
    N = H - center * np.eye(2, dtype=np.complex128)
    # For the fixture, discriminant = δ² − g² with δ = Re(H00−center), g = Im(-H01).
    half_diff = 0.5 * (H[0, 0] - H[1, 1])
    disc = half_diff * half_diff + H[0, 1] * H[1, 0]
    # Equivalent for fixture: δ² − g² when off-diagonals are −i g.
    theoretical = abs(disc) <= tol
    N2 = N @ N
    n_norm = float(np.linalg.norm(N, ord="fro"))
    n2_norm = float(np.linalg.norm(N2, ord="fro"))
    evals = np.linalg.eigvals(H)
    gap = float(np.abs(evals[0] - evals[1]))
    # Geometric multiplicity via numerical nullity of N (SVD).
    s = np.linalg.svd(N, compute_uv=False)
    scale = max(n_norm, 1.0)
    nullity = int(np.sum(s <= tol * scale))
    geo = nullity
    # Algebraic multiplicity two when discriminant vanishes.
    alg = 2 if theoretical else 1
    operator_ok = (n_norm > tol) and (n2_norm <= tol * max(scale, 1.0))
    notes = [
        "operator-entry / nilpotency prioritized over eigenvector conditioning",
        "numerical eig gap may be nonzero under floating-point even at analytic EP",
        "synthetic fixture only; not a biological exceptional-point claim",
        "large eigenvector condition number alone is not evidence of an EP",
    ]
    if theoretical and gap > tol:
        notes.append(
            f"theoretical coalescence with numerically split eigenvalues (gap={gap:.3e})"
        )
    if theoretical and n_norm <= tol:
        notes.append(
            "repeated eigenvalue with N≈0 (diagonalizable degeneracy); not a defective EP2"
        )
    if operator_ok:
        notes.append("nonzero nilpotent N with N^2≈0 verified")
    return EP2Report(
        theoretical_coalesced=theoretical,
        discriminant=complex(disc),
        nilpotent_norm=n_norm,
        nilpotent_square_norm=n2_norm,
        numerical_eig_gap=gap,
        geometric_multiplicity=geo,
        algebraic_multiplicity=alg,
        operator_entry_ok=operator_ok,
        notes=tuple(notes),
    )


def discrete_eigenvalue_from_frequency_hz(freq_hz: float, dt: float) -> complex:
    """Map frequency (Hz) to discrete eigenvalue under λ = exp(-i ω dt)."""
    freq_hz = _require_real("freq_hz", freq_hz)
    dt = _require_real("dt", dt)
    if not np.isfinite(dt) or dt <= 0.0:
        raise DMDValidationError("dt must be finite and positive")
    if not np.isfinite(freq_hz):
        raise DMDValidationError("freq_hz must be finite")
    omega = 2.0 * np.pi * float(freq_hz)
    return complex(np.exp(-1j * omega * dt))


def alias_ambiguity_report(
    f_hz: float = 240.0,
    fs_hz: float = 250.0,
) -> AliasAmbiguityReport:
    """Report the discriminating 240 Hz ↔ −10 Hz alias at fs = 250 Hz."""
    f_hz = _require_real("f_hz", f_hz)
    fs_hz = _require_real("fs_hz", fs_hz)
    if not np.isfinite(f_hz):
        raise DMDValidationError("f_hz must be finite")
    if not np.isfinite(fs_hz) or fs_hz <= 0.0:
        raise DMDValidationError("fs_hz must be finite and positive")
    dt = 1.0 / float(fs_hz)
    f_alias = float(f_hz) - float(fs_hz)
    lam_t = discrete_eigenvalue_from_frequency_hz(f_hz, dt)
    lam_a = discrete_eigenvalue_from_frequency_hz(f_alias, dt)
    match = abs(lam_t - lam_a) <= 1e-12
    return AliasAmbiguityReport(
        f_hz=float(f_hz),
        f_alias_hz=f_alias,
        fs_hz=float(fs_hz),
        dt=dt,
        lambda_true=lam_t,
        lambda_alias=lam_a,
        phases_match=bool(match),
        convention="lambda = exp(-i * 2*pi*f * dt)",
        claim=(
            "samples alone do not select between f and f-fs; "
            "report ambiguity rather than claiming unique frequency recovery"
        ),
    )


def _numerical_range_max_abs(A: np.ndarray, n_samples: int = 256) -> float:
    """Approximate max |z| over W(A) via boundary sampling (diagnostic only)."""
    n = A.shape[0]
    rng = np.random.default_rng(0)
    # Unit sphere samples + coordinate axes
    samples = []
    for _ in range(n_samples):
        v = rng.normal(size=n) + 1j * rng.normal(size=n)
        v = v / np.linalg.norm(v)
        samples.append(abs(np.vdot(v, A @ v)))
    for i in range(n):
        e = np.zeros(n, dtype=np.complex128)
        e[i] = 1.0
        samples.append(abs(np.vdot(e, A @ e)))
    return float(max(samples))


def _hermitian_dissipation_sign(L: np.ndarray) -> str:
    """Sign of Hermitian dissipation under ẋ = L x."""
    H = 0.5 * (L + L.conj().T)
    evals = np.linalg.eigvalsh(H)
    if np.all(evals <= 1e-10):
        return "dissipative_nonpositive_hermitian_part"
    if np.all(evals >= -1e-10):
        return "anti_dissipative_nonnegative_hermitian_part"
    return "indefinite_hermitian_part"


def crouzeix_bound_report(
    matrix: np.ndarray,
    *,
    role: str = "discrete_operator",
    use_preprint_c2: bool = False,
) -> CrouzeixReport:
    """Report a Crouzeix numerical-range bound for a square matrix.

    Parameters
    ----------
    matrix :
        Discrete operator ``A`` or continuous generator ``L``.
    role :
        ``\"discrete_operator\"`` or ``\"generator\"`` (affects dissipation note).
    use_preprint_c2 :
        If True, label ``C=2`` from preprint ``arXiv:2608.03841v2``
        (Lorist & Schwenninger; claims a proof of Crouzeix’s conjecture) as
        ``PREPRINT_UNVERIFIED`` instead of using the peer-reviewed
        ``C=1+√2`` fallback. The preprint version is cited exactly, but it is
        **not** treated as a settled peer-reviewed production constant here.
    """
    A = np.asarray(matrix, dtype=np.complex128)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise DMDValidationError("crouzeix_bound_report expects a square matrix")
    if not np.all(np.isfinite(A)):
        raise DMDValidationError("matrix contains non-finite values")
    if role not in {"discrete_operator", "generator"}:
        raise DMDValidationError("role must be 'discrete_operator' or 'generator'")

    theorem = (
        "For square A and f holomorphic on a neighborhood of the numerical "
        "range W(A), ||f(A)|| ≤ C * max_{z in W(A)} |f(z)|."
    )
    scope = (
        "Applies to the supplied finite-dimensional matrix only; "
        "not a biological, clinical, or safety certificate; "
        "HOLD / SYNTHETIC_ONLY."
    )
    if use_preprint_c2:
        constant = 2.0
        label = CROUZEIX_PREPRINT_C2_LABEL
        refs = (
            f"C=2 from preprint {CROUZEIX_PREPRINT_C2_ARXIV} "
            "(Lorist & Schwenninger; claims a proof of Crouzeix's conjecture); "
            "PREPRINT_UNVERIFIED / unrefereed; not a settled peer-reviewed "
            "production constant in this module",
            "Peer-reviewed fallback remains Crouzeix–Palencia 2017 C=1+sqrt(2)",
        )
    else:
        constant = CROUZEIX_PEER_REVIEWED_C
        label = "peer_reviewed_crouzeix_palencia_2017"
        refs = ("Crouzeix & Palencia, SIAM J. Matrix Anal. Appl. 2017 (C=1+sqrt(2))",)

    nr_max = _numerical_range_max_abs(A)
    if role == "generator":
        diss = _hermitian_dissipation_sign(A)
    else:
        # For discrete A, report dissipation from a principal log when available;
        # otherwise mark as not_inferred_from_discrete_operator.
        if _HAS_SCIPY_LOGM:
            try:
                L = logm(A)
                if np.all(np.isfinite(L)):
                    diss = _hermitian_dissipation_sign(L) + "_via_principal_logm_of_A"
                else:
                    diss = "not_inferred_nonfinite_logm"
            except Exception:  # pragma: no cover
                diss = "not_inferred_logm_failed"
        else:
            diss = "not_inferred_scipy_logm_unavailable"

    return CrouzeixReport(
        constant=float(constant),
        constant_label=label,
        theorem_statement=theorem,
        scope=scope,
        numerical_range_max_abs=nr_max,
        hermitian_dissipation_sign=diss,
        references=refs,
    )


__all__ = [
    "SCHEMA_VERSION",
    "PROJECT_STATUS",
    "CROUZEIX_PEER_REVIEWED_C",
    "CROUZEIX_PREPRINT_C2_LABEL",
    "CROUZEIX_PREPRINT_C2_ARXIV",
    "ARRAY_ORIENTATION",
    "DMDValidationError",
    "SnapshotPairMeta",
    "DMDDiagnostics",
    "GeneratorDiagnostics",
    "DMDResult",
    "EP2Report",
    "CrouzeixReport",
    "AliasAmbiguityReport",
    "build_snapshot_matrices",
    "estimate_exact_dmd",
    "ep2_hamiltonian",
    "diagnose_ep2",
    "discrete_eigenvalue_from_frequency_hz",
    "alias_ambiguity_report",
    "crouzeix_bound_report",
]
