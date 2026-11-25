"""Bounded numerical stochastic-escape benchmark on a 1D saddle-node normal form.

Dimensionless normal-form SDE (units: [q]=1, [t]=1, [r]=1, [D]=1):
    dq = (r - q^2) dt + sqrt(2 * D) dW_t,     r > 0, D > 0

Associated potential:
    V(q) = -r * q + q^3 / 3
with stable well q_+ = +sqrt(r), unstable saddle q_- = -sqrt(r), and barrier
height Delta_V = (4 / 3) * r^(3/2).

Strictly compares compatible finite-horizon estimands on [q_min, q_max] over
[0, T] (survival probability S(T) = P(tau > T) and Restricted Mean Survival Time
RMST(T) = E[min(tau, T)]) between a backward-Kolmogorov Crank-Nicolson PDE
oracle and censored Euler-Maruyama Monte Carlo with per-trial SeedSequence
streams.

Epistemic scope:
- SYNTHETIC_NUMERICAL_BENCHMARK only.
- Does NOT infer or claim a biological, SU(2), or neural escape law.
- Asymptotic Kramers rate is gated by barrier-to-noise ratio (Delta_V / D >= 6)
  and is never conflated with finite-horizon / non-asymptotic survival.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Any, Dict, List, Optional, Sequence
import numpy as np
from scipy.linalg import solve_banded

from runs.run_record import RunRecordV1


@dataclass(frozen=True)
class EscapeBenchmarkConfig:
    """Parameters and domain/discretization contract for 1D saddle-node escape."""

    r: float = 0.25
    D: float = 0.04
    q0: float = 0.50         # initialized at stable equilibrium +sqrt(0.25) = 0.50
    T: float = 12.0
    q_min: float = -1.25     # absorbing escape boundary below saddle (-sqrt(r) = -0.50)
    q_max: float = 2.00      # reflecting upper boundary well above q_+ = 0.50
    dt_mc: float = 0.005
    n_trials: int = 1200
    base_seed: int = 20261124
    n_q_pde: int = 301
    n_t_pde: int = 600

    def validate(self) -> None:
        if self.r <= 0.0 or not math.isfinite(self.r):
            raise ValueError(f"r must be positive and finite, got {self.r}")
        if self.D <= 0.0 or not math.isfinite(self.D):
            raise ValueError(f"D must be positive and finite, got {self.D}")
        if self.T <= 0.0 or not math.isfinite(self.T):
            raise ValueError(f"T must be positive and finite, got {self.T}")
        if not (self.q_min < self.q0 <= self.q_max):
            raise ValueError(
                f"Require q_min < q0 <= q_max, got ({self.q_min}, {self.q0}, {self.q_max})"
            )
        saddle = -math.sqrt(self.r)
        if self.q_min >= saddle:
            raise ValueError(
                f"Absorbing boundary q_min={self.q_min} must lie below saddle q_-={saddle:.4f}"
            )
        if self.dt_mc <= 0.0 or self.n_trials < 1:
            raise ValueError("dt_mc must be > 0 and n_trials >= 1")
        if self.n_q_pde < 21 or self.n_t_pde < 10:
            raise ValueError("PDE grid too coarse (require n_q_pde >= 21, n_t_pde >= 10)")


def kramers_asymptotic_summary(r: float, D: float, min_ratio: float = 6.0) -> Dict[str, Any]:
    """Compute 1D saddle-node Kramers escape rate with explicit asymptotic validity gate.

    Only applicable in the deep-well asymptotic limit Delta_V / D >= min_ratio and
    infinite-horizon/unbounded-exit approximation; reports ``asymptotic_valid=False``
    outside that regime.
    """
    if r <= 0.0 or D <= 0.0:
        raise ValueError("r and D must be > 0")
    delta_v = (4.0 / 3.0) * (r ** 1.5)
    ratio = delta_v / D
    prefactor = math.sqrt(r) / math.pi
    rate = prefactor * math.exp(-ratio)
    mfpt = (1.0 / rate) if rate > 0.0 else float("inf")
    return {
        "delta_V": delta_v,
        "barrier_to_noise_ratio": ratio,
        "asymptotic_valid": bool(ratio >= min_ratio),
        "kramers_rate": rate if ratio >= min_ratio else None,
        "kramers_mfpt": mfpt if ratio >= min_ratio else None,
        "raw_formula_rate_unvalidated": rate,
    }


def solve_survival_pde(
    r: float,
    D: float,
    q0: float,
    T: float,
    q_min: float,
    q_max: float,
    n_q: int = 301,
    n_t: int = 600,
) -> Dict[str, Any]:
    """Solve the backward Kolmogorov survival PDE via Crank-Nicolson on [q_min, q_max].

    PDE: dS/dt = (r - q^2) dS/dq + D d^2S/dq^2
    IC:  S(q, 0) = 1 for q > q_min
    BCs: S(q_min, t) = 0 (absorbing), dS/dq(q_max, t) = 0 (reflecting).
    """
    q_grid = np.linspace(q_min, q_max, n_q, dtype=np.float64)
    dq = float(q_grid[1] - q_grid[0])
    dt = float(T) / float(n_t)

    # Unknowns are interior + upper boundary nodes j = 1 .. n_q - 1 (n_int = n_q - 1)
    q_int = q_grid[1:]
    n_int = len(q_int)
    drift = r - q_int ** 2

    # Discretized spatial operator L on nodes 1..n_q-1 (central drift + 2nd-order diffusion)
    sub = (D / (dq ** 2)) - (drift / (2.0 * dq))   # multiplies S_{j-1}
    diag = np.full(n_int, -2.0 * D / (dq ** 2), dtype=np.float64)
    sup = (D / (dq ** 2)) + (drift / (2.0 * dq))   # multiplies S_{j+1}

    # Reflecting ghost point S_{M+1} = S_{M-1} at j = M (last index n_int - 1)
    sub[-1] = 2.0 * D / (dq ** 2)
    sup[-1] = 0.0

    # Crank-Nicolson: (I - 0.5 dt L) S^{n+1} = (I + 0.5 dt L) S^n
    ab_lhs = np.zeros((3, n_int), dtype=np.float64)
    ab_lhs[0, 1:] = -0.5 * dt * sup[:-1]
    ab_lhs[1, :] = 1.0 - 0.5 * dt * diag
    ab_lhs[2, :-1] = -0.5 * dt * sub[1:]

    S = np.ones(n_int, dtype=np.float64)
    # Record survival curve at q0 over all time steps for exact RMST integration
    t_axis = np.linspace(0.0, T, n_t + 1, dtype=np.float64)
    S_curve = np.empty(n_t + 1, dtype=np.float64)
    S_curve[0] = float(np.interp(q0, q_grid, np.concatenate([[0.0], S])))

    for step in range(1, n_t + 1):
        rhs = S.copy()
        rhs += 0.5 * dt * (diag * S)
        rhs[1:] += 0.5 * dt * (sub[1:] * S[:-1])
        rhs[:-1] += 0.5 * dt * (sup[:-1] * S[1:])
        S = solve_banded((1, 1), ab_lhs, rhs)
        S_full = np.concatenate([[0.0], S])
        S_curve[step] = float(np.interp(q0, q_grid, S_full))

    S_T = float(np.clip(S_curve[-1], 0.0, 1.0))
    rmst = float(np.trapezoid(np.clip(S_curve, 0.0, 1.0), t_axis))
    peclet_max = float(np.max(np.abs(drift)) * dq / (2.0 * D))

    return {
        "survival_T": S_T,
        "rmst_T": rmst,
        "peclet_max": peclet_max,
        "dt_pde": dt,
        "dq_pde": dq,
    }


def simulate_censored_escape(
    r: float,
    D: float,
    q0: float,
    T: float,
    q_min: float,
    q_max: float,
    dt: float = 0.005,
    n_trials: int = 1200,
    base_seed: int = 20261124,
) -> Dict[str, Any]:
    """Run right-censored Euler-Maruyama Monte Carlo with per-trial SeedSequence streams."""
    n_steps = int(round(T / dt))
    dt_eff = float(T) / float(n_steps)
    noise_scale = math.sqrt(2.0 * D * dt_eff)

    ss = np.random.SeedSequence(base_seed)
    children = ss.spawn(n_trials)

    obs_times = np.empty(n_trials, dtype=np.float64)
    escaped = np.zeros(n_trials, dtype=bool)

    for k, child in enumerate(children):
        rng = np.random.default_rng(child)
        dW = rng.standard_normal(n_steps) * noise_scale
        q = float(q0)
        hit = False
        for step in range(n_steps):
            q = q + (r - q * q) * dt_eff + dW[step]
            if q > q_max:
                q = 2.0 * q_max - q
                if q > q_max:
                    q = q_max
            if q <= q_min:
                obs_times[k] = (step + 1) * dt_eff
                escaped[k] = True
                hit = True
                break
        if not hit:
            obs_times[k] = T

    survived = ~escaped
    survival_T = float(np.mean(survived))
    survival_se = float(math.sqrt(survival_T * (1.0 - survival_T) / n_trials))
    rmst_T = float(np.mean(obs_times))
    rmst_se = float(np.std(obs_times, ddof=1) / math.sqrt(n_trials)) if n_trials > 1 else 0.0

    return {
        "n_trials": n_trials,
        "dt_mc": dt_eff,
        "base_seed": base_seed,
        "survival_T": survival_T,
        "survival_se": survival_se,
        "rmst_T": rmst_T,
        "rmst_se": rmst_se,
        "censored_fraction": survival_T,
        "escaped_fraction": float(np.mean(escaped)),
    }


def run_stochastic_escape_benchmark(
    cfg: EscapeBenchmarkConfig = EscapeBenchmarkConfig(),
    run_sensitivity: bool = True,
) -> Dict[str, Any]:
    """Run the complete PDE-oracle vs. censored-MC benchmark and sensitivity suite."""
    cfg.validate()

    pde = solve_survival_pde(
        cfg.r, cfg.D, cfg.q0, cfg.T, cfg.q_min, cfg.q_max, cfg.n_q_pde, cfg.n_t_pde
    )
    mc = simulate_censored_escape(
        cfg.r, cfg.D, cfg.q0, cfg.T, cfg.q_min, cfg.q_max, cfg.dt_mc, cfg.n_trials, cfg.base_seed
    )
    kramers = kramers_asymptotic_summary(cfg.r, cfg.D)

    surv_diff = abs(mc["survival_T"] - pde["survival_T"])
    rmst_diff = abs(mc["rmst_T"] - pde["rmst_T"])
    surv_z = surv_diff / max(mc["survival_se"], 1e-12)
    rmst_z = rmst_diff / max(mc["rmst_se"], 1e-12)

    out: Dict[str, Any] = {
        "config": asdict(cfg),
        "units": {"q": "dimensionless", "t": "dimensionless", "r": "dimensionless", "D": "dimensionless"},
        "pde_oracle": pde,
        "mc_censored": mc,
        "pde_vs_mc_compatibility": {
            "survival_abs_diff": surv_diff,
            "survival_z_score": surv_z,
            "rmst_abs_diff": rmst_diff,
            "rmst_z_score": rmst_z,
        },
        "kramers_reference": kramers,
    }

    if run_sensitivity:
        pde_fine_t = solve_survival_pde(
            cfg.r, cfg.D, cfg.q0, cfg.T, cfg.q_min, cfg.q_max, cfg.n_q_pde, cfg.n_t_pde * 2
        )
        pde_wider_left = solve_survival_pde(
            cfg.r, cfg.D, cfg.q0, cfg.T, cfg.q_min - 0.50, cfg.q_max, cfg.n_q_pde + 50, cfg.n_t_pde
        )
        pde_wider_right = solve_survival_pde(
            cfg.r, cfg.D, cfg.q0, cfg.T, cfg.q_min, cfg.q_max + 0.50, cfg.n_q_pde + 50, cfg.n_t_pde
        )
        mc_half_dt = simulate_censored_escape(
            cfg.r, cfg.D, cfg.q0, cfg.T, cfg.q_min, cfg.q_max, cfg.dt_mc / 2.0, min(cfg.n_trials, 400), cfg.base_seed + 1
        )
        out["sensitivity"] = {
            "pde_dt_halved_survival_diff": abs(pde_fine_t["survival_T"] - pde["survival_T"]),
            "pde_dt_halved_rmst_diff": abs(pde_fine_t["rmst_T"] - pde["rmst_T"]),
            "pde_qmin_extended_survival_diff": abs(pde_wider_left["survival_T"] - pde["survival_T"]),
            "pde_qmax_extended_survival_diff": abs(pde_wider_right["survival_T"] - pde["survival_T"]),
            "mc_dt_halved_rmst": mc_half_dt["rmst_T"],
        }

    return out


def build_escape_run_record(
    result: Dict[str, Any],
    run_id: str = "stoch_escape_001",
    verdict: str = "PASS",
) -> RunRecordV1:
    """Package benchmark metrics into the repository's canonical RunRecordV1 contract."""
    compat = result["pde_vs_mc_compatibility"]
    pde = result["pde_oracle"]
    mc = result["mc_censored"]
    kramers = result["kramers_reference"]

    return RunRecordV1.make(
        run_id=run_id,
        run_kind="benchmark",
        spec_id="stochastic_escape_normal_form_v1",
        claim_type="synthetic_numerical_benchmark",
        layer="simulation",
        data_mode="synthetic",
        verdict=verdict,
        metrics={
            "pde_survival_T": pde["survival_T"],
            "pde_rmst_T": pde["rmst_T"],
            "mc_survival_T": mc["survival_T"],
            "mc_survival_se": mc["survival_se"],
            "mc_rmst_T": mc["rmst_T"],
            "mc_rmst_se": mc["rmst_se"],
            "survival_z_score": compat["survival_z_score"],
            "rmst_z_score": compat["rmst_z_score"],
            "barrier_to_noise_ratio": kramers["barrier_to_noise_ratio"],
            "kramers_asymptotic_valid": kramers["asymptotic_valid"],
        },
        source="sim.stochastic_escape_benchmark",
    )
