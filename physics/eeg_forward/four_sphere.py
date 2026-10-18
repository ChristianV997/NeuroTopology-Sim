"""Experimental quasi-static four-shell (four-sphere) EEG forward model.

STATUS: HOLD / SYNTHETIC_ONLY. Engineering model of a dipole in an idealised,
concentric, isotropic, piecewise-homogeneous head. It is not individual anatomy,
not validated against recordings, and supports no biological or clinical claim.

Geometry and conventions
------------------------
- Concentric spheres centred on the origin. Shells, innermost first:
  brain (0 <= r < r1, conductivity sigma1), CSF (r1 < r < r2, sigma2),
  skull (r2 < r < r3, sigma3), scalp (r3 < r < r4, sigma4). ``radii_m`` is
  (r1, r2, r3, r4) in metres, strictly increasing. ``conductivities_sm`` is
  (sigma1, sigma2, sigma3, sigma4) in S/m, in the same shell order.
- Sensors lie on the outer surface r = r4. Sources lie in the brain, depth
  d = |source_position| in [0, r1). The source-direction unit vector is
  e_s = source_position / d. For d = 0 the direction is arbitrary and only the
  degree-1 term survives.
- Dipole moment q in A*m, global Cartesian frame. Radial component
  q_r = q . e_s; tangential component of q with respect to the source direction
  is q_t = q - q_r e_s.
- Potential V in volts. Positive when the observer lies on the side the dipole
  points towards (V_inf = q.(r - r_s) / (4 pi sigma1 |r - r_s|^3)).
- Average reference: the degree-0 term is zero, so the mean potential over the
  scalp sphere is zero. No infinity reference is used.
- Normalisation is independent of length units: transfer ratios depend only on
  radius ratios and conductivity ratios, so the output scales only with
  q / (sigma1 r4^2).

Model (derived from the Laplace equation per degree, see
docs/physics/four_sphere_forward_model.md)
-------------------------------------------
Degree l = 1..L. Let e be the sensor unit vector, mu = e_s . e, rho_k = r_k / r4,
t = d / r4. Radial and tangential components of the dipole are
q_r = q . e_s and q_t = q - q_r e_s.

Free-space dipole, degree l (checked against q.(r - r_s) / (4 pi sigma1 |r - r_s|^3)):
    V_inf(l) = (1 / (4 pi sigma1 r4^2)) t^(l-1) [ l q_r P_l(mu) + P_l'(mu) (q_t . e) ]

Tangential term, explicitly. Let e_perp = e - mu e_s be the sensor direction with
its source-axis component removed, so |e_perp| = sin(theta) and q_t . e = q_t . e_perp.
With the Condon-Shortley phase P_l^1(mu) = -sin(theta) P_l'(mu) and the unit tangent
rho_hat = e_perp / sin(theta):
    P_l'(mu) (q_t . e) = -P_l^1(mu) (q_t . rho_hat).
The code evaluates P_l'(mu) (q . e - mu q_r) and never divides by sin(theta). At the
poles e_perp = 0, so the tangential term is zero. P_l'(+-1) = (+-1)^(l+1) l(l+1)/2
is finite, so the value is finite and symmetric at both poles.

Layered solution: each degree is multiplied by one transfer ratio,
    V(sensor) = sum_l T_l V_inf(l),   T_l = V_scalp,l / V_inf,l(r4),
which does not depend on orientation, because both orientations share the radial
functions r^l and r^-(l+1) in the brain. The homogeneous limit gives T_l = (2l+1)/l.

T_l is computed by propagating the state (Phi, sigma Phi') from the scalp
surface inwards through the three outer shells with closed-form transfer
matrices M = Psi(r_a) Psi(r_b)^-1, where Psi(r) = [[r^l, r^-(l+1)],
[sigma l r^(l-1), -sigma (l+1) r^-(l+2)]]. The brain match gives
T_l = 1 / beta_1, where beta_1 is the coefficient of r^-(l+1) in the brain.
The off-diagonal entries m12 and m21 are differences of two powers, so their
absolute rounding error is near machine epsilon times the matrix scale, and their
relative error grows for very thin shells. Measured against the independent 7x7
solve in the tests, T_l agrees to 5e-15 for shells as thin as 1e-9 of the radius.
The interface residuals do not isolate this effect and are not the evidence for it.

Attribution
-----------
Næss et al. (2017), "Corrected Four-Sphere Head Model for EEG Signals",
Frontiers in Human Neuroscience 11:490, doi:10.3389/fnhum.2017.00490, is the
literature model this module targets. In this session the publisher host was refused
by network policy (HTTP 403 at CONNECT), so the paper could not be read. The Table 1
values and the paper's series are therefore unverified. The equations here were derived
independently and checked numerically, not transcribed from the paper. The licence
(CC-BY-4.0) is as stated in the task brief and was not verified.
The Neuroinflab four-sphere code (GPL-3.0 per its README) was not read, copied,
or executed. Licensing is flagged for human review, not legal advice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

MAX_DEGREE = 512
DEFAULT_MAX_DEGREE = 256
DEFAULT_RESIDUAL_TOL = 1e-9
DEFAULT_TAIL_TOL = 1e-10
MAX_SCALE_RADIUS_M = 1.0
CONDUCTIVITY_BOUNDS_SM = (1e-4, 10.0)
_SURFACE_REL_TOL = 1e-9


class FourSphereError(ValueError):
    """Base class for four-sphere model errors."""


class FourSphereInputError(FourSphereError):
    """Geometry, source, sensor, or option outside the model's domain."""


class FourSphereQualityError(FourSphereError):
    """Numerical quality check failed; results are withheld rather than regularised."""


@dataclass(frozen=True)
class FourSphereGeometry:
    radii_m: tuple[float, float, float, float]
    conductivities_sm: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        radii = _finite_tuple(self.radii_m, 4, "radii_m")
        sigmas = _finite_tuple(self.conductivities_sm, 4, "conductivities_sm")
        if any(r <= 0.0 for r in radii):
            raise FourSphereInputError("radii_m must be positive")
        if not all(radii[i] < radii[i + 1] for i in range(3)):
            raise FourSphereInputError("radii_m must be strictly increasing (brain, CSF, skull, scalp)")
        if radii[3] > MAX_SCALE_RADIUS_M:
            raise FourSphereInputError("scalp radius above 1 m: check units (metres expected)")
        lo, hi = CONDUCTIVITY_BOUNDS_SM
        if any(not (lo <= s <= hi) for s in sigmas):
            raise FourSphereInputError(
                f"conductivities_sm must lie in [{lo}, {hi}] S/m; check units"
            )
        object.__setattr__(self, "radii_m", radii)
        object.__setattr__(self, "conductivities_sm", sigmas)


@dataclass(frozen=True)
class FourSphereResult:
    potentials_v: np.ndarray
    transfer_ratios: np.ndarray
    max_degree: int
    diagnostics: dict[str, float]


NAESS2017_TABLE1_K_VALUES = (20, 40, 80)


def naess2017_table1_geometry(skull_ratio_k: int) -> FourSphereGeometry:
    """Geometry from the task-specified Næss et al. (2017) Table 1 parameterisation.

    Radii (0.079, 0.080, 0.085, 0.090) m. Conductivities (0.33, 1.65, 0.33/K, 0.33) S/m
    with K in {20, 40, 80}. These values are as specified in the task brief. They were
    not checked against the paper, because the publisher host was refused by network
    policy in the session that wrote this function.
    """
    if isinstance(skull_ratio_k, bool) or skull_ratio_k not in NAESS2017_TABLE1_K_VALUES:
        raise FourSphereInputError(f"skull_ratio_k must be one of {NAESS2017_TABLE1_K_VALUES}")
    return FourSphereGeometry(
        radii_m=(0.079, 0.080, 0.085, 0.090),
        conductivities_sm=(0.33, 1.65, 0.33 / skull_ratio_k, 0.33),
    )


def _finite_tuple(values: Sequence[object], length: int, name: str) -> tuple[float, ...]:
    try:
        items = tuple(float(v) for v in values)
    except (TypeError, ValueError) as exc:
        raise FourSphereInputError(f"{name} must be a sequence of {length} real numbers") from exc
    if len(items) != length:
        raise FourSphereInputError(f"{name} must have exactly {length} entries")
    if not all(math.isfinite(v) for v in items):
        raise FourSphereInputError(f"{name} must be finite")
    return items


def _degree(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise FourSphereInputError("max_degree must be an integer")
    degree = int(value)
    if not 1 <= degree <= MAX_DEGREE:
        raise FourSphereInputError(f"max_degree must be in [1, {MAX_DEGREE}]")
    return degree


def _vector3(values: Sequence[object], name: str) -> np.ndarray:
    try:
        arr = np.asarray([float(v) for v in values], dtype=float)
    except (TypeError, ValueError) as exc:
        raise FourSphereInputError(f"{name} must be a 3-vector of real numbers") from exc
    if arr.shape != (3,) or not np.all(np.isfinite(arr)):
        raise FourSphereInputError(f"{name} must be a finite 3-vector")
    return arr


def _sensors(sensor_positions_m: object, surface_radius: float) -> np.ndarray:
    try:
        arr = np.asarray(sensor_positions_m, dtype=float)
    except (TypeError, ValueError) as exc:
        raise FourSphereInputError("sensor_positions_m must be an N x 3 array of reals") from exc
    if arr.ndim != 2 or arr.shape[1] != 3 or arr.shape[0] < 1:
        raise FourSphereInputError("sensor_positions_m must have shape (N, 3) with N >= 1")
    if not np.all(np.isfinite(arr)):
        raise FourSphereInputError("sensor_positions_m must be finite")
    norms = np.linalg.norm(arr, axis=1)
    tol = max(1e-12, surface_radius * _SURFACE_REL_TOL)
    if np.any(np.abs(norms - surface_radius) > tol):
        raise FourSphereInputError("every sensor must lie on the scalp sphere r = radii_m[3]")
    return arr


def legendre_and_derivative(max_degree: int, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return P_l(mu) and dP_l/dmu for l = 0..max_degree, shape (max_degree+1, N).

    Uses the three-term recurrence and P_{l+1}' = P_{l-1}' + (2l+1) P_l, which
    stay finite at mu = +-1 (no division by 1 - mu^2).
    """
    mu = np.asarray(mu, dtype=float)
    P = np.zeros((max_degree + 1,) + mu.shape)
    dP = np.zeros_like(P)
    P[0] = 1.0
    if max_degree >= 1:
        P[1] = mu
        dP[1] = 1.0
    for n in range(1, max_degree):
        P[n + 1] = ((2 * n + 1) * mu * P[n] - n * P[n - 1]) / (n + 1)
        dP[n + 1] = dP[n - 1] + (2 * n + 1) * P[n]
    return P, dP


def _psi(degree: int, rho: float, sigma: float) -> np.ndarray:
    l = degree
    return np.array([
        [rho**l, rho ** (-(l + 1))],
        [sigma * l * rho ** (l - 1), -sigma * (l + 1) * rho ** (-(l + 2))],
    ])


def _psi_inverse(degree: int, rho: float, sigma: float) -> np.ndarray:
    """Closed-form inverse of _psi, using only products of powers (no solve)."""
    l = degree
    det = -sigma * (2 * l + 1) / rho**2
    return (1.0 / det) * np.array([
        [-sigma * (l + 1) * rho ** (-(l + 2)), -rho ** (-(l + 1))],
        [-sigma * l * rho ** (l - 1), rho**l],
    ])


def shell_transfer(degree: int, rho_inner: float, rho_outer: float, sigma: float) -> np.ndarray:
    """Matrix M with state(rho_inner) = M state(rho_outer) for one homogeneous shell.

    State = (Phi, sigma dPhi/dr). Closed form of Psi(inner) Psi(outer)^-1 with
    x = rho_inner / rho_outer <= 1.
    """
    l = degree
    x = rho_inner / rho_outer
    xl = x**l
    xm = x ** (-(l + 1))
    xm2 = x ** (-(l + 2))
    xl1 = x ** (l - 1)
    m11 = ((l + 1) * xl + l * xm) / (2 * l + 1)
    m12 = -rho_outer * (xm - xl) / (sigma * (2 * l + 1))
    m21 = -sigma * l * (l + 1) * (xm2 - xl1) / (rho_outer * (2 * l + 1))
    m22 = (l * xl1 + (l + 1) * xm2) / (2 * l + 1)
    return np.array([[m11, m12], [m21, m22]])


def _normalised(geometry: FourSphereGeometry) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    r4 = geometry.radii_m[3]
    rho = tuple(r / r4 for r in geometry.radii_m)
    return rho, geometry.conductivities_sm


def _propagate(degree: int, rho: tuple[float, float, float, float], sigmas: tuple[float, float, float, float]):
    """States at each interface, scalp-to-brain, with scalp state (1, 0)."""
    rho1, rho2, rho3, rho4 = rho
    s1_, s2_, s3_, s4_ = sigmas
    s4 = np.array([1.0, 0.0])
    s3 = shell_transfer(degree, rho3, rho4, s4_) @ s4
    s2 = shell_transfer(degree, rho2, rho3, s3_) @ s3
    s1 = shell_transfer(degree, rho1, rho2, s2_) @ s2
    return s4, s3, s2, s1


def _transfer_and_diagnostics(degree: int, geometry: FourSphereGeometry) -> tuple[float, dict[str, float]]:
    rho, sigmas = _normalised(geometry)
    rho1, rho2, rho3, rho4 = rho
    s1_, s2_, s3_, s4_ = sigmas
    s4, s3, s2, s1 = _propagate(degree, rho, sigmas)

    # Brain: Phi_1 = alpha r^l + beta r^-(l+1) with (Phi, sigma1 Phi') = s1 at rho1.
    coeff_brain = _psi_inverse(degree, rho1, s1_) @ s1
    beta1 = float(coeff_brain[1])
    if not math.isfinite(beta1) or beta1 == 0.0:
        raise FourSphereQualityError(f"degree {degree}: brain coefficient is not finite and non-zero")
    transfer = 1.0 / beta1

    # Interface residuals: evaluate each shell's own Euler representation at the
    # interface and compare with the state propagated into that interface.
    # Outer boundary: shell-4 representation of (1, 0) at rho4.
    c4 = _psi_inverse(degree, rho4, s4_) @ s4
    flux_outer = s4_ * (c4[0] * degree * rho4 ** (degree - 1) - c4[1] * (degree + 1) * rho4 ** (-(degree + 2)))
    scale_outer = s4_ * (abs(c4[0]) * degree + abs(c4[1]) * (degree + 1)) + 1e-300

    residuals_pot: list[float] = []
    residuals_flux: list[float] = []
    for (rho_k, state_k, c_above, rho_above, sig_above, state_above) in (
        (rho3, s3, c4, rho4, s4_, s4),
        (rho2, s2, _psi_inverse(degree, rho3, s3_) @ s3, rho3, s3_, s3),
        (rho1, s1, _psi_inverse(degree, rho2, s2_) @ s2, rho2, s2_, s2),
    ):
        above_at_interface = _psi(degree, rho_k, sig_above) @ c_above
        diff = above_at_interface - state_k
        denom = np.abs(above_at_interface) + np.abs(state_k) + 1e-300
        residuals_pot.append(abs(diff[0]) / denom[0])
        residuals_flux.append(abs(diff[1]) / denom[1])
    # The brain side is matched exactly by the closed-form beta1, so check it directly.
    brain_check = _psi(degree, rho1, s1_) @ coeff_brain - s1
    brain_denom = np.abs(s1) + 1e-300
    residuals_pot.append(abs(brain_check[0]) / brain_denom[0])
    residuals_flux.append(abs(brain_check[1]) / brain_denom[1])

    diagnostics = {
        "interface_potential_residual": float(max(residuals_pot)),
        "interface_current_residual": float(max(residuals_flux)),
        "scalp_zero_current_residual": float(abs(flux_outer) / scale_outer),
        "shell_condition_number": float(max(np.linalg.cond(_psi(degree, r, sg)) for r, sg in ((rho1, s1_), (rho2, s2_), (rho3, s3_), (rho4, s4_)))),
    }
    return transfer, diagnostics


_GATED_RESIDUALS = ("interface_potential_residual", "interface_current_residual", "scalp_zero_current_residual")


def _checked_degree(degree: int, geometry: FourSphereGeometry) -> tuple[float, dict[str, float]]:
    """Transfer ratio and diagnostics for one degree, failing closed on overflow or NaN.

    NaN compares False against any tolerance, so non-finite values are rejected here
    rather than left to threshold checks.
    """
    message = (
        f"degree {degree}: non-finite transfer ratio or residual "
        "(powers overflow or lose precision at this radius ratio; reduce max_degree)"
    )
    # Overflow is caught by the finiteness check below, so the NumPy warning is suppressed.
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        try:
            transfer, diag = _transfer_and_diagnostics(degree, geometry)
        except OverflowError as exc:
            raise FourSphereQualityError(message) from exc
    if not math.isfinite(transfer) or not all(math.isfinite(diag[key]) for key in _GATED_RESIDUALS):
        raise FourSphereQualityError(message)
    return transfer, diag


def transfer_ratios(geometry: FourSphereGeometry, max_degree: int) -> np.ndarray:
    """Dimensionless transfer ratios T_l for l = 1..max_degree (scale invariant)."""
    degree_max = _degree(max_degree)
    return np.array([_checked_degree(l, geometry)[0] for l in range(1, degree_max + 1)])


def _truncation_tail_estimate(envelopes: np.ndarray, potentials: np.ndarray) -> float:
    """Estimated size of the dropped tail, relative to the largest sensor potential.

    The envelope of the dropped degrees is extrapolated geometrically from its last
    consecutive ratio r: tail ~ env_L r / (1 - r). This is an estimate, not a bound.
    It assumes the ratio stays at r beyond L. For layered geometries that is not
    proven, and a rigorous bound would also need |T_l| bounded for all l. Unestimable
    cases (r >= 1, too few degrees, or zero signal with a non-zero envelope) return inf.
    """
    last = float(envelopes[-1])
    if last == 0.0:
        return 0.0
    if len(envelopes) < 2 or envelopes[-2] == 0.0:
        return math.inf
    r = last / float(envelopes[-2])
    if not r < 1.0:
        return math.inf
    tail_abs = last * r / (1.0 - r)
    scale = float(np.max(np.abs(potentials)))
    return tail_abs / scale if scale > 0.0 else math.inf


def forward_potentials(
    geometry: FourSphereGeometry,
    source_position_m: Sequence[object],
    dipole_moment_am: Sequence[object],
    sensor_positions_m: object,
    *,
    max_degree: int = DEFAULT_MAX_DEGREE,
    residual_tol: float = DEFAULT_RESIDUAL_TOL,
    tail_tol: float = DEFAULT_TAIL_TOL,
) -> FourSphereResult:
    """Scalp potentials (volts) for one dipole, with quality diagnostics.

    Raises FourSphereInputError for invalid inputs and FourSphereQualityError if
    the boundary residuals or truncation tail exceed the given tolerances.
    """
    L = _degree(max_degree)
    if not (math.isfinite(residual_tol) and residual_tol > 0.0):
        raise FourSphereInputError("residual_tol must be finite and positive")
    if not (math.isfinite(tail_tol) and tail_tol > 0.0):
        raise FourSphereInputError("tail_tol must be finite and positive")
    source = _vector3(source_position_m, "source_position_m")
    moment = _vector3(dipole_moment_am, "dipole_moment_am")
    r1, r4 = geometry.radii_m[0], geometry.radii_m[3]
    sensors = _sensors(sensor_positions_m, r4)
    depth = float(np.linalg.norm(source))
    if not depth < r1:
        raise FourSphereInputError("source must lie strictly inside the brain shell (|source| < radii_m[0])")

    axis = source / depth if depth > 0.0 else np.array([0.0, 0.0, 1.0])
    q_r = float(moment @ axis)
    sensor_dirs = sensors / np.linalg.norm(sensors, axis=1, keepdims=True)
    mu = np.clip(sensor_dirs @ axis, -1.0, 1.0)
    q_dot_e = sensor_dirs @ moment
    q_t_dot_e = q_dot_e - q_r * mu

    transfer = np.zeros(L)
    diagnostics: dict[str, float] = {
        "interface_potential_residual": 0.0,
        "interface_current_residual": 0.0,
        "scalp_zero_current_residual": 0.0,
        "shell_condition_number": 0.0,
    }
    for l in range(1, L + 1):
        T, diag = _checked_degree(l, geometry)
        transfer[l - 1] = T
        for key in diagnostics:
            diagnostics[key] = max(diagnostics[key], diag[key])
    if diagnostics["interface_potential_residual"] > residual_tol or diagnostics["interface_current_residual"] > residual_tol \
            or diagnostics["scalp_zero_current_residual"] > residual_tol:
        raise FourSphereQualityError(f"boundary residuals exceed {residual_tol}: {diagnostics}")

    P, dP = legendre_and_derivative(L, mu)
    ratio = depth / r4
    prefactor = 1.0 / (4.0 * math.pi * geometry.conductivities_sm[0] * r4**2)
    potentials = np.zeros(sensors.shape[0])
    envelopes = np.zeros(L)
    q_t_norm = float(np.linalg.norm(moment - q_r * axis))
    for l in range(1, L + 1):
        coeff = transfer[l - 1] * prefactor * ratio ** (l - 1)
        potentials += coeff * (l * q_r * P[l] + dP[l] * q_t_dot_e)
        # |P_l| <= 1 and |P_l'| <= l(l+1)/2 on [-1, 1], and |q_t . e| <= |q_t|, so this
        # envelope bounds the degree-l term at every sensor. It does not depend on where
        # P_l vanishes, so a node at one sensor or degree cannot end the sum early.
        envelopes[l - 1] = abs(coeff) * (l * abs(q_r) + l * (l + 1) / 2.0 * q_t_norm)
    if not (np.all(np.isfinite(potentials)) and np.all(np.isfinite(envelopes))):
        raise FourSphereQualityError("non-finite potential")
    tail_rel = _truncation_tail_estimate(envelopes, potentials)
    diagnostics["tail_relative"] = tail_rel
    if not tail_rel <= tail_tol:
        raise FourSphereQualityError(
            f"truncation tail estimate {tail_rel:.3e} exceeds tail_tol {tail_tol}; increase max_degree (now {L})"
        )
    diagnostics["max_degree"] = float(L)
    return FourSphereResult(
        potentials_v=potentials,
        transfer_ratios=transfer,
        max_degree=L,
        diagnostics=diagnostics,
    )
