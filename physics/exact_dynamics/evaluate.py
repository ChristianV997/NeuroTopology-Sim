"""Conservative observables and falsification status for dynamics trajectories."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import numpy as np
from .dynamics_solver import DynamicsResult


@dataclass(frozen=True)
class FalsificationConfig:
    """Pre-registered evidence gate; threshold is one picosecond by design."""
    noise_dominant_threshold_s: float = 1e-12
    max_trace_residual: float = 1e-8
    max_positivity_residual: float = 1e-8


def _coherence_envelope(states: np.ndarray) -> np.ndarray:
    off_diagonal = states.copy()
    diagonal = np.arange(states.shape[1]); off_diagonal[:, diagonal, diagonal] = 0
    return np.max(np.abs(off_diagonal), axis=(1, 2))


def _lifetime(times: np.ndarray, envelope: np.ndarray) -> float:
    initial = float(envelope[0])
    if initial <= np.finfo(float).tiny: return 0.0
    below = np.flatnonzero(envelope <= initial / np.e)
    return float(times[below[0]]) if below.size else float("inf")


def evaluate_falsification(result: DynamicsResult, *, ab_initio_inputs: bool, config: FalsificationConfig = FalsificationConfig()) -> dict[str, object]:
    """Return only FALSIFIED/INCONCLUSIVE; never emit an affirmative evidence claim."""
    envelope = _coherence_envelope(result.density_matrices); tau = _lifetime(result.times_s, envelope)
    diagnostics_ok = result.trace_residual <= config.max_trace_residual and result.positivity_residual <= config.max_positivity_residual
    if result.converged and ab_initio_inputs and diagnostics_ok and tau < config.noise_dominant_threshold_s:
        verdict: Literal["FALSIFIED: NOISE_DOMINANT", "INCONCLUSIVE"] = "FALSIFIED: NOISE_DOMINANT"
    else: verdict = "INCONCLUSIVE"
    return {"verdict": verdict, "tau_subradiant_s": tau, "coherence_envelope": envelope.tolist(),
            "diagnostics_ok": diagnostics_ok, "ab_initio_inputs": ab_initio_inputs, "backend": result.backend,
            "reason": "Only converged local-QM-input trajectories can falsify the hypothesis; no automatic positive verdict is implemented."}
