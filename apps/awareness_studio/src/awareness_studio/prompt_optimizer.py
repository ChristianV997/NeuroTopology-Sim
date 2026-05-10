"""
Prompt optimization hooks (TASK-4).

Controlled by PROMPT_OPTIMIZER env var:
  none       — pass-through, no modification (default)
  dspy_stub  — placeholder scorer + logged no-op optimizer

To wire in real DSPy later: subclass PromptOptimizerBase and
register it in _get_optimizer().
"""
import logging
from typing import List, Tuple

from awareness_studio import config
from awareness_studio.doc_schema import Chunk

logger = logging.getLogger(__name__)

PROMPT_OPTIMIZER: str = config.PROMPT_OPTIMIZER


# ── Scoring helpers ───────────────────────────────────────────────────────────

def score_role_label_compliance(response: str) -> float:
    """
    Heuristic score in [0, 1]: fraction of sentences that carry a role label.

    Labels counted: [Direct teaching], [Method-synthesis], [Hypothesis].
    Returns 0.0 for empty responses.
    """
    labels = ("[Direct teaching]", "[Method-synthesis]", "[Hypothesis]")
    sentences = [s.strip() for s in response.split(".") if s.strip()]
    if not sentences:
        return 0.0
    labelled = sum(1 for s in sentences if any(lbl in s for lbl in labels))
    return labelled / len(sentences)


def score_sources_present(response: str) -> float:
    """1.0 if '## Sources used' section is present, else 0.0."""
    return 1.0 if "## Sources used" in response else 0.0


def score_no_certainty_leak(response: str) -> float:
    """1.0 if none of the forbidden certainty phrases appear, else 0.0."""
    forbidden = ("I am certain", "it is proven", "proven fact", "we know for certain")
    lowered = response.lower()
    return 0.0 if any(f.lower() in lowered for f in forbidden) else 1.0


def score_response(response: str) -> dict:
    """Aggregate scoring dict used by the optimizer and for logging."""
    return {
        "role_label_compliance": score_role_label_compliance(response),
        "sources_present": score_sources_present(response),
        "no_certainty_leak": score_no_certainty_leak(response),
    }


# ── Optimizer base + implementations ─────────────────────────────────────────

class PromptOptimizerBase:
    """Thin wrapper around build_chat_prompt — subclass to inject optimization."""

    def optimize(
        self,
        question: str,
        mode: str,
        chunks: List[Chunk],
    ) -> Tuple[str, str]:
        """Return (system_prompt, user_prompt). Default: unmodified."""
        from awareness_studio.answer_modes import build_chat_prompt
        return build_chat_prompt(question, mode, chunks)


class PassthroughOptimizer(PromptOptimizerBase):
    """No-op — returns prompt unchanged."""


class DSPyStubOptimizer(PromptOptimizerBase):
    """
    Placeholder for DSPy integration.

    Logs the score of the current prompt structure so future training
    runs have telemetry to optimize against. Does not modify prompts.
    """

    def optimize(
        self,
        question: str,
        mode: str,
        chunks: List[Chunk],
    ) -> Tuple[str, str]:
        system, user = super().optimize(question, mode, chunks)
        logger.debug(
            "[DSPy stub] prompt assembled — mode=%s question=%.60s…",
            mode, question,
        )
        return system, user

    def score_and_log(self, response: str, question: str, mode: str) -> dict:
        scores = score_response(response)
        logger.info(
            "[DSPy stub] scores — mode=%s role_label=%.2f sources=%.1f certainty_ok=%.1f  q=%.50s…",
            mode,
            scores["role_label_compliance"],
            scores["sources_present"],
            scores["no_certainty_leak"],
            question,
        )
        return scores


# ── Factory ───────────────────────────────────────────────────────────────────

def _get_optimizer() -> PromptOptimizerBase:
    if PROMPT_OPTIMIZER == "dspy_stub":
        return DSPyStubOptimizer()
    if PROMPT_OPTIMIZER == "none":
        return PassthroughOptimizer()
    logger.warning(
        "Unknown PROMPT_OPTIMIZER=%r — falling back to passthrough.", PROMPT_OPTIMIZER
    )
    return PassthroughOptimizer()


_optimizer: PromptOptimizerBase = _get_optimizer()


def get_optimized_prompt(
    question: str, mode: str, chunks: List[Chunk]
) -> Tuple[str, str]:
    """Public entry point used by chat_cli and book_generator."""
    return _optimizer.optimize(question, mode, chunks)
