#!/usr/bin/env python3
"""RAG-grounded evidence synthesis: Fable reasons over retrieved context chunks.

Integrates with Awareness Studio's retrieval system (BM25/embedding index)
to ground Fable's hypothesis synthesis in actual evidence.

Usage:
    synthesizer = RAGGroundedSynthesizer()
    report = synthesizer.synthesize_hypothesis(
        hypothesis=hypothesis_obj,
        query_keywords=["psilocybin", "charge reversal"],
        top_k=5
    )
"""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from anthropic import Anthropic


@dataclass
class RetrievedChunk:
    """A chunk retrieved from the RAG index."""
    chunk_id: str
    text: str
    source_title: str
    source_path: str
    relevance_score: float


@dataclass
class GroundedSynthesis:
    """Fable's synthesis grounded in retrieved evidence."""
    hypothesis: str
    supporting_evidence: List[str]
    contradictory_evidence: List[str]
    gaps: List[str]
    report_paragraph: str
    citations: List[str]


class RAGGroundedSynthesizer:
    """Synthesize hypotheses using Fable + RAG evidence grounding."""

    SYNTHESIS_PROMPT_TEMPLATE = """You are a neuroscientist. Evaluate this hypothesis:

HYPOTHESIS:
{hypothesis}

RETRIEVED EVIDENCE (top-5 chunks):
{evidence_chunks}

In JSON format:
{{
  "supporting_evidence": ["list", "of", "supporting", "claims"],
  "contradictory_evidence": ["list", "of", "contradicting", "findings"],
  "gaps": ["list", "of", "unaddressed", "questions"],
  "citations": ["ref1", "ref2"],
  "report": "A 200-word paragraph synthesizing hypothesis + evidence with citations"
}}
Ensure citations reference specific evidence chunks above."""

    def __init__(self, model: str = "claude-fable-5", retriever = None):
        """Initialize synthesizer.

        Args:
            model: Fable model ID
            retriever: Optional retrieval function (queries RAG index)
                      Signature: retriever(query: str, top_k: int) -> List[RetrievedChunk]
        """
        self.client = Anthropic()
        self.model = model
        self.retriever = retriever

    def _format_evidence_chunks(self, chunks: List[RetrievedChunk]) -> str:
        """Format retrieved chunks for prompt context."""
        formatted = []
        for i, chunk in enumerate(chunks, 1):
            formatted.append(f"[{i}] {chunk.source_title} (score: {chunk.relevance_score:.2f})\n{chunk.text[:500]}")
        return "\n\n".join(formatted)

    def synthesize_hypothesis(self, hypothesis: str, query_keywords: List[str],
                             top_k: int = 5) -> Optional[GroundedSynthesis]:
        """Synthesize a hypothesis grounded in retrieved evidence.

        Args:
            hypothesis: Hypothesis text (claim + mechanism)
            query_keywords: Keywords to retrieve relevant evidence
            top_k: Number of evidence chunks to retrieve

        Returns:
            GroundedSynthesis with report and evidence mapping
        """
        # Retrieve evidence if retriever is available
        if self.retriever:
            query = " ".join(query_keywords)
            chunks = self.retriever(query, top_k=top_k)
            evidence_text = self._format_evidence_chunks(chunks)
        else:
            chunks = []
            evidence_text = "(No RAG system available; using hypothesis alone)"

        prompt = self.SYNTHESIS_PROMPT_TEMPLATE.format(
            hypothesis=hypothesis,
            evidence_chunks=evidence_text,
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            response_text = message.content[0].text
            data = json.loads(response_text)

            return GroundedSynthesis(
                hypothesis=hypothesis,
                supporting_evidence=data.get("supporting_evidence", []),
                contradictory_evidence=data.get("contradictory_evidence", []),
                gaps=data.get("gaps", []),
                report_paragraph=data.get("report", ""),
                citations=data.get("citations", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Synthesis failed: {e}")
            return None

    def batch_synthesize(self, hypotheses: List[str],
                        keywords_list: List[List[str]]) -> List[Optional[GroundedSynthesis]]:
        """Synthesize multiple hypotheses.

        Args:
            hypotheses: List of hypothesis strings
            keywords_list: List of keyword lists (one per hypothesis)

        Returns:
            List of GroundedSynthesis objects
        """
        results = []
        for hyp, keywords in zip(hypotheses, keywords_list):
            synthesis = self.synthesize_hypothesis(hyp, keywords)
            results.append(synthesis)
        return results

    def generate_evidence_report(self, syntheses: List[GroundedSynthesis]) -> str:
        """Generate a comprehensive evidence report from multiple syntheses.

        Args:
            syntheses: List of GroundedSynthesis results

        Returns:
            Markdown-formatted evidence report
        """
        report_lines = [
            "# Hypothesis Evidence Report\n",
            f"Generated using Fable 5 + RAG grounding\n",
            "---\n",
        ]

        for i, synthesis in enumerate(syntheses, 1):
            report_lines.extend([
                f"## Hypothesis {i}",
                f"**Claim:** {synthesis.hypothesis}\n",
                f"### Supporting Evidence",
                "\n".join(f"- {e}" for e in synthesis.supporting_evidence) + "\n",
                f"### Contradictory Evidence",
                "\n".join(f"- {e}" for e in synthesis.contradictory_evidence) + "\n",
                f"### Gaps to Address",
                "\n".join(f"- {g}" for g in synthesis.gaps) + "\n",
                f"### Synthesis",
                synthesis.report_paragraph + "\n",
                f"**Citations:** {', '.join(synthesis.citations)}\n",
                "---\n",
            ])

        return "\n".join(report_lines)
