"""Active inference controller for steering simulation parameter search.

A simplified, discretized implementation of expected free energy (EFE)
minimization (Friston et al.'s free-energy principle), used here strictly
as a simulation-optimization tool: adaptively choosing which parameter
value to try next in a synthetic experiment, balancing goal-seeking
(pragmatic value -- KL divergence of the predicted outcome from a
preferred outcome) against uncertainty-resolution (epistemic value --
preferring under-sampled regions of the parameter space).

Scope, deliberately narrow: this is an optimizer for `sim/` /
`validation/synthetic.py` parameter sweeps only. It is never applied as
an analysis step to real EEG data, and makes no claim about biological
cognition -- see the project plan's Phase 9 scoping note. This module
must not import from `sciencer_d.btc_icft` or any real-EEG pipeline; a
test enforces that boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

import numpy as np


@dataclass
class _BinBelief:
    """Conjugate normal-normal posterior belief about one parameter bin's
    expected outcome."""

    mean: float
    precision: float  # 1 / variance

    @property
    def variance(self) -> float:
        return 1.0 / self.precision

    def update(self, observation: float, obs_precision: float) -> None:
        new_precision = self.precision + obs_precision
        self.mean = (self.precision * self.mean + obs_precision * observation) / new_precision
        self.precision = new_precision


class ActiveInferenceController:
    """Discretized expected-free-energy controller over a 1D parameter range.

    At each step, selects the parameter bin minimizing expected free
    energy: risk (KL divergence of the bin's predicted-outcome belief from
    a preferred-outcome distribution) minus an epistemic bonus (the bin's
    current predictive uncertainty, which favors under-sampled regions).
    After the caller evaluates the objective at that parameter, `observe`
    performs a Bayesian (conjugate normal-normal) belief update.
    """

    def __init__(
        self,
        param_min: float,
        param_max: float,
        n_bins: int = 20,
        preferred_mean: float = 0.0,
        preferred_variance: float = 1.0,
        obs_variance: float = 1.0,
        prior_variance: float = 100.0,
        epistemic_weight: float = 1.0,
    ) -> None:
        if n_bins < 2:
            raise ValueError("n_bins must be >= 2")
        if param_max <= param_min:
            raise ValueError("param_max must be > param_min")
        self.param_min = param_min
        self.param_max = param_max
        self.n_bins = n_bins
        self.preferred_mean = preferred_mean
        self.preferred_variance = preferred_variance
        self.obs_variance = obs_variance
        self.epistemic_weight = epistemic_weight

        self.bin_centers = np.linspace(param_min, param_max, n_bins)
        self.beliefs: List[_BinBelief] = [
            _BinBelief(mean=0.0, precision=1.0 / prior_variance) for _ in range(n_bins)
        ]
        self.history: List[Tuple[float, float]] = []  # (param, observed_outcome)

    def _risk(self, belief: _BinBelief) -> float:
        """KL(predicted outcome N(mean, obs_variance) || preferred
        N(preferred_mean, preferred_variance)).

        Deliberately uses the fixed observation variance here, not the
        belief's own (epistemic) variance about the mean: risk asks "how
        far would a typical draw at this bin's current best-guess mean be
        from what I want," which stays bounded even for an unvisited bin.
        Epistemic value (below) is where the belief's own uncertainty
        about the mean is used instead -- conflating the two collapses
        exploration, since an unvisited bin's huge belief-variance would
        otherwise dominate the risk term and make it look artificially
        risky rather than simply uninformative.
        """
        obs_var = self.obs_variance
        pref_var = self.preferred_variance
        return 0.5 * (
            np.log(pref_var / obs_var)
            + (obs_var + (belief.mean - self.preferred_mean) ** 2) / pref_var
            - 1.0
        )

    def expected_free_energy(self, bin_idx: int) -> float:
        belief = self.beliefs[bin_idx]
        risk = self._risk(belief)
        epistemic_value = belief.variance  # belief's own uncertainty about the mean
        return risk - self.epistemic_weight * epistemic_value

    def select_next(self) -> Tuple[int, float]:
        """Return (bin_idx, param_value) minimizing expected free energy."""
        efe = np.array([self.expected_free_energy(i) for i in range(self.n_bins)])
        best_idx = int(np.argmin(efe))
        return best_idx, float(self.bin_centers[best_idx])

    def observe(self, bin_idx: int, outcome: float) -> None:
        self.beliefs[bin_idx].update(outcome, obs_precision=1.0 / self.obs_variance)
        self.history.append((float(self.bin_centers[bin_idx]), float(outcome)))

    def run(self, objective: Callable[[float], float], n_iterations: int = 30) -> List[Tuple[float, float]]:
        """Iteratively select a parameter, evaluate `objective(param) -> outcome`,
        and update beliefs. Returns the (param, outcome) history."""
        for _ in range(n_iterations):
            bin_idx, param = self.select_next()
            outcome = objective(param)
            self.observe(bin_idx, outcome)
        return self.history

    def best_estimate(self) -> float:
        """Return the parameter value whose belief mean is closest to the preference."""
        means = np.array([b.mean for b in self.beliefs])
        best_idx = int(np.argmin(np.abs(means - self.preferred_mean)))
        return float(self.bin_centers[best_idx])


def search_vortex_noise_threshold(
    target_Qz: float = 0.5,
    N: int = 16,
    amplitude_min: float = 0.0,
    amplitude_max: float = 2.5,
    n_bins: int = 20,
    n_iterations: int = 40,
    obs_variance: float = 0.1,
    epistemic_weight: float = 0.5,
    seed: int = 0,
) -> Tuple[ActiveInferenceController, float]:
    """Use active inference to locate the noise_amplitude at which
    `validation.synthetic.perturbed_vortex`'s measured winding charge
    (Qz_mean) crosses a target value -- an "informative region" of the
    perturbation-parameter space (the robustness transition), found
    adaptively rather than via an exhaustive grid sweep.

    Simulation-optimization only: this function evaluates a synthetic
    field generator, never real EEG data. Returns (controller,
    best_amplitude_estimate).
    """
    from core.topology import compute_Qz
    from validation.synthetic import perturbed_vortex

    rng = np.random.default_rng(seed)

    def objective(amplitude: float) -> float:
        eval_seed = int(rng.integers(0, 2**31 - 1))
        psi = perturbed_vortex(N=N, noise_amplitude=amplitude, seed=eval_seed)
        qz, _ = compute_Qz(psi)
        return float(np.mean(qz))

    controller = ActiveInferenceController(
        param_min=amplitude_min,
        param_max=amplitude_max,
        n_bins=n_bins,
        preferred_mean=target_Qz,
        preferred_variance=0.05,
        obs_variance=obs_variance,
        epistemic_weight=epistemic_weight,
    )
    controller.run(objective, n_iterations=n_iterations)
    return controller, controller.best_estimate()
