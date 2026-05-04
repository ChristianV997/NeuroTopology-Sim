"""CLI: python -m awareness_studio.book_generator --quadrant q1 --chapter "X" --words 1200"""
import argparse
import sys
from typing import List

from awareness_studio import config
from awareness_studio.doc_schema import Chunk
from awareness_studio.index_build import build_index, get_or_build_index
from awareness_studio.prompts import SYSTEM_PROMPT, format_context, format_sources

_QUADRANT_VOICES: dict = {
    "q1": {
        "name": "Autoayuda práctica (Q1)",
        "voice": (
            "Warm, simple, story-first. Tone like El poder del ahora. "
            "No Pali jargon in main text (footnotes only). "
            "Lead with a short human story (1–2 paragraphs). "
            "One idea per paragraph. Practices feel doable in 1–5 minutes. "
            "End sections with a gentle invitation, never a command."
        ),
    },
    "q2": {
        "name": "Theravāda avanzado EBT (Q2)",
        "voice": (
            "Dense, technical, Pali-precise. Cite suttas by name and number. "
            "EBT-weighted claims with explicit confidence labels. "
            "Structure each teaching: doctrine → phenomenological observation → "
            "practice instruction → debugging common mistakes. "
            "Distinguish vedanā / taṇhā / upādāna with precision."
        ),
    },
    "q3": {
        "name": "Escépticos ciencia-pop (Q3)",
        "voice": (
            "Skeptical, rational, youth-accessible. Use information-theory and "
            "neuroscience analogies: loops, signals, prediction error, compression, "
            "latency, bitrate. No supernatural claims. Samsara = 'recursive loops'. "
            "Tone: curious engineer explaining a mind-hack. Short punchy sentences. "
            "Modern metaphors: feed, algorithm, signal/noise, overfitting."
        ),
    },
    "q4": {
        "name": "Liberation Engineering PhD (Q4)",
        "voice": (
            "Rigorous, formal, falsifiable. State claims as testable hypotheses. "
            "Use notation where useful: v_t (valence), g_t (gain), ℓ_t (latch), "
            "π(a|s) (policy). Every claim needs a falsifier or operationalization. "
            "Reference research designs: N-of-1, EMA, response inhibition paradigms. "
            "Flag speculative bridges to neuroscience explicitly."
        ),
    },
}

_BOOK_SYSTEM_ADDON = """
## Book generation contract

1. Follow the 6-element chapter matrix in this exact order:
   a) Una verdad humana — what happens inside the reader
   b) Una explicación sencilla — the mechanism that sustains it
   c) Una práctica corta — 1–5 min exercise
   d) Qué cambia si lo haces 7 días — one concrete observable signal
   e) Cómo evitar engañarte — release vs suppression vs bypass

2. Address the "Preguntas duras" (hard questions the book must answer):
   - How to live well when everything changes and nothing can be fully controlled?
   - How to exit the desire–fear–reaction loop that repeats endlessly?
   - What is worth pursuing if nothing is permanent?
   - How to look at samsara without falling into despair?

3. Samsara-as-perspective framing: the blood/tears/oceans image is a traditional
   pedagogical tool for contextualizing impermanence. Present it as a perspective
   (tag [Direct teaching] if doctrinal), NEVER as a literal factual claim.

4. Embed role labels [Direct teaching] / [Method-synthesis] / [Hypothesis] inline.

5. The chapter MUST end with these three sections:
   ### Practices
   (3–5 numbered practice exercises)

   ### Common confusions
   (3 numbered confusions people have with this topic)

   ### Falsifiers — when you might be self-deceiving
   (3 numbered signs that you are suppressing, bypassing, or fooling yourself)
"""

_QUADRANT_EXTRA_QUERIES: dict = {
    "q1": "soltar práctica historia cotidiano simple",
    "q2": "vedana tanha upadana satipatthana EBT sutta",
    "q3": "loops señal algoritmo ciclo predicción información",
    "q4": "mecanismo hipótesis falsable métrica operacionalización",
}


def build_book_prompt(
    quadrant: str, chapter: str, words: int, chunks: List[Chunk]
) -> tuple[str, str]:
    q_info = _QUADRANT_VOICES.get(quadrant, _QUADRANT_VOICES["q1"])
    context = format_context(chunks)
    sources = format_sources(chunks)
    system = SYSTEM_PROMPT + _BOOK_SYSTEM_ADDON
    user = f"""\
CONTEXT FROM KNOWLEDGE BASE:
{context}

---
TASK: Write a complete book chapter draft.

Quadrant: **{q_info['name']}**
Chapter title: "{chapter}"
Target length: approximately {words} words
Voice / style: {q_info['voice']}

Write the full chapter now. Use the 6-element matrix. Embed role labels inline.
End with the Practices, Common confusions, and Falsifiers sections.

{sources}
"""
    return system, user


def run_book_generator(
    quadrant: str, chapter: str, words: int, stream: bool = False
) -> str:
    index = get_or_build_index()
    extra = _QUADRANT_EXTRA_QUERIES.get(quadrant, "")
    query = f"{chapter} {extra}"
    results = index.retrieve(query, k=10)

    quadrant_kind = f"book_seed_{quadrant}" if quadrant in _QUADRANT_VOICES else "other"
    extra_results = index.retrieve(chapter, k=20)
    extra_chunks = [
        c for c, _ in extra_results
        if c.source_kind in ("book_system", quadrant_kind)
    ]

    seen: set = set()
    deduped: List[Chunk] = []
    for c in [c for c, _ in results] + extra_chunks:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            deduped.append(c)

    from awareness_studio.llm_client import get_llm_client
    client = get_llm_client()
    system, user = build_book_prompt(quadrant, chapter, words, deduped)

    if stream:
        parts = []
        for token in client.complete_stream(system, user):
            print(token, end="", flush=True)
            parts.append(token)
        print()
        return "".join(parts)

    return client.complete(system, user)


def main() -> None:
    parser = argparse.ArgumentParser(description="Awareness Studio — Book Generator")
    parser.add_argument("--quadrant", choices=list(_QUADRANT_VOICES), required=True)
    parser.add_argument("--chapter", required=True, help="Chapter title")
    parser.add_argument("--words", type=int, default=1200, help="Target word count")
    parser.add_argument(
        "--stream", action="store_true",
        help="Stream output tokens to stdout",
    )
    parser.add_argument("--build-index", action="store_true", help="Force rebuild index first")
    args = parser.parse_args()

    if args.build_index:
        build_index()
        print("[index rebuilt]", file=sys.stderr)

    if args.stream:
        run_book_generator(args.quadrant, args.chapter, args.words, stream=True)
    else:
        result = run_book_generator(args.quadrant, args.chapter, args.words)
        print(result)


if __name__ == "__main__":
    main()
