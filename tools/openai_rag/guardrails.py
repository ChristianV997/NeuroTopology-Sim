from __future__ import annotations

BLOCKED = (
    "soul is real", "theory validated", "qabs proves liberation", "q proves consciousness",
    "fdress proves suffering", "trauma deletion", "instant arhat", "guaranteed healing",
    "unresponsive means unconscious", "sedated means no experience", "empirical proof from tol text",
    "ontology promotion",
)

SAFE_APPEND = "Use candidate telemetry/hypothesis framing only; requires real execution, controls, and is not directly measured."

def apply_guardrails(text: str) -> tuple[str, list[str]]:
    t = text
    hits = [p for p in BLOCKED if p in text.lower()]
    if hits:
        t = f"Blocked unsafe ontology/clinical certainty language. {SAFE_APPEND}"
    return t, hits

def response_envelope(answer: str, source_artifacts: list[str], claim_scope: str = "hypothesis", evidence_state: str = "not_directly_measured") -> dict:
    safe, hits = apply_guardrails(answer)
    return {
        "answer": safe,
        "citations": source_artifacts,
        "source_artifacts": source_artifacts,
        "claim_scope": claim_scope,
        "evidence_state": evidence_state,
        "guardrails_applied": hits,
        "limitations": ["No empirical proof from ToL text.", "No clinical claims.", "Requires controlled real execution."],
    }
