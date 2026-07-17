#!/usr/bin/env python3
"""Fable 5 metric interpretation: fast topology reasoning over embeddings and metrics.

Interprets topological state from raw metrics (Q, Qabs, defect density, etc.)
and produces state classifications with confidence scores.

Usage:
    interpreter = FableInterpreter()
    state_label = interpreter.classify_state(q=1.5, qabs=2.0, defect_density=0.1)
    # Returns: {"state": "coherent_vortex", "confidence": 0.92, "reasoning": "..."}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import json

from anthropic import Anthropic


@dataclass
class MetricsContext:
    """Container for topological metrics and context."""
    Q: float
    Qabs: float
    defect_density: float
    dataset: str | None = None
    drug: str | None = None
    timepoint: str | None = None
    subject_id: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for prompt formatting."""
        return {
            "Q": f"{self.Q:.3f}",
            "Qabs": f"{self.Qabs:.3f}",
            "defect_density": f"{self.defect_density:.4f}",
            "dataset": self.dataset or "unknown",
            "drug": self.drug or "N/A",
            "timepoint": self.timepoint or "unknown",
            "subject_id": self.subject_id or "unknown",
        }


class FableInterpreter:
    """Interpret topological metrics using Fable 5 for fast, accurate reasoning."""

    # State classification prompt (minimal, efficient)
    CLASSIFY_PROMPT_TEMPLATE = """Given topological metrics from neuroimaging data:
- Q (signed charge): {Q}
- Qabs (absolute charge): {Qabs}
- Defect density: {defect_density}
- Dataset: {dataset}, Drug: {drug}, Timepoint: {timepoint}

Classify the topological state in ≤50 words:
1. State (coherent_vortex | turbulent_defect_sea | intermediate | noise)
2. Confidence (1-10 scale)
3. Key metric constraint
Format as JSON only."""

    # Trajectory interpretation prompt
    TRAJECTORY_PROMPT_TEMPLATE = """Interpret this topological trajectory across timepoints:
{trajectory}

In ≤100 words:
1. Overall pattern (e.g., "acute drop with recovery")
2. Most significant transition
3. Comparison to expected baseline
Format as JSON only."""

    def __init__(self, model: str = "claude-fable-5", temperature: float = 0.3):
        """Initialize Fable interpreter.

        Args:
            model: Model ID (default: claude-fable-5)
            temperature: Temperature for deterministic reasoning (default: 0.3)
        """
        self.client = Anthropic()
        self.model = model
        self.temperature = temperature

    def classify_state(self, metrics: MetricsContext) -> Dict[str, Any]:
        """Classify topology state from metrics using Fable.

        Args:
            metrics: MetricsContext with Q, Qabs, defect_density, etc.

        Returns:
            dict with state, confidence, reasoning
        """
        prompt = self.CLASSIFY_PROMPT_TEMPLATE.format(**metrics.to_dict())

        message = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            temperature=self.temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        # Parse response as JSON
        try:
            response_text = message.content[0].text
            result = json.loads(response_text)
            result["raw_response"] = response_text
            return result
        except (json.JSONDecodeError, IndexError) as e:
            return {
                "state": "parse_error",
                "confidence": 0,
                "reasoning": str(e),
                "raw_response": message.content[0].text if message.content else "",
            }

    def interpret_trajectory(self, metric_trajectory: list[float],
                            timepoints: list[str],
                            context: str = "") -> Dict[str, Any]:
        """Interpret a time series of metrics across conditions/timepoints.

        Args:
            metric_trajectory: list of metric values over time
            timepoints: list of timepoint labels (e.g., ["baseline", "acute", "persist"])
            context: optional additional context

        Returns:
            dict with pattern, transitions, comparison
        """
        traj_str = "\n".join(
            f"{tp}: {val:.3f}" for tp, val in zip(timepoints, metric_trajectory)
        )

        if context:
            traj_str += f"\nContext: {context}"

        prompt = self.TRAJECTORY_PROMPT_TEMPLATE.format(trajectory=traj_str)

        message = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            temperature=self.temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        try:
            response_text = message.content[0].text
            result = json.loads(response_text)
            result["raw_response"] = response_text
            return result
        except (json.JSONDecodeError, IndexError) as e:
            return {
                "pattern": "parse_error",
                "raw_response": message.content[0].text if message.content else "",
            }

    def multi_turn_analysis(self, initial_metrics: MetricsContext,
                           follow_up_questions: list[str]) -> Dict[str, Any]:
        """Multi-turn conversation with Fable for deeper analysis.

        Args:
            initial_metrics: Starting metric context
            follow_up_questions: List of follow-up questions

        Returns:
            dict with conversation history and final synthesis
        """
        messages = []
        results = {}

        # Initial classification
        initial_prompt = self.CLASSIFY_PROMPT_TEMPLATE.format(**initial_metrics.to_dict())
        messages.append({"role": "user", "content": initial_prompt})

        for i, question in enumerate(follow_up_questions):
            # Get Fable response
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                temperature=self.temperature,
                messages=messages,
            )

            assistant_response = response.content[0].text
            messages.append({"role": "assistant", "content": assistant_response})
            results[f"response_{i}"] = assistant_response

            # Add next question
            messages.append({"role": "user", "content": question})

        # Final synthesis
        messages.append({
            "role": "user",
            "content": "Synthesize your findings into a brief topological summary (≤200 words)."
        })

        final_response = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=self.temperature,
            messages=messages,
        )

        results["synthesis"] = final_response.content[0].text
        results["conversation_length"] = len(messages)

        return results


class FastMetricBatchInterpreter:
    """Batch interpretation of multiple metric samples using Fable."""

    def __init__(self, model: str = "claude-fable-5"):
        self.interpreter = FableInterpreter(model=model)

    def interpret_batch(self, metrics_list: list[MetricsContext]) -> list[Dict[str, Any]]:
        """Interpret a batch of metric contexts (with caching).

        Args:
            metrics_list: List of MetricsContext objects

        Returns:
            List of interpretation results
        """
        results = []
        for i, metrics in enumerate(metrics_list):
            result = self.interpreter.classify_state(metrics)
            result["index"] = i
            results.append(result)

        return results
