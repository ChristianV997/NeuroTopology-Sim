#!/usr/bin/env python3
"""Fable 5 hypothesis generation: data-driven discovery of falsifiable topology claims.

Observes metric clusters and state transitions, then proposes novel hypotheses
about underlying mechanisms (e.g., "Psilocybin causes CEN charge reversal because...").

Usage:
    generator = HypothesisGenerator()
    hypothesis = generator.propose_from_metrics(
        metric_trajectory={"baseline": 1.0, "acute": -1.3, "persist": 0.3},
        dataset="ds006072",
        drug="psilocybin"
    )
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from anthropic import Anthropic


@dataclass
class Hypothesis:
    """A falsifiable hypothesis generated from metrics."""
    claim: str
    mechanism: str
    predicted_signature: str
    discriminator: str  # How to falsify
    confidence: float  # 1-10 scale
    justification: str


class HypothesisGenerator:
    """Generate falsifiable hypotheses from topological metrics using Fable."""

    HYPOTHESIS_PROMPT_TEMPLATE = """You are a neurotopologist. Given metric data:
Dataset: {dataset}
Drug/Condition: {condition}
Metric trajectory: {trajectory}
Current state: {current_state}

Propose ONE falsifiable hypothesis about the underlying topological mechanism.
Format (JSON only):
{{
  "claim": "One-sentence claim about mechanism",
  "mechanism": "How does this mechanism change topology?",
  "predicted_signature": "What observable metric signature would confirm this?",
  "discriminator": "How would we falsify this hypothesis?",
  "confidence": 7
}}
Keep response under 300 tokens."""

    CROSS_DATASET_PROMPT_TEMPLATE = """Compare metrics across datasets:
Dataset A ({dataset_a}):
  {trajectory_a}

Dataset B ({dataset_b}):
  {trajectory_b}

Both show similar patterns. Propose a hypothesis that explains the common mechanism
underlying both trajectories. Format as JSON with fields:
claim, mechanism, predicted_signature, discriminator, confidence."""

    def __init__(self, model: str = "claude-fable-5"):
        self.client = Anthropic()
        self.model = model

    def propose_from_metrics(self, metric_trajectory: Dict[str, float],
                            dataset: str, condition: str,
                            current_state: str = "") -> Optional[Hypothesis]:
        """Propose a hypothesis from a metric trajectory.

        Args:
            metric_trajectory: dict like {"baseline": 1.0, "acute": -1.3, "persist": 0.3}
            dataset: dataset name (e.g., "ds006072")
            condition: drug or condition name
            current_state: optional state classification from FableInterpreter

        Returns:
            Hypothesis object or None if generation fails
        """
        traj_str = ", ".join(f"{tp}={val:.2f}" for tp, val in metric_trajectory.items())

        prompt = self.HYPOTHESIS_PROMPT_TEMPLATE.format(
            dataset=dataset,
            condition=condition,
            trajectory=traj_str,
            current_state=current_state or "unknown",
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=0.3,  # Deterministic for reproducibility
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            response_text = message.content[0].text
            data = json.loads(response_text)

            return Hypothesis(
                claim=data.get("claim", ""),
                mechanism=data.get("mechanism", ""),
                predicted_signature=data.get("predicted_signature", ""),
                discriminator=data.get("discriminator", ""),
                confidence=float(data.get("confidence", 0)),
                justification=response_text,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Hypothesis generation failed: {e}")
            return None

    def propose_cross_dataset_hypothesis(self, trajectory_a: Dict[str, float],
                                        dataset_a: str,
                                        trajectory_b: Dict[str, float],
                                        dataset_b: str) -> Optional[Hypothesis]:
        """Propose a hypothesis explaining similar patterns across datasets.

        Args:
            trajectory_a: metric trajectory for dataset A
            dataset_a: name of dataset A
            trajectory_b: metric trajectory for dataset B
            dataset_b: name of dataset B

        Returns:
            Hypothesis explaining common mechanism
        """
        traj_a_str = ", ".join(f"{tp}={val:.2f}" for tp, val in trajectory_a.items())
        traj_b_str = ", ".join(f"{tp}={val:.2f}" for tp, val in trajectory_b.items())

        prompt = self.CROSS_DATASET_PROMPT_TEMPLATE.format(
            dataset_a=dataset_a,
            trajectory_a=traj_a_str,
            dataset_b=dataset_b,
            trajectory_b=traj_b_str,
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            response_text = message.content[0].text
            data = json.loads(response_text)

            return Hypothesis(
                claim=data.get("claim", ""),
                mechanism=data.get("mechanism", ""),
                predicted_signature=data.get("predicted_signature", ""),
                discriminator=data.get("discriminator", ""),
                confidence=float(data.get("confidence", 0)),
                justification=response_text,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Cross-dataset hypothesis generation failed: {e}")
            return None

    def batch_propose(self, trajectories: List[Dict[str, float]],
                     datasets: List[str],
                     conditions: List[str]) -> List[Optional[Hypothesis]]:
        """Generate hypotheses for a batch of metric trajectories.

        Args:
            trajectories: list of metric trajectory dicts
            datasets: list of dataset names
            conditions: list of condition labels

        Returns:
            List of Hypothesis objects (may contain None for failures)
        """
        results = []
        for traj, dataset, condition in zip(trajectories, datasets, conditions):
            hyp = self.propose_from_metrics(traj, dataset, condition)
            results.append(hyp)
        return results
