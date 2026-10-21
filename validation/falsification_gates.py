"""Falsification diagnostic evaluation gates and Bayesian evidence bounds.

Enforces:
- Non-static Bayesian evidence thresholding (K > 100).
- Separation of model-dependent numerical parameters from empirical biological claims.
- Inviolable guardrail compliance: no clinical, consciousness, or TOE claims.
"""
from __future__ import annotations

import math
from typing import Any, Dict


def evaluate_falsification_gate(
    bayes_factor: float,
    prior_odds: float = 1.0,
    threshold_k: float = 100.0,
    target_metric: str = "simulation_gap_divergence",
) -> Dict[str, Any]:
    """Evaluate a formal Bayesian falsification gate on simulation evidence.

    Args:
        bayes_factor: Marginal likelihood ratio B_10.
        prior_odds: Prior probability ratio P(H1) / P(H0).
        threshold_k: Decisive threshold (default K=100 Jeffreys/Kass-Raftery standard).
        target_metric: Name of the evaluated parameter or metric.

    Returns:
        Structured evaluation dictionary with verdict and guardrail disclaimers.
    """
    if not math.isfinite(bayes_factor) or bayes_factor < 0.0:
        raise ValueError(f"bayes_factor must be finite and non-negative; got {bayes_factor}")
    if not math.isfinite(prior_odds) or prior_odds <= 0.0:
        raise ValueError(f"prior_odds must be finite and positive; got {prior_odds}")

    posterior_odds = bayes_factor * prior_odds

    if bayes_factor >= threshold_k:
        verdict = "DECISIVE_SUPPORT"
        falsification_status = "HYPOTHESIS_SUPPORTED"
    elif bayes_factor <= 1.0 / threshold_k:
        verdict = "DECISIVE_FALSIFICATION"
        falsification_status = "HYPOTHESIS_FALSIFIED"
    elif bayes_factor <= 1.0:
        verdict = "NOT_SUPPORTED"
        falsification_status = "NULL_FAVORED"
    else:
        verdict = "INCONCLUSIVE"
        falsification_status = "AMBIGUOUS"

    return {
        "target_metric": target_metric,
        "bayes_factor": float(bayes_factor),
        "prior_odds": float(prior_odds),
        "posterior_odds": float(posterior_odds),
        "threshold_k": float(threshold_k),
        "verdict": verdict,
        "falsification_status": falsification_status,
        "guardrails": {
            "no_clinical_claims": True,
            "no_consciousness_claim": True,
            "no_toe_claim": True,
            "interpretation": (
                "Decay rates and persistence metrics are properties of the finite mathematical "
                "model only; they do not constitute biological evidence or clinical diagnostics."
            ),
        },
    }
