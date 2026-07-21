#!/usr/bin/env python3
"""Orchestrator stage: Fable reasoning over executed results.

Integrates Fable 5 for:
1. Metric interpretation (classifying topological states)
2. Adaptive hypothesis generation (proposing novel contrasts)
3. RAG-grounded synthesis (grounding in evidence)

This stage runs after `execute` and before `validate`, enriching
experiment results with data-driven reasoning.

Usage:
    stage = FableReasoningStage(orchestrator_config)
    result = stage.run(previous_stage_output)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

from llm_reasoning.fable_interpreter import FableInterpreter, MetricsContext, FastMetricBatchInterpreter
from llm_reasoning.hypothesis_generator import HypothesisGenerator
from llm_reasoning.rag_grounded_synthesis import RAGGroundedSynthesizer


@dataclass
class FableReasoningOutput:
    """Output from Fable reasoning stage."""
    stage_name: str = "fable_reasoning"
    status: str = "ok"  # ok or error
    error: Optional[str] = None

    # Interpretations
    metric_interpretations: List[Dict[str, Any]] = field(default_factory=list)
    state_classifications: List[str] = field(default_factory=list)

    # Hypothesis generation
    generated_hypotheses: List[Dict[str, Any]] = field(default_factory=list)

    # Evidence synthesis
    rag_syntheses: List[Dict[str, Any]] = field(default_factory=list)

    # Summary
    reasoning_summary: str = ""
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "error": self.error,
            "metric_interpretations": self.metric_interpretations,
            "state_classifications": self.state_classifications,
            "generated_hypotheses": self.generated_hypotheses,
            "rag_syntheses": self.rag_syntheses,
            "reasoning_summary": self.reasoning_summary,
            "recommendations": self.recommendations,
        }


class FableReasoningStage:
    """Orchestrator stage for Fable-powered reasoning."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, output_dir: Optional[Path] = None):
        """Initialize Fable reasoning stage.

        Args:
            config: Configuration dict (optional)
            output_dir: Output directory for artifacts
        """
        self.config = config or {}
        self.output_dir = Path(output_dir or "artifacts/fable_reasoning")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Fable components
        self.interpreter = FableInterpreter(model="claude-fable-5")
        self.batch_interpreter = FastMetricBatchInterpreter(model="claude-fable-5")
        self.hypothesis_generator = HypothesisGenerator(model="claude-fable-5")
        self.synthesizer = RAGGroundedSynthesizer(model="claude-fable-5", retriever=None)

    def run(self, previous_results: Dict[str, Any]) -> FableReasoningOutput:
        """Run Fable reasoning stage.

        Args:
            previous_results: Output from `execute` stage (metrics, embeddings, etc.)

        Returns:
            FableReasoningOutput with interpretations and hypotheses
        """
        output = FableReasoningOutput()

        try:
            # Extract metrics from previous stage
            metrics = previous_results.get("metrics", {})
            embeddings = previous_results.get("embeddings", {})

            if not metrics:
                output.status = "skip"
                output.reasoning_summary = "No metrics found in previous stage; skipping Fable reasoning."
                return output

            # Stage 1: Interpret topological metrics
            output.metric_interpretations = self._interpret_metrics(metrics)
            output.state_classifications = [
                interp.get("state", "unknown") for interp in output.metric_interpretations
            ]

            # Stage 2: Generate adaptive hypotheses
            output.generated_hypotheses = self._generate_hypotheses(metrics, output.state_classifications)

            # Stage 3: RAG-grounded synthesis
            output.rag_syntheses = self._synthesize_with_rag(output.generated_hypotheses)

            # Stage 4: Recommendations
            output.recommendations = self._generate_recommendations(output.generated_hypotheses)

            # Summary
            output.reasoning_summary = self._create_summary(output)

            # Save artifacts
            self._save_artifacts(output)

        except Exception as e:
            output.status = "error"
            output.error = str(e)

        return output

    def _interpret_metrics(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Interpret topological metrics using Fable."""
        interpretations = []

        for metric_key, metric_value in metrics.items():
            if isinstance(metric_value, dict):
                # Extract Q, Qabs, defect_density
                q = metric_value.get("Q", 0.0)
                qabs = metric_value.get("Qabs", 0.0)
                defect_density = metric_value.get("defect_density", 0.0)

                context = MetricsContext(
                    Q=float(q),
                    Qabs=float(qabs),
                    defect_density=float(defect_density),
                    dataset=metric_value.get("dataset"),
                    drug=metric_value.get("drug"),
                    timepoint=metric_value.get("timepoint"),
                    subject_id=metric_value.get("subject_id"),
                )

                interpretation = self.interpreter.classify_state(context)
                interpretation["metric_key"] = metric_key
                interpretations.append(interpretation)

        return interpretations

    def _generate_hypotheses(self, metrics: Dict[str, Any], states: List[str]) -> List[Dict[str, Any]]:
        """Generate adaptive hypotheses from metrics."""
        hypotheses = []

        # Look for metric transitions or patterns
        for i, (metric_key, metric_value) in enumerate(metrics.items()):
            if isinstance(metric_value, dict) and "trajectory" in metric_value:
                traj = metric_value["trajectory"]
                dataset = metric_value.get("dataset", "unknown")
                condition = metric_value.get("drug", metric_value.get("condition", "unknown"))
                current_state = states[i] if i < len(states) else ""

                hypothesis = self.hypothesis_generator.propose_from_metrics(
                    metric_trajectory=traj,
                    dataset=dataset,
                    condition=condition,
                    current_state=current_state,
                )

                if hypothesis:
                    hypotheses.append({
                        "claim": hypothesis.claim,
                        "mechanism": hypothesis.mechanism,
                        "predicted_signature": hypothesis.predicted_signature,
                        "discriminator": hypothesis.discriminator,
                        "confidence": hypothesis.confidence,
                    })

        return hypotheses

    def _synthesize_with_rag(self, hypotheses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Synthesize hypotheses with RAG grounding."""
        syntheses = []

        for hyp in hypotheses:
            claim = hyp.get("claim", "")
            keywords = [hyp.get("mechanism", ""), hyp.get("predicted_signature", "")]

            synthesis = self.synthesizer.synthesize_hypothesis(
                hypothesis=claim,
                query_keywords=keywords,
                top_k=3,
            )

            if synthesis:
                syntheses.append({
                    "hypothesis": synthesis.hypothesis,
                    "supporting_evidence": synthesis.supporting_evidence,
                    "contradictory_evidence": synthesis.contradictory_evidence,
                    "gaps": synthesis.gaps,
                    "report": synthesis.report_paragraph,
                    "citations": synthesis.citations,
                })

        return syntheses

    def _generate_recommendations(self, hypotheses: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations for next experiments."""
        recommendations = []

        for hyp in hypotheses:
            if hyp.get("confidence", 0) >= 7:
                discriminator = hyp.get("discriminator", "")
                if discriminator:
                    recommendations.append(f"Test discriminator: {discriminator}")

        # Add general recommendations
        if not recommendations:
            recommendations.append("Run follow-up validation across datasets")
            recommendations.append("Implement surrogate gate for learned metrics")

        return recommendations

    def _create_summary(self, output: FableReasoningOutput) -> str:
        """Create a text summary of Fable reasoning results."""
        lines = [
            f"Fable Reasoning Summary ({len(output.metric_interpretations)} metrics interpreted)",
            f"States identified: {', '.join(set(output.state_classifications))}",
            f"Hypotheses generated: {len(output.generated_hypotheses)}",
            f"Recommendations: {len(output.recommendations)}",
        ]

        if output.generated_hypotheses:
            top_hyp = output.generated_hypotheses[0]
            lines.append(f"Leading hypothesis: {top_hyp.get('claim', '')}")

        return "\n".join(lines)

    def _save_artifacts(self, output: FableReasoningOutput):
        """Save Fable reasoning artifacts to disk."""
        # Save JSON
        (self.output_dir / "fable_reasoning_output.json").write_text(
            json.dumps(output.to_dict(), indent=2)
        )

        # Save summary as markdown
        summary_md = [
            "# Fable Reasoning Results\n",
            f"Status: {output.status}\n",
            f"## Summary\n{output.reasoning_summary}\n",
            "## Metric Interpretations\n",
        ]

        for interp in output.metric_interpretations:
            summary_md.append(f"- {interp.get('metric_key', 'unknown')}: {interp.get('state', 'unknown')}")

        summary_md.extend([
            "\n## Generated Hypotheses\n",
        ])

        for i, hyp in enumerate(output.generated_hypotheses, 1):
            summary_md.append(f"{i}. {hyp.get('claim', '')}")
            summary_md.append(f"   Confidence: {hyp.get('confidence', 0)}/10")

        summary_md.extend([
            "\n## Recommendations\n",
        ])

        for rec in output.recommendations:
            summary_md.append(f"- {rec}")

        (self.output_dir / "fable_reasoning_summary.md").write_text("\n".join(summary_md))
