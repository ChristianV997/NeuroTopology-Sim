"""Language rules for mapping text.

This reuses the repository's claim scanners (``shared.research_claims.language_rules`` and
the Level-O ontology firewall) and adds three rule families they do not cover: equivalence
language, causal or mechanistic language, and wording that implies empirical support.

Matching is a conservative keyword screen. It is not a semantic review, so a clean result
does not show that a statement is sound.
"""
from __future__ import annotations

import re
from typing import Iterable

from sciencer_d.ontology.firewall import scan_text as ontology_firewall_scan
from shared.research_claims.language_rules import scan_text as shared_claim_scan

from .schema import TARGET_CONSTRUCT_PHRASES, THEORY_NAMESPACE_TERMS

# "X is Y" sameness claims. A mapping may not equate an electrode or a metric with a
# theoretical object, so these are never negation-exempt.
EQUIVALENCE_PHRASES: tuple[str, ...] = (
    "is equivalent to", "are equivalent to", "is identical to", "are identical to",
    "is the same as", "are the same as", "is literally", "are literally",
    "literal gauge", "is a gauge", "is the gauge", "is the self", "is the soul",
    "is the mechanism", "equals ", "equal to the",
)

# Causal and mechanistic framing. A mapping proposes a reading; it does not assert how
# a process works, so these are never negation-exempt either.
CAUSAL_PHRASES: tuple[str, ...] = (
    "causes", "caused by", "causal", "causally", "drives", "driven by", "mechanism",
    "mechanistic", "underlies", "underlying mechanism", "produces", "responsible for",
)

# Wording that presents a proposal as an established finding. Negated forms such as
# "not yet validated" are allowed, because they state the status accurately.
SUPPORT_PHRASES: tuple[str, ...] = (
    "confirm", "validat", "demonstrat", "prove", "establish", "evidence that",
    "shows that", "supports the", "support for", "empirically",
)

_NEGATION_PREFIXES: tuple[str, ...] = (
    "not ", "not yet ", "not a ", "not an ", "not the ", "no ", "never ", "without ", "un",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _negated(lowered: str, index: int) -> bool:
    window = lowered[max(0, index - 14) : index]
    return any(window.endswith(prefix) for prefix in _NEGATION_PREFIXES)


def _hits(lowered: str, phrases: Iterable[str], *, negation_allowed: bool) -> list[str]:
    found: list[str] = []
    for phrase in phrases:
        for match in re.finditer(r"\b" + re.escape(phrase), lowered):
            if negation_allowed and _negated(lowered, match.start()):
                continue
            found.append(phrase.strip())
            break
    return found


def scan_interpretation(text: str) -> dict[str, list[str]]:
    """Categorized hits for one piece of interpretation text. Empty lists mean no hits."""
    shared = shared_claim_scan(text)
    return {
        "equivalence": _hits(_normalize(text), EQUIVALENCE_PHRASES, negation_allowed=False),
        "causal_or_mechanism": _hits(_normalize(text), CAUSAL_PHRASES, negation_allowed=False),
        "empirical_support": _hits(_normalize(text), SUPPORT_PHRASES, negation_allowed=True),
        "shared_claim_rules": [f"{category}:{phrase}" for category, phrases in shared.items() for phrase in phrases],
        "ontology_firewall": list(ontology_firewall_scan(text).violations),
    }


def target_construct_hits(text: str) -> list[str]:
    """Target constructs (cortical wave, source localization, consciousness, biological validation).

    An explicit negation such as "not a cortical wave" is allowed. An affirmative equation is not.
    """
    return _hits(_normalize(text), TARGET_CONSTRUCT_PHRASES, negation_allowed=True)


def theory_terms_in(value: str) -> list[str]:
    """Interpretation-namespace terms found in an identifier or prose string.

    Matching compacts case, underscores, and punctuation, so ``ttfcd_phase`` and
    ``TTFCD.phase`` both match ``ttfcd``.
    """
    compact = re.sub(r"[^a-z0-9]", "", (value or "").lower())
    return [term for term in THEORY_NAMESPACE_TERMS if term in compact]
