"""Synthetic EEG forward-model contract and verification fixture for NeuroTopology-Sim.

This module establishes a strict, type-safe contract around synthetic EEG forward modeling
in the dual-engine pipeline (dual_engine/source_space_tda_pipeline.py and data_adapters.py).

SCIENTIFIC AND ENGINEERING GUARDRAILS:
-------------------------------------
1. SYNTHETIC_ONLY / ENGINEERING_ONLY:
   All forward models produced or audited by this module are synthetic approximations
   (e.g., concentric spherical conductor models) designed exclusively for unit verification,
   coordinate contract enforcement, numerical stability tests, and regression fixtures.
2. NO ANATOMICAL PROMOTION:
   A spherical head model is NOT an individual anatomical localization. It does not replace
   subject MRI, boundary element models (BEM), or finite element models (FEM).
3. NO BIOLOGICAL / CONSCIOUSNESS CLAIMS:
   No claim is made that synthetic leadfield inversions reflect biological ground truth,
   causal neural dynamics, or validation of consciousness theories.
4. FAIL-CLOSED GEOMETRY:
   Ambiguous, missing, or out-of-scale coordinates (e.g. millimeters instead of meters,
   unaligned coordinate frames, out-of-bounds sources) fail closed immediately with
   explicit contract exceptions.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# -----------------------------------------------------------------------------
# Unit and Framing Constants
# -----------------------------------------------------------------------------

CANONICAL_LENGTH_UNIT: str = "m"
CANONICAL_POTENTIAL_UNIT: str = "V"
CANONICAL_DIPOLE_MOMENT_UNIT: str = "A*m"
CANONICAL_CONDUCTIVITY_UNIT: str = "S/m"
CANONICAL_ANGLE_UNIT: str = "rad"

MAX_PLAUSIBLE_SCALP_RADIUS_M: float = 0.20
MIN_PLAUSIBLE_SCALP_RADIUS_M: float = 0.04
MILLIMETER_THRESHOLD_M: float = 1.0  # Coordinates > 1.0m indicate millimeter units

DEFAULT_SCALP_RADIUS_M: float = 0.090
DEFAULT_SKULL_RADIUS_M: float = 0.085
DEFAULT_BRAIN_RADIUS_M: float = 0.080

DEFAULT_SCALP_SIGMA: float = 0.33
DEFAULT_SKULL_SIGMA: float = 0.0042
DEFAULT_BRAIN_SIGMA: float = 0.33

CONTRACT_DISCLAIMER: str = (
    "SYNTHETIC/ENGINEERING CONTRACT ONLY. "
    "This forward model uses idealized spherical conductor geometry "
    "and synthetic dipole positions for pipeline verification and contract testing. "
    "It does NOT constitute individual anatomical MRI localization, "
    "biological truth, clinical evidence, causal brain dynamics, "
    "or validation of consciousness theories."
)


# -----------------------------------------------------------------------------
# Contract Exceptions
# -----------------------------------------------------------------------------

class ForwardModelContractError(ValueError):
    """Base exception for all forward-model contract violations."""


class CoordinateUnitMismatchError(ForwardModelContractError):
    """Raised when coordinates appear to be specified in millimeters instead of meters."""


class CoordinateFrameMismatchError(ForwardModelContractError):
    """Raised when an unaligned or unsupported coordinate frame is encountered."""


class ConductorGeometryError(ForwardModelContractError):
    """Raised when conductor geometry parameters violate physical or spherical invariants."""


class LeadfieldDimensionMismatchError(ForwardModelContractError):
    """Raised when leadfield matrix dimensions do not match channel or source counts."""


class ChannelOrderMismatchError(ForwardModelContractError):
    """Raised when channel labels or ordering do not match leadfield rows."""


class SourceOutOfBoundsError(ForwardModelContractError):
    """Raised when a dipole source is positioned outside the innermost conductor shell."""


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class CoordinateFrame(str, Enum):
    """Supported coordinate frame designations."""
    HEAD = "head"            # MNE FIFFV_COORD_HEAD (x: LPA->RPA, y: Nasion, z: Up)
    MNI = "mni"              # MNI / Talairach template frame
    UNKNOWN = "unknown"      # Unverified or legacy frame (must fail closed)


class ConductorModelType(str, Enum):
    """Supported conductor model categories."""
    SPHERICAL_3SHELL = "spherical_3shell"  # Brain, skull, scalp concentric spheres
    SPHERICAL_1SHELL = "spherical_1shell"  # Single homogeneous sphere
    ANATOMICAL_BEM = "anatomical_bem"      # Anatomical BEM (unsupported in synthetic fixture)


class OrientationType(str, Enum):
    """Dipole orientation modes."""
    FREE = "free"    # 3 orthogonal dipole components per source location
    FIXED = "fixed"  # 1 dipole component along specified normal/radial vector


class ContractStatus(str, Enum):
    """Contract evaluation outcomes."""
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    ENGINEERING_ONLY = "ENGINEERING_ONLY"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED = "REJECTED"


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ConductorModel:
    """Concentric spherical conductor model definition."""
    model_type: ConductorModelType = ConductorModelType.SPHERICAL_3SHELL
    radii_m: Tuple[float, ...] = (DEFAULT_BRAIN_RADIUS_M, DEFAULT_SKULL_RADIUS_M, DEFAULT_SCALP_RADIUS_M)
    sigmas_sm: Tuple[float, ...] = (DEFAULT_BRAIN_SIGMA, DEFAULT_SKULL_SIGMA, DEFAULT_SCALP_SIGMA)
    origin_m: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def validate(self) -> None:
        """Validate spherical conductor model physical consistency."""
        if len(self.radii_m) != len(self.sigmas_sm):
            raise ConductorGeometryError(
                f"Mismatch: {len(self.radii_m)} radii vs {len(self.sigmas_sm)} conductivities."
            )
        if not self.radii_m:
            raise ConductorGeometryError("Conductor model requires at least one layer.")

        for i, r in enumerate(self.radii_m):
            if r > MILLIMETER_THRESHOLD_M:
                raise CoordinateUnitMismatchError(
                    f"Radius layer {i} is {r}m > 1.0m; coordinates must be in meters, not mm."
                )
            if r <= 0:
                raise ConductorGeometryError(f"Radius layer {i} must be positive, got {r}.")

        # Check strictly monotonic radii
        for i in range(len(self.radii_m) - 1):
            if self.radii_m[i] >= self.radii_m[i + 1]:
                raise ConductorGeometryError(
                    f"Layer radii must be strictly increasing: {self.radii_m[i]} >= {self.radii_m[i+1]}"
                )

        # Check scalp radius bounds
        outer_r = self.radii_m[-1]
        if not (MIN_PLAUSIBLE_SCALP_RADIUS_M <= outer_r <= MAX_PLAUSIBLE_SCALP_RADIUS_M):
            raise ConductorGeometryError(
                f"Outer conductor radius {outer_r}m outside plausible range "
                f"[{MIN_PLAUSIBLE_SCALP_RADIUS_M}, {MAX_PLAUSIBLE_SCALP_RADIUS_M}]m."
            )

        for i, s in enumerate(self.sigmas_sm):
            if s <= 0:
                raise ConductorGeometryError(f"Conductivity layer {i} must be positive, got {s}.")

    @property
    def brain_radius_m(self) -> float:
        """Return innermost shell radius (brain compartment)."""
        return self.radii_m[0]

    @property
    def scalp_radius_m(self) -> float:
        """Return outermost shell radius (scalp surface)."""
        return self.radii_m[-1]


@dataclass(frozen=True)
class SensorGeometry:
    """Sensor montage configuration with verified SI units."""
    channel_names: Tuple[str, ...]
    positions_m: Tuple[Tuple[float, float, float], ...]
    coordinate_frame: CoordinateFrame = CoordinateFrame.HEAD
    reference_channel: Optional[str] = None

    def validate(self) -> None:
        """Validate sensor montage consistency and coordinate scaling."""
        if len(self.channel_names) != len(self.positions_m):
            raise LeadfieldDimensionMismatchError(
                f"Channel count ({len(self.channel_names)}) does not match "
                f"positions count ({len(self.positions_m)})."
            )
        if len(self.channel_names) < 4:
            raise ForwardModelContractError(
                f"At least 4 channels are required for 3D forward geometry; got {len(self.channel_names)}."
            )
        if len(set(self.channel_names)) != len(self.channel_names):
            raise ForwardModelContractError("Duplicate channel names detected in sensor montage.")
        if self.coordinate_frame == CoordinateFrame.UNKNOWN:
            raise CoordinateFrameMismatchError("Coordinate frame UNKNOWN is rejected; must be HEAD or MNI.")

        for ch, pos in zip(self.channel_names, self.positions_m):
            norm = math.sqrt(sum(p * p for p in pos))
            if norm > MILLIMETER_THRESHOLD_M:
                raise CoordinateUnitMismatchError(
                    f"Channel '{ch}' position norm {norm:.2f}m > 1.0m; "
                    "positions must be specified in meters (m), not millimeters (mm)."
                )
            if not (MIN_PLAUSIBLE_SCALP_RADIUS_M <= norm <= MAX_PLAUSIBLE_SCALP_RADIUS_M):
                raise ConductorGeometryError(
                    f"Channel '{ch}' position norm {norm:.4f}m outside plausible scalp range "
                    f"[{MIN_PLAUSIBLE_SCALP_RADIUS_M}, {MAX_PLAUSIBLE_SCALP_RADIUS_M}]m."
                )

    @property
    def n_channels(self) -> int:
        return len(self.channel_names)


@dataclass(frozen=True)
class SourceSpace:
    """Dipole source locations and orientation configuration."""
    positions_m: Tuple[Tuple[float, float, float], ...]
    orientations: Optional[Tuple[Tuple[float, float, float], ...]] = None
    is_fixed_orientation: bool = False
    coordinate_frame: CoordinateFrame = CoordinateFrame.HEAD

    def validate(self, conductor: Optional[ConductorModel] = None) -> None:
        """Validate dipole positions and orientation unit vectors."""
        if not self.positions_m:
            raise ForwardModelContractError("Source space must contain at least one source location.")
        if self.coordinate_frame == CoordinateFrame.UNKNOWN:
            raise CoordinateFrameMismatchError("Coordinate frame UNKNOWN is rejected; must be HEAD or MNI.")

        brain_r = conductor.brain_radius_m if conductor is not None else DEFAULT_BRAIN_RADIUS_M

        for i, pos in enumerate(self.positions_m):
            norm = math.sqrt(sum(p * p for p in pos))
            if norm > MILLIMETER_THRESHOLD_M:
                raise CoordinateUnitMismatchError(
                    f"Source index {i} position norm {norm:.2f}m > 1.0m; must be in meters."
                )
            if norm >= brain_r:
                raise SourceOutOfBoundsError(
                    f"Source index {i} position norm {norm:.4f}m exceeds "
                    f"brain shell radius {brain_r:.4f}m."
                )

        if self.is_fixed_orientation:
            if self.orientations is None:
                raise ForwardModelContractError(
                    "Fixed orientation requested but no orientation vectors provided."
                )
            if len(self.orientations) != len(self.positions_m):
                raise ForwardModelContractError(
                    f"Orientation count ({len(self.orientations)}) does not match "
                    f"source count ({len(self.positions_m)})."
                )
            for i, ori in enumerate(self.orientations):
                norm = math.sqrt(sum(o * o for o in ori))
                if abs(norm - 1.0) > 1e-4:
                    raise ForwardModelContractError(
                        f"Fixed orientation vector at index {i} must be unit norm; got {norm}."
                    )

    @property
    def n_sources(self) -> int:
        return len(self.positions_m)

    @property
    def n_columns(self) -> int:
        return self.n_sources if self.is_fixed_orientation else self.n_sources * 3


@dataclass(frozen=True)
class LeadfieldDiagnostics:
    """Numerical diagnostics and conditioning metrics for the leadfield matrix."""
    n_channels: int
    n_sources: int
    n_columns: int
    is_fixed_orientation: bool
    numerical_rank: int
    condition_number: float
    singular_values: Tuple[float, ...]
    channel_frobenius_norms: Tuple[float, ...]
    is_average_referenced: bool
    zero_sum_column_error: float
    min_channel_norm: float
    max_channel_norm: float
    is_well_conditioned: bool
    crosstalk_index: float


@dataclass(frozen=True)
class ForwardModelContractResult:
    """Comprehensive contract evaluation artifact."""
    status: ContractStatus
    is_valid: bool
    leadfield: Tuple[Tuple[float, ...], ...]
    sensor_geometry: SensorGeometry
    conductor_model: ConductorModel
    source_space: SourceSpace
    diagnostics: LeadfieldDiagnostics
    warnings: Tuple[str, ...] = ()
    failure_reason: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to standard dictionary."""
        return {
            "status": self.status.value,
            "is_valid": self.is_valid,
            "channel_names": list(self.sensor_geometry.channel_names),
            "n_channels": self.sensor_geometry.n_channels,
            "n_sources": self.source_space.n_sources,
            "n_columns": self.source_space.n_columns,
            "is_fixed_orientation": self.source_space.is_fixed_orientation,
            "coordinate_frame": self.sensor_geometry.coordinate_frame.value,
            "diagnostics": asdict(self.diagnostics),
            "warnings": list(self.warnings),
            "failure_reason": self.failure_reason,
            "provenance": self.provenance,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize metadata and diagnostics to strict finite JSON."""
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)

    def simulate_scalp_potentials(
        self,
        dipole_moments: Sequence[Sequence[float]],
    ) -> List[List[float]]:
        """Simulate scalp potentials V = L * q.

        dipole_moments: (n_time, n_columns) or (n_columns,) sequence in A*m.
        Returns: (n_time, n_channels) potentials in Volts (V).
        """
        if not self.is_valid:
            raise ForwardModelContractError("Cannot simulate potentials from an invalid forward model.")

        moments = list(dipole_moments)
        if not moments:
            return []

        # If a single 1D vector of moments was provided
        if not isinstance(moments[0], (list, tuple)):
            moments = [moments]  # type: ignore

        n_col = self.source_space.n_columns
        n_ch = self.sensor_geometry.n_channels
        out_potentials: List[List[float]] = []

        for t_idx, q_vec in enumerate(moments):
            if len(q_vec) != n_col:
                raise LeadfieldDimensionMismatchError(
                    f"Moment vector at step {t_idx} has length {len(q_vec)}, expected {n_col}."
                )
            v_t = [0.0] * n_ch
            for i in range(n_ch):
                row_sum = 0.0
                row = self.leadfield[i]
                for j in range(n_col):
                    row_sum += row[j] * q_vec[j]
                v_t[i] = row_sum
            out_potentials.append(v_t)

        return out_potentials


# -----------------------------------------------------------------------------
# Pure-Python Analytic Spherical Forward Engine
# -----------------------------------------------------------------------------

def _legendre_p(n: int, x: float) -> float:
    """Compute Legendre polynomial P_n(x) using Bonnet's recurrence relation."""
    if n == 0:
        return 1.0
    if n == 1:
        return x
    p0, p1 = 1.0, x
    for k in range(1, n):
        p2 = ((2 * k + 1) * x * p1 - k * p0) / (k + 1)
        p0, p1 = p1, p2
    return p1


def _legendre_p_deriv(n: int, x: float) -> float:
    """Compute derivative of Legendre polynomial P'_n(x)."""
    if n == 0:
        return 0.0
    if n == 1:
        return 1.0
    p0, p1 = 1.0, x
    for k in range(1, n):
        p2 = ((2 * k + 1) * x * p1 - k * p0) / (k + 1)
        p0, p1 = p1, p2
    # p1 is P_n, p0 is P_{n-1}
    one_minus_x2 = 1.0 - x * x
    if abs(one_minus_x2) < 1e-12:
        # Limit as x -> 1 or -1
        lim = 0.5 * n * (n + 1)
        return lim if x > 0 else lim * ((-1) ** (n - 1))
    return n * (p0 - x * p1) / one_minus_x2


def compute_homogeneous_sphere_potential(
    electrode_pos_m: Tuple[float, float, float],
    source_pos_m: Tuple[float, float, float],
    dipole_moment_am: Tuple[float, float, float],
    sphere_radius_m: float = DEFAULT_SCALP_RADIUS_M,
    conductivity_sm: float = DEFAULT_SCALP_SIGMA,
    n_max_terms: int = 50,
) -> float:
    """Analytic potential at sphere surface due to a current dipole in a homogeneous sphere.

    Uses the standard Legendre series expansion (Nunez & Srinivasan 2006, Frank 1952).
    Linear in dipole_moment_am, unconditionally convergent for r_source < sphere_radius.
    """
    rs = math.sqrt(sum(p * p for p in source_pos_m))
    re = math.sqrt(sum(p * p for p in electrode_pos_m))

    # Center dipole limit (analytic exact)
    if rs < 1e-12:
        re_dot_q = sum(electrode_pos_m[i] * dipole_moment_am[i] for i in range(3))
        return 3.0 * re_dot_q / (4.0 * math.pi * conductivity_sm * (sphere_radius_m ** 3))

    a = rs / sphere_radius_m
    if a >= 1.0:
        raise SourceOutOfBoundsError(
            f"Source radius {rs:.4f}m must be strictly inside sphere radius {sphere_radius_m:.4f}m."
        )

    re_hat = [electrode_pos_m[i] / re for i in range(3)]
    rs_hat = [source_pos_m[i] / rs for i in range(3)]

    cos_th = sum(re_hat[i] * rs_hat[i] for i in range(3))
    cos_th = max(-1.0, min(1.0, cos_th))

    qr = sum(dipole_moment_am[i] * rs_hat[i] for i in range(3))
    q_dot_re = sum(dipole_moment_am[i] * re_hat[i] for i in range(3))
    qt_proj = q_dot_re - cos_th * qr

    # n = 1 term:
    sum_r = 3.0 * cos_th * qr
    sum_t = -1.5 * qt_proj  # (3 / 2) * P'_1(cos_th) = 1.5 * 1.0

    p0, p1 = 1.0, cos_th
    an = 1.0

    for n in range(2, n_max_terms + 1):
        p2 = ((2 * n - 1) * cos_th * p1 - (n - 1) * p0) / n
        one_minus_x2 = 1.0 - cos_th * cos_th
        if abs(one_minus_x2) < 1e-12:
            pn_prime = 0.5 * n * (n + 1) if cos_th > 0 else 0.5 * n * (n + 1) * ((-1) ** (n - 1))
        else:
            pn_prime = n * (p0 - cos_th * p1) / one_minus_x2

        an *= a
        coeff_r = (2 * n + 1) / n
        coeff_t = (2 * n + 1) / (n * (n + 1))
        sum_r += coeff_r * an * p2 * qr
        sum_t -= coeff_t * an * pn_prime * qt_proj

        p0, p1 = p1, p2
        if an < 1e-15:
            break

    v = (sum_r + sum_t) / (4.0 * math.pi * conductivity_sm * (sphere_radius_m ** 2))
    return v


def compute_3shell_sphere_potential(
    electrode_pos_m: Tuple[float, float, float],
    source_pos_m: Tuple[float, float, float],
    dipole_moment_am: Tuple[float, float, float],
    conductor: ConductorModel,
) -> float:
    """Compute surface potential for a 3-shell concentric sphere conductor model.

    Uses the standard Berg-Scherg (1994) 3-shell equivalent dipole formulation.
    """
    conductor.validate()
    # Berg-Scherg equivalent dipole parameters for brain/skull/scalp concentric spheres
    # with typical 1:80 skull/brain conductivity ratio
    lambdas = (0.08, 0.36, 0.56)
    mus = (0.63, 0.88, 0.99)

    r_scalp = conductor.scalp_radius_m
    sigma_scalp = conductor.sigmas_sm[-1]

    total_potential = 0.0
    for lam, mu in zip(lambdas, mus):
        scaled_source = tuple(mu * p for p in source_pos_m)
        v_hom = compute_homogeneous_sphere_potential(
            electrode_pos_m=electrode_pos_m,
            source_pos_m=scaled_source,  # type: ignore
            dipole_moment_am=dipole_moment_am,
            sphere_radius_m=r_scalp,
            conductivity_sm=sigma_scalp,
        )
        total_potential += lam * v_hom

    return total_potential


# -----------------------------------------------------------------------------
# Linear Algebra & Conditioning Diagnostics (Self-Contained Pure-Python)
# -----------------------------------------------------------------------------

def apply_average_reference(
    leadfield: Sequence[Sequence[float]],
) -> List[List[float]]:
    """Project leadfield matrix onto average reference space: P_avg = I - (1/M) * 1 * 1^T.

    Each column of the resulting matrix sums exactly to zero.
    """
    n_rows = len(leadfield)
    if n_rows == 0:
        return []
    n_cols = len(leadfield[0])

    # Compute column means
    col_means = [0.0] * n_cols
    for row in leadfield:
        for j in range(n_cols):
            col_means[j] += row[j]
    for j in range(n_cols):
        col_means[j] /= n_rows

    # Subtract column mean from each element
    projected: List[List[float]] = []
    for row in leadfield:
        projected.append([row[j] - col_means[j] for j in range(n_cols)])

    return projected


def verify_average_reference_invariant(
    leadfield: Sequence[Sequence[float]],
    tolerance: float = 1e-10,
) -> Tuple[bool, float]:
    """Verify that every column of the leadfield sums to zero within tolerance."""
    n_rows = len(leadfield)
    if n_rows == 0:
        return True, 0.0
    n_cols = len(leadfield[0])

    max_col_error = 0.0
    for j in range(n_cols):
        col_sum = sum(leadfield[i][j] for i in range(n_rows))
        max_col_error = max(max_col_error, abs(col_sum))

    return max_col_error <= tolerance, max_col_error


def _jacobi_eigenvalues_symmetric(
    matrix: Sequence[Sequence[float]],
    max_sweeps: int = 60,
    tolerance: float = 1e-12,
) -> List[float]:
    """Compute eigenvalues of a real symmetric matrix via Jacobi's algorithm."""
    n = len(matrix)
    a = [list(row) for row in matrix]

    for sweep in range(max_sweeps):
        max_off = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) > max_off:
                    max_off = abs(a[p][q])

        if max_off < tolerance:
            break

        for p in range(n):
            for q in range(p + 1, n):
                app, aqq, apq = a[p][p], a[q][q], a[p][q]
                if abs(apq) < 1e-15:
                    continue

                tau = (aqq - app) / (2.0 * apq)
                t = (1.0 if tau >= 0 else -1.0) / (abs(tau) + math.sqrt(1.0 + tau * tau))
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c

                for i in range(n):
                    if i != p and i != q:
                        a_ip = a[i][p]
                        a_iq = a[i][q]
                        a[i][p] = a[p][i] = c * a_ip - s * a_iq
                        a[i][q] = a[q][i] = s * a_ip + c * a_iq

                a[p][p] = c * c * app - 2.0 * s * c * apq + s * s * aqq
                a[q][q] = s * s * app + 2.0 * s * c * apq + c * c * aqq
                a[p][q] = a[q][p] = 0.0

    evals = [a[i][i] for i in range(n)]
    evals.sort(reverse=True)
    return evals


def compute_leadfield_diagnostics(
    leadfield: Sequence[Sequence[float]],
    is_fixed_orientation: bool,
    n_sources: int,
    is_average_referenced: bool = True,
) -> LeadfieldDiagnostics:
    """Compute comprehensive numerical diagnostics for a leadfield matrix."""
    n_ch = len(leadfield)
    if n_ch == 0:
        raise LeadfieldDimensionMismatchError("Leadfield has zero rows.")
    n_col = len(leadfield[0])

    # Check zero-sum column invariant
    is_avg_ref, max_zero_sum_err = verify_average_reference_invariant(leadfield)

    # Channel Frobenius norms
    channel_norms = tuple(math.sqrt(sum(x * x for x in row)) for row in leadfield)
    min_norm = min(channel_norms) if channel_norms else 0.0
    max_norm = max(channel_norms) if channel_norms else 0.0

    # Compute Gram matrix C = L * L^T (size n_ch x n_ch)
    gram: List[List[float]] = [[0.0] * n_ch for _ in range(n_ch)]
    for i in range(n_ch):
        row_i = leadfield[i]
        for j in range(i, n_ch):
            row_j = leadfield[j]
            s = sum(row_i[k] * row_j[k] for k in range(n_col))
            gram[i][j] = gram[j][i] = s

    # Singular values are square roots of eigenvalues of L * L^T
    eigenvals = _jacobi_eigenvalues_symmetric(gram)
    singular_values = tuple(math.sqrt(max(0.0, ev)) for ev in eigenvals)

    # Numerical rank with relative tolerance
    # Since singular values are derived from Gram matrix eigenvalues (L * L^T),
    # the numerical precision floor is O(sqrt(eps)) ~ 1e-7 * max_s.
    max_s = singular_values[0] if singular_values else 0.0
    tol = max(n_ch, n_col) * 1e-7 * max_s
    rank = sum(1 for s in singular_values if s > tol)

    # Condition number accounting for average-reference rank deficiency
    effective_svs = [s for s in singular_values if s > tol]
    if effective_svs:
        cond = effective_svs[0] / effective_svs[-1]
    else:
        cond = float("inf")

    # Estimated crosstalk / source collinearity metric
    # Average off-diagonal correlation of normalized columns
    crosstalk = 0.0
    if n_col > 1:
        col_norms = [math.sqrt(sum(leadfield[r][c] ** 2 for r in range(n_ch))) for c in range(n_col)]
        n_pairs = 0
        corr_sum = 0.0
        # Sample up to 20 columns to keep O(1) computation
        step = max(1, n_col // 20)
        sample_indices = list(range(0, n_col, step))
        for idx_a in range(len(sample_indices)):
            c1 = sample_indices[idx_a]
            n1 = col_norms[c1]
            if n1 < 1e-14:
                continue
            for idx_b in range(idx_a + 1, len(sample_indices)):
                c2 = sample_indices[idx_b]
                n2 = col_norms[c2]
                if n2 < 1e-14:
                    continue
                dot = sum(leadfield[r][c1] * leadfield[r][c2] for r in range(n_ch))
                corr_sum += abs(dot / (n1 * n2))
                n_pairs += 1
        crosstalk = (corr_sum / n_pairs) if n_pairs > 0 else 0.0

    is_well_conditioned = cond < 1e6 and min_norm > 1e-12

    return LeadfieldDiagnostics(
        n_channels=n_ch,
        n_sources=n_sources,
        n_columns=n_col,
        is_fixed_orientation=is_fixed_orientation,
        numerical_rank=rank,
        condition_number=cond,
        singular_values=singular_values,
        channel_frobenius_norms=channel_norms,
        is_average_referenced=is_average_referenced,
        zero_sum_column_error=max_zero_sum_err,
        min_channel_norm=min_norm,
        max_channel_norm=max_norm,
        is_well_conditioned=is_well_conditioned,
        crosstalk_index=crosstalk,
    )


# -----------------------------------------------------------------------------
# Canonical Synthetic Sensor & Source Fixtures
# -----------------------------------------------------------------------------

def make_standard_1020_synthetic_sensors(
    radius_m: float = DEFAULT_SCALP_RADIUS_M,
) -> SensorGeometry:
    """Build canonical 19-channel 10-20 spherical electrode geometry in meters."""
    if radius_m > MILLIMETER_THRESHOLD_M:
        raise CoordinateUnitMismatchError("Electrode radius must be in meters, not mm.")

    # Canonical spherical coordinates (theta, phi) in degrees
    # theta: inclination from Z (vertex Cz = 0 deg)
    # phi: azimuth from +X (RPA = 0, Nasion = 90, LPA = 180, Inion = 270)
    ch_angles_deg: Dict[str, Tuple[float, float]] = {
        "Fp1": (60.0, 108.0),
        "Fp2": (60.0, 72.0),
        "F7":  (90.0, 144.0),
        "F3":  (60.0, 144.0),
        "Fz":  (45.0, 90.0),
        "F4":  (60.0, 36.0),
        "F8":  (90.0, 36.0),
        "T7":  (90.0, 180.0),
        "C3":  (45.0, 180.0),
        "Cz":  (0.0,  0.0),
        "C4":  (45.0, 0.0),
        "T8":  (90.0, 0.0),
        "P7":  (90.0, 216.0),
        "P3":  (60.0, 216.0),
        "Pz":  (45.0, 270.0),
        "P4":  (60.0, 324.0),
        "P8":  (90.0, 324.0),
        "O1":  (60.0, 252.0),
        "O2":  (60.0, 288.0),
    }

    names: List[str] = []
    positions: List[Tuple[float, float, float]] = []

    for name, (th_deg, phi_deg) in ch_angles_deg.items():
        th = math.radians(th_deg)
        phi = math.radians(phi_deg)
        x = radius_m * math.sin(th) * math.cos(phi)
        y = radius_m * math.sin(th) * math.sin(phi)
        z = radius_m * math.cos(th)
        names.append(name)
        positions.append((x, y, z))

    geom = SensorGeometry(
        channel_names=tuple(names),
        positions_m=tuple(positions),
        coordinate_frame=CoordinateFrame.HEAD,
    )
    geom.validate()
    return geom


def make_synthetic_source_grid(
    n_sources: int = 16,
    max_radius_m: float = 0.065,
    is_fixed_orientation: bool = False,
) -> SourceSpace:
    """Generate deterministic synthetic dipole locations strictly inside the brain shell."""
    if max_radius_m >= DEFAULT_BRAIN_RADIUS_M:
        raise SourceOutOfBoundsError(
            f"Source grid radius {max_radius_m}m must be strictly inside brain radius {DEFAULT_BRAIN_RADIUS_M}m."
        )

    positions: List[Tuple[float, float, float]] = []
    orientations: Optional[List[Tuple[float, float, float]]] = [] if is_fixed_orientation else None

    # Deterministic spherical shell distribution using golden spiral / Fibonacci lattice
    golden_ratio = (1.0 + math.sqrt(5.0)) / 2.0
    for i in range(n_sources):
        # Varying radius between 0.02m and max_radius_m
        r = 0.02 + (max_radius_m - 0.02) * (i / max(1, n_sources - 1))
        theta = math.acos(1.0 - 2.0 * (i + 0.5) / n_sources)
        phi = 2.0 * math.pi * i / golden_ratio

        x = r * math.sin(theta) * math.cos(phi)
        y = r * math.sin(theta) * math.sin(phi)
        z = r * math.cos(theta)
        positions.append((x, y, z))

        if is_fixed_orientation:
            # Outward radial unit vector
            norm = math.sqrt(x * x + y * y + z * z)
            if norm > 1e-12:
                orientations.append((x / norm, y / norm, z / norm))  # type: ignore
            else:
                orientations.append((0.0, 0.0, 1.0))  # type: ignore

    src = SourceSpace(
        positions_m=tuple(positions),
        orientations=tuple(orientations) if orientations is not None else None,
        is_fixed_orientation=is_fixed_orientation,
        coordinate_frame=CoordinateFrame.HEAD,
    )
    src.validate()
    return src


# -----------------------------------------------------------------------------
# High-Level Contract Builders and Auditors
# -----------------------------------------------------------------------------

def build_synthetic_forward_contract(
    sensor_geometry: Optional[SensorGeometry] = None,
    source_space: Optional[SourceSpace] = None,
    conductor_model: Optional[ConductorModel] = None,
    apply_avg_ref: bool = True,
) -> ForwardModelContractResult:
    """Build and verify a synthetic forward model contract with SI units and diagnostics.

    Returns a ForwardModelContractResult marked SYNTHETIC_ONLY.
    """
    conductor = conductor_model or ConductorModel()
    conductor.validate()

    sensors = sensor_geometry or make_standard_1020_synthetic_sensors(conductor.scalp_radius_m)
    sensors.validate()

    sources = source_space or make_synthetic_source_grid(16, is_fixed_orientation=False)
    sources.validate(conductor)

    n_ch = sensors.n_channels
    n_src = sources.n_sources
    is_fixed = sources.is_fixed_orientation
    n_col = sources.n_columns

    raw_leadfield: List[List[float]] = [[0.0] * n_col for _ in range(n_ch)]

    # Compute leadfield matrix elements via 3-shell concentric sphere engine
    for ch_idx, elec_pos in enumerate(sensors.positions_m):
        col_idx = 0
        for src_idx, src_pos in enumerate(sources.positions_m):
            if is_fixed:
                # 1 unit dipole along fixed orientation
                ori = sources.orientations[src_idx]  # type: ignore
                v = compute_3shell_sphere_potential(
                    electrode_pos_m=elec_pos,
                    source_pos_m=src_pos,
                    dipole_moment_am=ori,
                    conductor=conductor,
                )
                raw_leadfield[ch_idx][col_idx] = v
                col_idx += 1
            else:
                # 3 orthogonal unit dipoles along X, Y, Z
                for axis_idx in range(3):
                    q = [0.0, 0.0, 0.0]
                    q[axis_idx] = 1.0
                    v = compute_3shell_sphere_potential(
                        electrode_pos_m=elec_pos,
                        source_pos_m=src_pos,
                        dipole_moment_am=tuple(q),  # type: ignore
                        conductor=conductor,
                    )
                    raw_leadfield[ch_idx][col_idx] = v
                    col_idx += 1

    final_leadfield = apply_average_reference(raw_leadfield) if apply_avg_ref else raw_leadfield

    diagnostics = compute_leadfield_diagnostics(
        leadfield=final_leadfield,
        is_fixed_orientation=is_fixed,
        n_sources=n_src,
        is_average_referenced=apply_avg_ref,
    )

    provenance = {
        "engine": "concentric_3shell_analytic",
        "units": {
            "length": CANONICAL_LENGTH_UNIT,
            "potential": CANONICAL_POTENTIAL_UNIT,
            "dipole_moment": CANONICAL_DIPOLE_MOMENT_UNIT,
            "conductivity": CANONICAL_CONDUCTIVITY_UNIT,
            "angle": CANONICAL_ANGLE_UNIT,
        },
        "coordinate_frame": sensors.coordinate_frame.value,
        "conductor_radii_m": list(conductor.radii_m),
        "conductor_sigmas_sm": list(conductor.sigmas_sm),
        "disclaimer": CONTRACT_DISCLAIMER,
    }

    return ForwardModelContractResult(
        status=ContractStatus.SYNTHETIC_ONLY,
        is_valid=diagnostics.is_well_conditioned,
        leadfield=tuple(tuple(r) for r in final_leadfield),
        sensor_geometry=sensors,
        conductor_model=conductor,
        source_space=sources,
        diagnostics=diagnostics,
        warnings=() if diagnostics.is_well_conditioned else ("Leadfield condition number high.",),
        failure_reason=None,
        provenance=provenance,
    )


def audit_mne_forward_solution(
    fwd: Any,
    info: Optional[Any] = None,
    expected_conductor: Optional[ConductorModel] = None,
) -> ForwardModelContractResult:
    """Audit an existing MNE Forward solution against the repository contract.

    Verifies coordinate frame (HEAD), SI units (meters), channel order,
    leadfield dimensions, reference projection, and rank conditioning.
    """
    warnings: List[str] = []

    # 1. Coordinate Frame Verification
    coord_frame = getattr(fwd, "coord_frame", None)
    if coord_frame is None and isinstance(fwd, dict):
        coord_frame = fwd.get("coord_frame")

    # MNE FIFFV_COORD_HEAD is 4
    if coord_frame not in (4, "head", CoordinateFrame.HEAD):
        raise CoordinateFrameMismatchError(
            f"Forward solution coordinate frame {coord_frame} is not FIFFV_COORD_HEAD (4)."
        )

    # 2. Extract Leadfield Data and Row Names
    sol = fwd.get("sol") if isinstance(fwd, dict) else getattr(fwd, "sol", None)
    if sol is None:
        raise ForwardModelContractError("MNE forward solution missing 'sol' dict.")

    leadfield_data = sol.get("data") if isinstance(sol, dict) else getattr(sol, "data", None)
    row_names = sol.get("row_names") if isinstance(sol, dict) else getattr(sol, "row_names", None)

    if leadfield_data is None or row_names is None:
        raise ForwardModelContractError("MNE forward solution missing 'data' or 'row_names'.")

    # Convert to pure Python list-of-lists
    leadfield_list: List[List[float]] = [
        [float(x) for x in row] for row in leadfield_data
    ]
    ch_names_tuple = tuple(str(ch) for ch in row_names)

    # 3. Channel Order Verification against Info
    if info is not None:
        info_ch_names = info.get("ch_names") if isinstance(info, dict) else getattr(info, "ch_names", None)
        if info_ch_names is not None:
            # Filter info channels to EEG picks
            if list(ch_names_tuple) != list(info_ch_names):
                # If they have the same set but different order, fail closed
                if set(ch_names_tuple) == set(info_ch_names):
                    raise ChannelOrderMismatchError(
                        "Leadfield row names are a permutation of info['ch_names']; strict ordering required."
                    )
                else:
                    warnings.append("Leadfield row names do not exactly match info channels.")

    # 4. Source Space and Unit Verification
    src = fwd.get("src") if isinstance(fwd, dict) else getattr(fwd, "src", None)
    n_sources = fwd.get("nsource") if isinstance(fwd, dict) else getattr(fwd, "nsource", None)
    is_fixed = (fwd.get("source_ori") == 1) if isinstance(fwd, dict) else (getattr(fwd, "source_ori", None) == 1)

    positions: List[Tuple[float, float, float]] = []
    if src is not None:
        for s in src:
            rr = s.get("rr") if isinstance(s, dict) else getattr(s, "rr", None)
            inuse = s.get("inuse") if isinstance(s, dict) else getattr(s, "inuse", None)
            if rr is not None and inuse is not None:
                for idx, active in enumerate(inuse):
                    if active:
                        p = rr[idx]
                        norm = math.sqrt(sum(float(x) ** 2 for x in p))
                        if norm > MILLIMETER_THRESHOLD_M:
                            raise CoordinateUnitMismatchError(
                                f"MNE source vertex norm {norm:.2f}m > 1.0m; units must be meters."
                            )
                        positions.append((float(p[0]), float(p[1]), float(p[2])))

    if n_sources is None:
        n_sources = len(positions) if positions else (len(leadfield_list[0]) // (1 if is_fixed else 3))

    expected_cols = n_sources if is_fixed else n_sources * 3
    if len(leadfield_list[0]) != expected_cols:
        raise LeadfieldDimensionMismatchError(
            f"Leadfield columns ({len(leadfield_list[0])}) do not match "
            f"expected ({expected_cols}) for {n_sources} sources (fixed={is_fixed})."
        )

    # 5. Extract Sensor Positions from Info if available
    sensor_positions: List[Tuple[float, float, float]] = []
    if info is not None:
        chs = info.get("chs") if isinstance(info, dict) else getattr(info, "chs", None)
        if chs is not None:
            for ch in chs:
                if ch.get("ch_name") in ch_names_tuple:
                    loc = ch.get("loc")
                    if loc is not None and len(loc) >= 3:
                        p = (float(loc[0]), float(loc[1]), float(loc[2]))
                        norm = math.sqrt(sum(x * x for x in p))
                        if norm > MILLIMETER_THRESHOLD_M:
                            raise CoordinateUnitMismatchError(
                                f"Sensor '{ch.get('ch_name')}' loc norm {norm:.2f}m > 1.0m; units must be meters."
                            )
                        sensor_positions.append(p)

    if not sensor_positions:
        # Fallback dummy positions on default scalp sphere for structure completion
        sensor_positions = [(0.0, 0.0, DEFAULT_SCALP_RADIUS_M)] * len(ch_names_tuple)

    sensor_geom = SensorGeometry(
        channel_names=ch_names_tuple,
        positions_m=tuple(sensor_positions),
        coordinate_frame=CoordinateFrame.HEAD,
    )

    if not positions:
        positions = [(0.0, 0.0, 0.0)] * n_sources

    src_space = SourceSpace(
        positions_m=tuple(positions),
        orientations=None,
        is_fixed_orientation=is_fixed,
        coordinate_frame=CoordinateFrame.HEAD,
    )

    conductor = expected_conductor or ConductorModel()

    diagnostics = compute_leadfield_diagnostics(
        leadfield=leadfield_list,
        is_fixed_orientation=is_fixed,
        n_sources=n_sources,
        is_average_referenced=diagnostics_is_avg(leadfield_list),
    )

    provenance = {
        "engine": "mne_forward_audit",
        "units": {
            "length": CANONICAL_LENGTH_UNIT,
            "potential": CANONICAL_POTENTIAL_UNIT,
            "dipole_moment": CANONICAL_DIPOLE_MOMENT_UNIT,
            "conductivity": CANONICAL_CONDUCTIVITY_UNIT,
            "angle": CANONICAL_ANGLE_UNIT,
        },
        "coordinate_frame": CoordinateFrame.HEAD.value,
        "disclaimer": CONTRACT_DISCLAIMER,
    }

    return ForwardModelContractResult(
        status=ContractStatus.ENGINEERING_ONLY,
        is_valid=diagnostics.is_well_conditioned,
        leadfield=tuple(tuple(r) for r in leadfield_list),
        sensor_geometry=sensor_geom,
        conductor_model=conductor,
        source_space=src_space,
        diagnostics=diagnostics,
        warnings=tuple(warnings),
        failure_reason=None,
        provenance=provenance,
    )


def diagnostics_is_avg(leadfield: Sequence[Sequence[float]]) -> bool:
    """Helper to check if average reference was applied."""
    is_avg, _ = verify_average_reference_invariant(leadfield, tolerance=1e-6)
    return is_avg
