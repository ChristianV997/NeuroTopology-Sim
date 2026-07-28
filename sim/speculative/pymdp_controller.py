"""Real Active-Inference (pymdp) controller — a discrete POMDP free-energy
demonstration, SPECULATIVE track only.

Why this exists: the repo already has `sim/active_inference.py`, a hand-rolled
continuous expected-free-energy optimizer for synthetic parameter sweeps. That
module is real but is NOT a POMDP and does not use a maintained
active-inference library. This module is a genuine discrete Partially
Observable Markov Decision Process built on the `pymdp` library
(`inferactively-pymdp`, MIT-licensed), computing the ACTUAL variational free
energy (VFE) of belief updating via `pymdp.maths.calc_free_energy` — not a
re-derivation.

Falsifiable synthetic experiment (the ONLY claim made here): an agent whose
generative model holds a rigid, high-precision prior over the hidden state
pays MORE variational free energy when it receives an observation that
contradicts that prior than an agent with a flexible (near-uniform) prior
does, under the same likelihood and the same surprising observation. This is
a standard, textbook property of variational inference (precision-weighted
prediction error), reproduced here on a minimal 2-state / 2-outcome model so
it is exact and inspectable. `prior_cost_gradient()` returns the VFE across a
sweep of prior precisions and asserts nothing about biology.

STRICT SCOPE (enforced, not just documented):
- This file lives under `sim/speculative/` and must never be imported by
  `sciencer_d/btc_icft/` or feed any published dataset report
  (`tests/test_speculative_boundary.py` enforces the import boundary via a
  static AST check).
- No neuroscience, consciousness, or contemplative-practice claim is made.
  Variable names are neutral POMDP terms. Any text artifact this module emits
  must carry `SPECULATIVE_BANNER` and pass `validate_speculative_text`.
- This is a controller/measurement demo on a toy generative model. It is NOT
  applied to any EEG/fMRI/LFP recording, real or simulated.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.speculative import SPECULATIVE_BANNER, validate_speculative_text


@dataclass(frozen=True)
class VFEResult:
    prior: tuple[float, ...]
    observation: int
    posterior: tuple[float, ...]
    variational_free_energy: float


def _require_pymdp():
    try:
        from pymdp import maths, utils
        from pymdp.algos.fpi import run_vanilla_fpi
    except Exception as exc:  # pragma: no cover - dependency guard
        raise ImportError(
            "pymdp (inferactively-pymdp==0.0.7.1) is required for the speculative "
            "active-inference controller. Install via requirements.txt."
        ) from exc
    return maths, utils, run_vanilla_fpi


def variational_free_energy(A: np.ndarray, observation: int, prior: np.ndarray) -> VFEResult:
    """Infer the posterior over hidden states and compute the REAL variational
    free energy of that update, via pymdp.

    A: (n_outcomes, n_states) likelihood P(o|s), columns sum to 1.
    observation: index of the observed outcome.
    prior: (n_states,) prior P(s), sums to 1.
    """
    maths, utils, run_vanilla_fpi = _require_pymdp()
    A = np.asarray(A, dtype=float)
    prior = np.asarray(prior, dtype=float)
    n_out, n_states = A.shape

    A_obj = utils.to_obj_array(A)
    obs_obj = utils.to_obj_array(utils.onehot(int(observation), n_out))
    prior_obj = utils.to_obj_array(prior)

    qs = run_vanilla_fpi(A_obj, obs_obj, num_obs=[n_out], num_states=[n_states], prior=prior_obj)
    log_lik = maths.spm_log_single(maths.get_joint_likelihood(A_obj, obs_obj, [n_states]))
    F = float(np.asarray(maths.calc_free_energy(qs, prior_obj, 1, log_lik)).ravel()[0])

    return VFEResult(
        prior=tuple(float(p) for p in prior),
        observation=int(observation),
        posterior=tuple(float(q) for q in np.asarray(qs[0])),
        variational_free_energy=F,
    )


def _two_state_prior(precision: float) -> np.ndarray:
    """A 2-state prior that concentrates on state 0 as `precision` -> 1 and is
    uniform at `precision` = 0.5."""
    p0 = float(np.clip(precision, 1e-6, 1 - 1e-6))
    return np.array([p0, 1.0 - p0])


def prior_cost_gradient(
    precisions: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99),
    surprising_observation: int = 1,
    likelihood_precision: float = 0.9,
) -> list[VFEResult]:
    """VFE across a sweep of prior precisions, for an observation that
    contradicts the concentrated prior.

    With a likelihood that maps state 0 -> outcome 0 (prob `likelihood_precision`)
    and the agent observing outcome `surprising_observation` = 1, a more rigid
    (higher-precision) prior on state 0 should incur monotonically higher VFE.
    Returns one VFEResult per precision.
    """
    lp = float(np.clip(likelihood_precision, 1e-6, 1 - 1e-6))
    A = np.array([[lp, 1 - lp], [1 - lp, lp]])  # P(o|s)
    return [
        variational_free_energy(A, surprising_observation, _two_state_prior(pi))
        for pi in precisions
    ]


def rigidity_increases_free_energy_under_surprise() -> bool:
    """The single falsifiable check: VFE is non-decreasing as the prior becomes
    more rigid, when the observation contradicts that prior. Returns True if the
    real pymdp computation exhibits this (a property of variational inference,
    reproduced here — not a biological claim)."""
    results = prior_cost_gradient()
    f = [r.variational_free_energy for r in results]
    return all(f[i + 1] >= f[i] - 1e-9 for i in range(len(f) - 1))


def render_report() -> str:
    """A short, banner-carrying, guardrail-passing summary of the demo."""
    results = prior_cost_gradient()
    lines = [
        f"# {SPECULATIVE_BANNER}",
        "",
        "## Active-Inference (pymdp) POMDP free-energy demonstration",
        "",
        "Real variational free energy (via `pymdp.maths.calc_free_energy`) of a "
        "2-state/2-outcome belief update, for an observation that contradicts a "
        "prior concentrated on state 0, across increasing prior precision:",
        "",
        "| prior P(s0) | posterior P(s0) | variational free energy |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.prior[0]:.3f} | {r.posterior[0]:.3f} | {r.variational_free_energy:.4f} |")
    monotone = rigidity_increases_free_energy_under_surprise()
    lines += [
        "",
        f"Rigidity monotonically increases free energy under surprise: **{monotone}** "
        "(a standard property of precision-weighted variational inference, reproduced "
        "on a toy model — no claim about biological cognition).",
    ]
    text = "\n".join(lines) + "\n"
    validate_speculative_text(text)
    return text


if __name__ == "__main__":
    print(render_report())
