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
