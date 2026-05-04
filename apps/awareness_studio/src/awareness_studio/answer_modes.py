from typing import List

from awareness_studio.doc_schema import Chunk
from awareness_studio.prompts import SYSTEM_PROMPT, format_context, format_sources

_MODE_INSTRUCTIONS: dict = {
    "TEACH": """\
Use the TEACH template:
1. One-sentence framing of the topic
2. 3–7 bullet teaching points, each prefixed with a role label
3. 1 concrete modern example
4. 1 practice handle (what to do right now, ≤ 3 steps)
5. 1 falsifier / confound (scientist constraint — how you could be wrong or self-deceiving)
""",
    "EXPLAIN": """\
Use the EXPLAIN template:
- **Definition (plain)**: one sentence for a non-practitioner
- **Definition (operational)**: what to observe/measure to know it is occurring
- **Distinctions**: at least 2 "A vs B" pairs that clarify the concept
- **Common confusions**: at least 2 mistakes people make with this concept
- Role labels + EBT confidence for all doctrinal claims
""",
    "ELABORATE": """\
Use the ELABORATE template:
- **Short summary** (2–3 sentences)
- ### Direct teaching (EBT-weighted)
  Doctrinal claims with [Direct teaching] labels
- ### Method-synthesis
  Practice-oriented translations with [Method-synthesis] labels
- ### Hypotheses
  Speculative extensions with [Hypothesis] labels
- **Guardrails**: what NOT to conclude from this material
""",
    "MATRIX": """\
Use the MATRIX template (fill every field exactly):

**Doctrine / Claim / Practice:**
**Mechanism:**
**Operationalization:**
**Telemetry proxy:**
**Discriminator:**
""",
    "CARD": """\
Use the CARD (Evidence Card) template:

**Card ID:** (generate a slug from the topic)
**Text:** (≤ 80 words — the core teaching)
**EBT confidence:** (high / medium / low / none)
**Primary quote:** (sutta reference if applicable, else "N/A")
**Claim statement:**
**Operationalization (gain / latch / loop mapping):**
**Telemetry proxy:**
**Discriminator / confounds:**
""",
    "CANONICAL": """\
Use the CANONICAL template:

**Candidate paragraph** (≤ 120 words, role labels embedded inline)
**Target section** (suggest 1 exact heading to insert under)
**Replaces** (what existing text this would replace, if any)
""",
}


def build_chat_prompt(
    question: str, mode: str, chunks: List[Chunk]
) -> tuple[str, str]:
    mode_upper = mode.upper()
    mode_instr = _MODE_INSTRUCTIONS.get(mode_upper, _MODE_INSTRUCTIONS["EXPLAIN"])
    context = format_context(chunks)
    sources = format_sources(chunks)

    system = SYSTEM_PROMPT
    user = f"""\
CONTEXT FROM KNOWLEDGE BASE:
{context}

---
QUESTION: {question}

RESPONSE FORMAT:
{mode_instr}

Embed role labels ([Direct teaching] / [Method-synthesis] / [Hypothesis]) inline with every claim.
Append the sources section below verbatim as the final section.

{sources}
"""
    return system, user
