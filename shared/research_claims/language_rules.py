"""Deterministic language-rule catalog.

Patterns are lowercase substring matches. Rule application is a function of
claim text plus declared metadata only. Matching never edits ``text``.
"""

from __future__ import annotations

from typing import Iterable

GLOBAL_PROHIBITED_PHRASES: tuple[str, ...] = (
    "proves consciousness",
    "proof of consciousness",
    "consciousness proven",
    "consciousness solved",
    "proves biological quantum coherence",
    "evidence of biological quantum coherence",
    "biological confirmation",
    "confirms biology",
    "confirms a biological mechanism",
    "ontology solved",
    "final theory",
    "toe validated",
    "q equals self",
    "q equals soul",
)

PROXY_AS_FORMAL_PHRASES: tuple[str, ...] = (
    "formal bayes factor",
    "formal k",
    "bayes factor k",
    "marginal likelihood",
    "k > 100 pass",
    "k>100",
)

BETA1_CONSCIOUSNESS_PHRASES: tuple[str, ...] = (
    "proof of consciousness",
    "proves consciousness",
    "beta-1 proves consciousness",
    "beta1 proves consciousness",
    "graph beta-1 proves consciousness",
    "consciousness confirmed",
)

GRAPH_AS_SPATIAL_PHRASES: tuple[str, ...] = (
    "spatial topological charge",
    "spatial winding",
    "topological charge",
    "spatial_winding_q",
)

EP_AS_BIOLOGICAL_TRANSITION_PHRASES: tuple[str, ...] = (
    "biological phase transition",
    "phase transition in vivo",
    "biological exceptional point",
    "neural phase transition",
)

DECOHERENCE_AS_BIO_QUANTUM_PHRASES: tuple[str, ...] = (
    "biological quantum coherence",
    "quantum coherence in vivo",
    "evidence of biological quantum",
    "proves quantum coherence",
    "confirms quantum coherence",
)

SYNTHETIC_BIOLOGY_PHRASES: tuple[str, ...] = (
    "biological confirmation",
    "confirms biology",
    "empirical confirmation",
    "validates the biological",
    "in vivo confirmation",
    "proves the mechanism",
)

CERTAINTY_ERASURE_PHRASES: tuple[str, ...] = (
    "without limitation",
    "no uncertainty",
    "definitively proves",
    "unambiguously confirms",
    "settled fact that consciousness",
)

_NEGATION_PREFIXES: tuple[str, ...] = (
    "not ",
    "not a ",
    "not an ",
    "cannot be called ",
    "cannot be ",
    "is not ",
    "is not a ",
    "is not an ",
    "never ",
    "no ",
    "without ",
    "rather than ",
    "instead of ",
    "\u2260 ",
    "!= ",
)


def _is_negated(text_l: str, index: int) -> bool:
    window = text_l[max(0, index - 28) : index]
    return any(window.endswith(prefix) for prefix in _NEGATION_PREFIXES)


def _contains_any(text_l: str, phrases: Iterable[str]) -> list[str]:
    hits = []
    for phrase in phrases:
        start = 0
        while True:
            index = text_l.find(phrase, start)
            if index < 0:
                break
            if not _is_negated(text_l, index):
                hits.append(phrase)
                break
            start = index + len(phrase)
    return hits


def scan_text(text: str) -> dict[str, list[str]]:
    text_l = (text or "").lower()
    return {
        "global_prohibited": _contains_any(text_l, GLOBAL_PROHIBITED_PHRASES),
        "proxy_as_formal": _contains_any(text_l, PROXY_AS_FORMAL_PHRASES),
        "beta1_consciousness": _contains_any(text_l, BETA1_CONSCIOUSNESS_PHRASES),
        "graph_as_spatial": _contains_any(text_l, GRAPH_AS_SPATIAL_PHRASES),
        "ep_as_biological_transition": _contains_any(text_l, EP_AS_BIOLOGICAL_TRANSITION_PHRASES),
        "decoherence_as_bio_quantum": _contains_any(text_l, DECOHERENCE_AS_BIO_QUANTUM_PHRASES),
        "synthetic_biology": _contains_any(text_l, SYNTHETIC_BIOLOGY_PHRASES),
        "certainty_erasure": _contains_any(text_l, CERTAINTY_ERASURE_PHRASES),
    }


def mentions_beta1(text: str) -> bool:
    text_l = (text or "").lower()
    return any(token in text_l for token in ("beta-1", "beta1", "\u03b21", "graph beta"))


def mentions_graph_beta1(text: str) -> bool:
    text_l = (text or "").lower()
    return any(
        token in text_l
        for token in ("graph beta-1", "graph beta1", "cycle rank", "graph \u03b21")
    )


def mentions_proxy_k(text: str) -> bool:
    text_l = (text or "").lower()
    return any(
        token in text_l
        for token in ("proxy k", "proxy bayes", "k_proxy", "bayes_factor_proxy", "aic", "bic")
    )


def mentions_exceptional_point(text: str) -> bool:
    text_l = (text or "").lower()
    return any(token in text_l for token in ("exceptional point", " fitted ep", "fitted ep", "ep fit"))


def mentions_decoherence_simulation(text: str) -> bool:
    text_l = (text or "").lower()
    return any(
        token in text_l
        for token in ("decoherence simulation", "simulated decoherence", "synthetic decoherence")
    )
