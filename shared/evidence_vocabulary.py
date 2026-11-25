"""Canonical evidence-class vocabulary shared by the claim and promotion gates.

Before this module the repository carried ~20 spellings of the same evidence tiers
(``synthetic_demonstration`` / ``synthetic_demo_only`` / ``synthetic``; ``proxy`` /
``proxy_only`` / ``proxy_inference``; ``unknown`` / ``unspecified`` ...) and two gates with
near-identical taxonomies (tools/research_claim_gate: 9 classes, tools/evidence_promotion_gate:
8 classes = the same minus ``formal_statistical_evidence``).

* ``EVIDENCE_CLASSES`` is the single ordered taxonomy (weakest-claim-last ordering preserved
  from research_claim_gate).
* ``PROMOTABLE_TO_DESCRIPTIVE_REVIEW`` is the subset the promotion gate admits (it never
  admits formal statistical evidence; descriptive review is not confirmation).
* ``normalize_evidence_class`` maps legacy spellings to a canonical class and fails closed:
  unknown strings map to ``unsupported_claim`` rather than to anything stronger.

Nothing here can upgrade evidence: every alias maps to the same or a weaker tier.
"""

from __future__ import annotations

EVIDENCE_CLASSES: tuple[str, ...] = (
    "engineering_fact",
    "benchmark_result",
    "synthetic_demonstration",
    "descriptive_empirical",
    "proxy_inference",
    "formal_statistical_evidence",
    "hypothesis",
    "speculation",
    "unsupported_claim",
)

PROMOTABLE_TO_DESCRIPTIVE_REVIEW: tuple[str, ...] = tuple(
    c for c in EVIDENCE_CLASSES if c != "formal_statistical_evidence"
)

LEGACY_ALIASES: dict[str, str] = {
    "synthetic": "synthetic_demonstration",
    "synthetic_demo_only": "synthetic_demonstration",
    "synthetic_only": "synthetic_demonstration",
    "proxy": "proxy_inference",
    "proxy_only": "proxy_inference",
    "formal": "formal_statistical_evidence",
    "engineering_execution": "engineering_fact",
    "performance_only": "benchmark_result",
    "descriptive_topology_only": "descriptive_empirical",
    "empirical_dataset": "descriptive_empirical",
    "review_required": "hypothesis",
    "unknown": "unsupported_claim",
    "unspecified": "unsupported_claim",
}


def normalize_evidence_class(value: object) -> str:
    """Return the canonical class for ``value``; unknown or non-string input fails closed."""
    if not isinstance(value, str):
        return "unsupported_claim"
    key = value.strip().lower()
    if key in EVIDENCE_CLASSES:
        return key
    return LEGACY_ALIASES.get(key, "unsupported_claim")
