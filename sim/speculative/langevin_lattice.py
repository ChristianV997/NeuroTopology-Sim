"""Stochastic Langevin-lattice field engine -- SPECULATIVE, segregated track.

Built on `py-pde` (numpy/numba-accelerated PDE solver, MIT-licensed) for the
spatial grid and Laplacian operator, with a custom explicit-Euler time
stepper so both standard (white) and fractional (non-Markovian, memory-
kernel) noise can drive the same damped-diffusion field. This is a real
numerical technique -- a damped stochastic diffusion equation
(an Ornstein-Uhlenbeck-like field, optionally with fractional Gaussian
noise instead of white noise) -- not a claim about biological neural
dynamics. See `sim/speculative/__init__.py` for the segregation policy this
module is subject to.

    du/dt = diffusivity * laplace(u) - damping * u + noise_amplitude * xi(t)

`noise_mode="white"`: xi is i.i.d. standard Gaussian per step per grid
point (a standard additive-noise SDE). `noise_mode="fractional"`: xi is
fractional Gaussian noise (fGn) with the given Hurst exponent, generated
independently per grid point via the `fbm` package (already a tested
dependency in this repo's DFA/MFDFA ground-truth fixtures) -- a real,
non-Markovian noise process with the requested long-range temporal
correlation structure, not a from-scratch reimplementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import pde

from sim.speculative import SPECULATIVE_BANNER, validate_speculative_text


@dataclass
class LangevinLatticeResult:
    steps: List[Dict[str, float]]
    final_field: np.ndarray
    params: Dict[str, Any]


def _generate_noise(
    n_steps: int,
    N: int,
    noise_mode: str,
    hurst: float,
    seed: int,
) -> np.ndarray:
    """Return an (n_steps, N, N) array of noise increments, one independent
    time series per grid point."""
    rng = np.random.default_rng(seed)
    if noise_mode == "white":
        return rng.standard_normal((n_steps, N, N))
    if noise_mode == "fractional":
        from fbm import FBM

        # `fbm.FBM` draws from the *global* numpy legacy random state (it
        # has no Generator/seed parameter) -- save and restore that global
        # state around this loop so seeding per grid point for
        # reproducibility doesn't leak into unrelated code using
        # `np.random` elsewhere in the process.
        global_state = np.random.get_state()
        try:
            noise = np.zeros((n_steps, N, N))
            for i in range(N):
                for j in range(N):
                    point_seed = int(rng.integers(0, 2**31 - 1))
                    np.random.seed(point_seed)
                    f = FBM(n=n_steps, hurst=hurst, length=1.0, method="daviesharte")
                    noise[:, i, j] = f.fgn()
        finally:
            np.random.set_state(global_state)
        return noise
    raise ValueError(f"unknown noise_mode: {noise_mode!r} (expected 'white' or 'fractional')")


def run_langevin_lattice(
    N: int = 16,
    n_steps: int = 50,
    dt: float = 0.01,
    diffusivity: float = 1.0,
    damping: float = 0.1,
    noise_amplitude: float = 0.1,
    noise_mode: str = "white",
    hurst: float = 0.7,
    seed: int = 0,
) -> LangevinLatticeResult:
    """Run a damped stochastic diffusion field on an `N`x`N` periodic
    py-pde grid for `n_steps`, returning per-step telemetry and the final
    field. Simulation-only: never fed real EEG data, never applied to a
    real dataset report -- see `sim/speculative/__init__.py`.
    """
    if noise_mode not in ("white", "fractional"):
        raise ValueError(f"unknown noise_mode: {noise_mode!r} (expected 'white' or 'fractional')")

    grid = pde.CartesianGrid([[0, N]] * 2, [N, N], periodic=True)
    rng = np.random.default_rng(seed)
    field = pde.ScalarField.random_normal(grid, mean=0.0, std=1.0, rng=rng)

    noise = _generate_noise(n_steps, N, noise_mode, hurst, seed)

    steps: List[Dict[str, float]] = []
    for step_idx in range(n_steps):
        laplacian = field.laplace(bc="periodic")
        drift = diffusivity * laplacian.data - damping * field.data
        field = pde.ScalarField(
            grid, field.data + dt * drift + np.sqrt(dt) * noise_amplitude * noise[step_idx]
        )

        data = field.data
        mean_val = float(np.mean(data))
        std_val = float(np.std(data))
        grad = np.gradient(data)
        energy = float(np.sum(grad[0] ** 2 + grad[1] ** 2))
        steps.append({"step": step_idx, "mean": mean_val, "std": std_val, "energy": energy})

    return LangevinLatticeResult(
        steps=steps,
        final_field=field.data,
        params={
            "N": N, "n_steps": n_steps, "dt": dt, "diffusivity": diffusivity,
            "damping": damping, "noise_amplitude": noise_amplitude,
            "noise_mode": noise_mode, "hurst": hurst, "seed": seed,
        },
    )


def build_speculative_report(result: LangevinLatticeResult) -> str:
    """Render a banner-labeled, guardrail-validated Markdown summary of a
    Langevin-lattice run. Raises ValueError (via `validate_speculative_text`)
    if the banner or a banned phrase check fails -- this function cannot
    silently emit an unlabeled or overclaiming report."""
    final_energy = result.steps[-1]["energy"] if result.steps else float("nan")
    final_std = result.steps[-1]["std"] if result.steps else float("nan")
    lines = [
        SPECULATIVE_BANNER,
        "",
        "# Speculative Langevin-Lattice Run",
        "",
        f"- noise_mode: {result.params['noise_mode']}",
        f"- N: {result.params['N']}, n_steps: {result.params['n_steps']}",
        f"- final field std: {final_std:.6f}",
        f"- final gradient energy: {final_energy:.6f}",
        "",
        "This is a synthetic stochastic-field simulation exploring "
        "physics-inspired lattice dynamics. It uses no real EEG data as "
        "input and supports no claim about biological neural dynamics.",
    ]
    text = "\n".join(lines)
    validate_speculative_text(text)
    return text
