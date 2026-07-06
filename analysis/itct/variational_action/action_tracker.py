"""Variational action tracker for ITCT-style dynamics.

Tracks a scalar "action" functional built from arbitrary energy/information observable
time series, and measures how close the system sits to stationarity (dS/dt ~ 0) at each
point in time. This is a measurement scaffold, not a proof of any physical claim: it
reports numbers, it does not assert what those numbers mean about consciousness.

Baseline comparators (GNWBaselineGenerator, IITBaselineGenerator) are explicitly labeled
SIMPLIFIED PROXIES for the qualitative dynamical shape each theory is usually described as
predicting (GNW: diffuse, global, roughly-simultaneous desynchronization; IIT: graded,
smooth, non-bifurcating metric decline). They are NOT validated tests of GNW or IIT, and
they are NOT tuned to lose to anything -- their parameters are drawn from the same
config-driven RNG as any other synthetic input here, with no privileged target value.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VariationalActionConfig:
    """Weights are free parameters of the *measurement*, not of a hoped-for result.
    Change them and re-run; nothing here is calibrated to output a specific number."""

    energy_weight: float = 1.0
    information_weight: float = 1.0
    dt: float = 1.0
    stationarity_eps: float = 1e-3  # |dS/dt| below this counts as "near-stationary"


class VariationalActionTracker:
    """Computes S(t) = w_E * E(t) - w_I * I(t) (a generic Lagrangian-style balance of an
    energetic cost term against an informational term) from arbitrary input time series,
    and reports dS/dt and a boolean stationarity flag per timestep.

    E and I are whatever the caller passes in -- e.g. Qabs/entropy_proxy from
    core.topology or sciencer_d.btc_icft.level_m.features, or raw synthetic arrays for
    offline testing. This class does not generate its own "energy" or "information";
    it only tracks the action built from what it's given.
    """

    def __init__(self, config: VariationalActionConfig | None = None):
        self.config = config or VariationalActionConfig()

    def action_series(self, energy: np.ndarray, information: np.ndarray) -> np.ndarray:
        energy = np.asarray(energy, dtype=float)
        information = np.asarray(information, dtype=float)
        if energy.shape != information.shape:
            raise ValueError(
                f"energy shape {energy.shape} != information shape {information.shape}"
            )
        return self.config.energy_weight * energy - self.config.information_weight * information

    def track(self, energy: np.ndarray, information: np.ndarray) -> dict:
        """Returns action S(t), its time derivative, and a per-step stationarity flag."""
        S = self.action_series(energy, information)
        dS_dt = np.gradient(S, self.config.dt)
        stationary = np.abs(dS_dt) < self.config.stationarity_eps
        return {
            "S": S,
            "dS_dt": dS_dt,
            "stationary": stationary,
            "frac_time_stationary": float(np.mean(stationary)),
            "mean_abs_dS_dt": float(np.mean(np.abs(dS_dt))),
        }


class GNWBaselineGenerator:
    """Simplified proxy for a Global-Neuronal-Workspace-style transition: a fast, roughly
    simultaneous, diffuse drop across many channels (an 'ignition/extinction' step with
    added noise), NOT a validated simulation of GNW itself. Parameters are exposed, not
    hidden, and are not chosen to make this look worse than any other model.
    """

    def __init__(self, n_channels: int = 32, seed: int | None = None):
        self.n_channels = n_channels
        self.rng = np.random.default_rng(seed)

    def generate(self, n_steps: int, transition_step: int, steepness: float = 4.0) -> np.ndarray:
        """Returns (n_steps, n_channels) array: diffuse global sigmoid drop + noise."""
        t = np.arange(n_steps)
        sigmoid = 1.0 / (1.0 + np.exp(steepness * (t - transition_step) / max(n_steps, 1)))
        base = np.tile(sigmoid[:, None], (1, self.n_channels))
        noise = 0.05 * self.rng.standard_normal((n_steps, self.n_channels))
        return np.clip(base + noise, 0.0, 1.0)


class IITBaselineGenerator:
    """Simplified proxy for an Integrated-Information-Theory-style transition: a smooth,
    graded, non-bifurcating decline (no sharp step, no bimodal jump), NOT a validated
    simulation of IIT/phi itself.
    """

    def __init__(self, n_channels: int = 32, seed: int | None = None):
        self.n_channels = n_channels
        self.rng = np.random.default_rng(seed)

    def generate(self, n_steps: int, decay_rate: float = 0.02) -> np.ndarray:
        """Returns (n_steps, n_channels) array: smooth exponential-ish graded decline."""
        t = np.arange(n_steps)
        base_curve = np.exp(-decay_rate * t)
        base = np.tile(base_curve[:, None], (1, self.n_channels))
        noise = 0.03 * self.rng.standard_normal((n_steps, self.n_channels))
        return np.clip(base + noise, 0.0, 1.0)


def compare_against_baselines(
    itct_energy: np.ndarray,
    itct_information: np.ndarray,
    n_channels: int = 32,
    transition_step: int | None = None,
    seed: int = 0,
    tracker_config: VariationalActionConfig | None = None,
) -> dict:
    """Runs the same action-stationarity measurement on the ITCT-derived series AND on
    GNW/IIT baseline proxies generated with the SAME length and seed policy, so all three
    get an identical measurement procedure applied. Reports all three sets of numbers;
    does not pick a winner. Whether ITCT's stationarity profile is actually distinct from
    the baselines is for the caller (a human, or a later honest analysis step) to judge
    from the returned numbers -- this function does not embed a verdict.
    """
    n_steps = len(itct_energy)
    if transition_step is None:
        transition_step = n_steps // 2

    tracker = VariationalActionTracker(tracker_config)
    itct_result = tracker.track(itct_energy, itct_information)

    gnw = GNWBaselineGenerator(n_channels=n_channels, seed=seed).generate(n_steps, transition_step)
    iit = IITBaselineGenerator(n_channels=n_channels, seed=seed + 1).generate(n_steps)

    gnw_energy = gnw.mean(axis=1)
    gnw_information = 1.0 - gnw_energy  # placeholder-free: complementary channel, not tuned
    iit_energy = iit.mean(axis=1)
    iit_information = 1.0 - iit_energy

    gnw_result = tracker.track(gnw_energy, gnw_information)
    iit_result = tracker.track(iit_energy, iit_information)

    return {
        "itct": itct_result,
        "gnw_baseline": gnw_result,
        "iit_baseline": iit_result,
        "note": (
            "GNW/IIT results are simplified dynamical-shape proxies for benchmarking, "
            "not validated simulations of either theory. No verdict is asserted here; "
            "compare frac_time_stationary and mean_abs_dS_dt yourself."
        ),
    }
