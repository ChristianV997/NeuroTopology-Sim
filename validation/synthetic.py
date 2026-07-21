from __future__ import annotations
import numpy as np
from core.topology import compute_Qz

def single_vortex(N=64):
    """Create a synthetic single-vortex complex field.

    The sign is chosen so the current plaquette orientation convention yields
    positive Q for this canonical test field.
    """
    x = np.linspace(-1, 1, N)
    y = np.linspace(-1, 1, N)
    X, Y = np.meshgrid(x, y)
    theta = -np.arctan2(Y, X)
    psi = np.exp(1j * theta)
    return np.repeat(psi[:, :, None], N, axis=2)

def double_vortex(N=64):
    """Create a synthetic double-vortex complex field with net Q≈2."""
    x = np.linspace(-1, 1, N)
    y = np.linspace(-1, 1, N)
    X, Y = np.meshgrid(x, y)
    theta1 = -np.arctan2(Y - 0.25, X - 0.25)
    theta2 = -np.arctan2(Y + 0.25, X + 0.25)
    psi = np.exp(1j * (theta1 + theta2))
    return np.repeat(psi[:, :, None], N, axis=2)

def perturbed_vortex(N=64, noise_amplitude=0.0, seed=0):
    """Single-vortex field with additive complex Gaussian noise, then
    renormalized to unit modulus per-pixel (phase is what carries winding
    charge, so noise is applied to phase-bearing amplitude directly rather
    than left unnormalized). `noise_amplitude` is the noise standard
    deviation relative to the field's unit amplitude: 0.0 reproduces
    `single_vortex` exactly; increasing it progressively degrades the
    measured winding charge, giving a continuous knob for parameter-search
    experiments (see `sim/active_inference.py`)."""
    psi = single_vortex(N)
    if noise_amplitude <= 0.0:
        return psi
    rng = np.random.default_rng(seed)
    noise = noise_amplitude * (
        rng.standard_normal(psi.shape) + 1j * rng.standard_normal(psi.shape)
    )
    perturbed = psi + noise
    magnitude = np.abs(perturbed)
    magnitude[magnitude < 1e-12] = 1e-12
    return perturbed / magnitude


def validate_vortex_charges(charge_tolerance: float = 0.25) -> dict:
    """Validate expected synthetic charges for single and double vortex fields."""
    q1, _ = compute_Qz(single_vortex())
    q2, _ = compute_Qz(double_vortex())
    q1_mean = float(np.mean(q1))
    q2_mean = float(np.mean(q2))
    return {
        "single_vortex_Q_mean": q1_mean,
        "double_vortex_Q_mean": q2_mean,
        "single_vortex_pass": bool(abs(q1_mean - 1.0) <= charge_tolerance),
        "double_vortex_pass": bool(abs(q2_mean - 2.0) <= charge_tolerance),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dynamical ground-truth generators.
#
# `single_vortex`/`double_vortex` above are STATIC: the winding charge is
# hand-written directly into the phase (theta = -arctan2(Y, X)), tiled
# identically across z, with |psi| = 1 everywhere by construction. They confirm
# `compute_Qz` recovers a known charge on one frame, but give
# `analysis/qzt.py`, `analysis/events.py`, and `tracking/worldlines.py` nothing
# to validate against -- there has never been a synthetic field whose defects
# actually move, are created, or annihilate over time. They also cannot exercise
# `core.defects.detect_defects`, whose `amp_patch < amp_threshold` core-detection
# criterion never fires on a field of constant unit amplitude.
#
# The two generators below are genuine dynamical systems (an oscillator lattice
# and a PDE) whose *outputs*, not hand-written formulas, carry the winding
# charge -- giving both a tunable, dial-a-defect-density ground truth and,
# for the CGL field specifically, real amplitude dips at vortex cores so
# `detect_defects` has something to find.
# ─────────────────────────────────────────────────────────────────────────────


def cgl_step(psi: np.ndarray, c1: float = 0.5, c2: float = -0.5, dt: float = 0.05) -> np.ndarray:
    """One explicit-Euler step of the complex Ginzburg-Landau equation on a
    periodic 2D grid: dA/dt = A + (1+i*c1)*lap(A) - (1+i*c2)*|A|^2*A.

    CGL is the canonical amplitude equation for oscillatory media (Aranson &
    Kramer 2002). Unlike a plain diffusion step (a heat equation, which only
    smooths any field toward uniformity and cannot sustain topological
    structure), CGL spontaneously nucleates spiral-wave phase singularities
    whose cores go to |A| -> 0 -- a real, physically motivated vortex, not a
    hand-written one. ``(c1, c2) = (0.5, -0.5)`` (this module's default) sits in
    the Benjamin-Feir-stable regime (``1 + c1*c2 > 0``): a field seeded with
    small-amplitude noise nucleates many defects immediately, then coarsens as
    pairs annihilate over time -- a bounded, well-behaved trajectory (not
    runaway spatiotemporal chaos) suitable as a validation oracle.
    """
    lap = (
        np.roll(psi, 1, 0) + np.roll(psi, -1, 0)
        + np.roll(psi, 1, 1) + np.roll(psi, -1, 1) - 4 * psi
    )
    return psi + dt * (psi + (1 + 1j * c1) * lap - (1 + 1j * c2) * np.abs(psi) ** 2 * psi)


def cgl_defect_field(
    N: int = 64,
    n_steps: int = 100,
    c1: float = 0.5,
    c2: float = -0.5,
    dt: float = 0.05,
    seed: int = 0,
    amp0: float = 0.1,
    return_trajectory: bool = False,
):
    """Integrate CGL from small-amplitude noise; return the (N, N) complex field
    (or, if ``return_trajectory``, the full ``(n_steps+1, N, N)`` history).

    Winding charge is not planted -- it emerges from the dynamics, so it is
    known only in the weaker sense of "read off `compute_Qz` on the output",
    not prescribed in advance. What IS known and controllable: defect *density*
    decreases roughly monotonically with `n_steps` (many defects at small
    n_steps, few after long-time coarsening -- see this module's tests), so
    sweeping `n_steps` gives a tunable, reproducible (fixed `seed`) defect-count
    dial, and `detect_defects` genuinely fires on this field's amplitude dips.
    """
    if N < 4:
        raise ValueError(f"N must be >= 4, got {N}")
    if n_steps < 0:
        raise ValueError(f"n_steps must be >= 0, got {n_steps}")
    rng = np.random.default_rng(seed)
    psi = amp0 * (rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N)))

    traj = [psi.copy()] if return_trajectory else None
    for _ in range(n_steps):
        psi = cgl_step(psi, c1=c1, c2=c2, dt=dt)
        if traj is not None:
            traj.append(psi.copy())

    if not np.all(np.isfinite(psi)):
        raise ValueError(
            f"CGL integration diverged (N={N}, n_steps={n_steps}, c1={c1}, c2={c2}, dt={dt}); "
            "reduce dt or n_steps, or move (c1, c2) away from the instability boundary"
        )
    return np.stack(traj, axis=0) if traj is not None else psi


def _planted_winding_theta(N: int, charge: int) -> np.ndarray:
    """Phase grid with `charge` turns of winding about the grid centre (a
    charge-generalized version of `single_vortex`'s arctan2 construction, used
    to seed `kuramoto_vortex_field` with a KNOWN initial topological charge).
    """
    x = np.linspace(-1, 1, N)
    y = np.linspace(-1, 1, N)
    X, Y = np.meshgrid(x, y)
    return charge * (-np.arctan2(Y, X))


def kuramoto_vortex_field(
    N: int = 64,
    n_steps: int = 200,
    dt: float = 0.05,
    K: float = 4.0,
    coupling_radius: float = 3.0,
    sigma_omega: float = 0.0,
    noise_std: float = 0.0,
    planted_charge: int = 1,
    seed: int = 0,
    return_trajectory: bool = False,
):
    """Spatially-coupled 2D Kuramoto oscillator lattice, phase seeded with a
    PLANTED, known winding charge; returns psi = exp(i*theta) -- a drop-in
    ground-truth field for `compute_Qz` -- as the final ``(N, N)`` frame (or the
    full ``(n_steps+1, N, N)`` trajectory if ``return_trajectory``).

    Each oscillator's phase evolves as
    ``dtheta_i/dt = omega_i + K * mean_j~i[sin(theta_j - theta_i)]``, where the
    neighborhood average is a Gaussian kernel of width ``coupling_radius``
    (periodic boundary, via `scipy.ndimage.convolve(mode="wrap")`) -- the
    standard local/nonlocal Kuramoto model, known to support persistent,
    slowly-drifting phase vortices in the partially-synchronized regime.
    Because coupling continuously competes against frequency heterogeneity
    (``sigma_omega``) and phase noise (``noise_std``) to erase the planted
    charge, sweeping either knob gives a tunable dial: strong coupling / low
    disorder synchronizes the field (planted charge is retained, or the field
    relaxes toward a single coherent phase); weak coupling / high disorder lets
    the charge decay or new defects nucleate -- exactly the metastable,
    known-but-evolving regime `analysis/events.py` and `tracking/worldlines.py`
    have never had a ground truth to validate creation/motion/annihilation
    against.

    Unlike `cgl_defect_field`, this is a PURE PHASE model -- amplitude is
    exactly 1 everywhere by construction (`psi = exp(i*theta)`), so it does
    NOT exercise `core.defects.detect_defects`'s amplitude-dip criterion (use
    `cgl_defect_field` for that); it exercises `compute_Qz`/`compute_Qabs_slice`
    charge tracking under known, controllable dynamics instead.
    """
    if N < 4:
        raise ValueError(f"N must be >= 4, got {N}")
    if n_steps < 0:
        raise ValueError(f"n_steps must be >= 0, got {n_steps}")
    from scipy.ndimage import convolve as _ndconvolve

    rng = np.random.default_rng(seed)
    theta = _planted_winding_theta(N, planted_charge)
    omega = rng.normal(0.0, sigma_omega, size=(N, N)) if sigma_omega > 0 else np.zeros((N, N))

    r = max(1, int(round(coupling_radius)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    kernel = np.exp(-(xx ** 2 + yy ** 2) / (2 * coupling_radius ** 2))
    kernel /= kernel.sum()

    traj = [np.exp(1j * theta)] if return_trajectory else None
    for _ in range(n_steps):
        sin_t, cos_t = np.sin(theta), np.cos(theta)
        local_sin = _ndconvolve(sin_t, kernel, mode="wrap")
        local_cos = _ndconvolve(cos_t, kernel, mode="wrap")
        coupling_term = cos_t * local_sin - sin_t * local_cos  # mean_j sin(theta_j - theta_i)
        dtheta = omega + K * coupling_term
        theta = theta + dt * dtheta
        if noise_std > 0:
            theta = theta + rng.normal(0.0, noise_std * np.sqrt(dt), size=(N, N))
        if traj is not None:
            traj.append(np.exp(1j * theta))

    if not np.all(np.isfinite(theta)):
        raise ValueError(
            f"Kuramoto integration diverged (N={N}, n_steps={n_steps}, K={K}, dt={dt})"
        )
    psi = np.exp(1j * theta)
    return np.stack(traj, axis=0) if traj is not None else psi


def validate_dynamical_ground_truth(seed: int = 0) -> dict:
    """Smoke-validate the two dynamical generators (parallel to
    `validate_vortex_charges`, but for time-evolving, non-hand-written fields).

    Checks:
      1. `cgl_defect_field` at short integration time produces a genuinely
         nonzero, substantial `Qabs` (many defects freshly nucleated from
         noise) -- confirming CGL, not diffusion, is doing the work.
      2. `core.defects.detect_defects` finds a nonzero defect count on that
         same CGL field -- closing the generator/detector amplitude mismatch
         that made `detect_defects` find zero defects on `single_vortex`.
      3. `kuramoto_vortex_field` with strong coupling / no disorder retains
         detectable net winding consistent with its planted charge (coupling
         alone does not have to erase a topologically protected charge),
         demonstrating the field is a genuine dynamical carrier of the planted
         charge, not just a static relabeling of it.
    """
    from core.defects import detect_defects

    cgl = cgl_defect_field(N=64, n_steps=100, seed=seed)
    _, cgl_qabs = compute_Qz(cgl[:, :, np.newaxis])
    cgl_qabs = float(cgl_qabs[0])
    n_defects = int(detect_defects(cgl[:, :, np.newaxis], amp_threshold=0.2).shape[0])

    kuramoto = kuramoto_vortex_field(N=64, n_steps=200, K=6.0, sigma_omega=0.0, planted_charge=1, seed=seed)
    kur_q, _ = compute_Qz(kuramoto[:, :, np.newaxis])
    kur_q = int(kur_q[0])

    return {
        "cgl_qabs": cgl_qabs,
        "cgl_qabs_nonzero": bool(cgl_qabs > 1.0),
        "cgl_n_defects_detected": n_defects,
        "cgl_defects_detected_pass": bool(n_defects > 0),
        "kuramoto_planted_charge": 1,
        "kuramoto_recovered_Q": kur_q,
        "kuramoto_charge_retained_pass": bool(kur_q == 1),
    }
