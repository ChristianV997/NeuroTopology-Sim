"""Text-level hints for the scientific claim guardrails this ecosystem
already enforces in code (K > 100 gates, synthetic-vs-empirical labeling,
provenance/control requirements -- see the prior independent scientific
review referenced in docs/integration_reconciliation/README.md).

These are HINTS derived from a PR's own description text (a legitimate,
already-available data source -- no additional fetch), not a static or
dynamic analysis of the branch's code. A hint firing means "a human
scientific reviewer should look at this," never "this PR is wrong." A
hint NOT firing is not proof the PR is correct either -- it only means
the description text didn't trip a known-risky pattern.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SYNTHETIC_TERMS = re.compile(r"\b(synthetic|mock|demo|fixture|fake)\b", re.IGNORECASE)
_PASS_CLAIM = re.compile(r"\bPASS\b")
_SYNTHETIC_SAFEGUARD_TERMS = re.compile(
    r"\b(cannot produce PASS|never PASS|NOT_SUPPORTED|not empirical evidence|unable to produce PASS)\b",
    re.IGNORECASE,
)

_BAYES_FACTOR_TERM = re.compile(r"\bbayes factor\b", re.IGNORECASE)
_BAYES_FACTOR_QUALIFIERS = re.compile(
    r"\b(proxy|descriptive|approximate|not a formal|formal marginal.likelihood|evidence proxy)\b",
    re.IGNORECASE,
)

_EMPIRICAL_TERMS = re.compile(r"\b(empirical|real data|real fmri|real eeg)\b", re.IGNORECASE)
_PROVENANCE_TERMS = re.compile(
    r"\b(provenance|source_kind|dataset_id|checksum|sha-?256|s3 bucket|bids session)\b", re.IGNORECASE
)

_SIGNIFICANCE_TERMS = re.compile(r"\b(PASS|significant|evidence for)\b")
_CONTROL_TERMS = re.compile(r"\b(null control|permutation|control|baseline|classical)\b", re.IGNORECASE)

_STRONG_CLAIM_TERMS = re.compile(r"\b(confirms|demonstrates|proves|establishes)\b", re.IGNORECASE)
_CLAIM_QUALIFIER_TERMS = re.compile(
    r"\b(not proof|descriptive only|NOT_SUPPORTED|no .*claim|not a claim|does not (claim|assert))\b",
    re.IGNORECASE,
)


@dataclass
class ScientificGateHints:
    synthetic_pass_claim_risk: bool = False
    unqualified_bayes_factor_claim: bool = False
    empirical_claim_missing_provenance_terms: bool = False
    significance_claim_missing_control_terms: bool = False
    strong_claim_missing_qualifier: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def scientific_review_required(self) -> bool:
        return any([
            self.synthetic_pass_claim_risk,
            self.unqualified_bayes_factor_claim,
            self.empirical_claim_missing_provenance_terms,
            self.significance_claim_missing_control_terms,
            self.strong_claim_missing_qualifier,
        ])

    def to_dict(self) -> dict:
        return {
            "synthetic_pass_claim_risk": self.synthetic_pass_claim_risk,
            "unqualified_bayes_factor_claim": self.unqualified_bayes_factor_claim,
            "empirical_claim_missing_provenance_terms": self.empirical_claim_missing_provenance_terms,
            "significance_claim_missing_control_terms": self.significance_claim_missing_control_terms,
            "strong_claim_missing_qualifier": self.strong_claim_missing_qualifier,
            "scientific_review_required": self.scientific_review_required,
            "reasons": list(self.reasons),
        }


# Scientific-module path prefixes: a work order touching any of these
# requires scientific review regardless of what its description says.
SCIENTIFIC_PATH_PREFIXES: tuple[str, ...] = (
    "sim/pitnn", "physics/exact_dynamics", "core/topology",
    "analysis/connectivity_topology", "analysis/permutation", "analysis/stats",
    "topo_monitor", "validation",
)


def evaluate_text(text: str) -> ScientificGateHints:
    hints = ScientificGateHints()
    if not text:
        return hints

    if _SYNTHETIC_TERMS.search(text) and _PASS_CLAIM.search(text) and not _SYNTHETIC_SAFEGUARD_TERMS.search(text):
        hints.synthetic_pass_claim_risk = True
        hints.reasons.append(
            "mentions synthetic/mock/demo data alongside a PASS claim with no visible "
            "safeguard language (e.g. 'cannot produce PASS', 'NOT_SUPPORTED')"
        )

    if _BAYES_FACTOR_TERM.search(text) and not _BAYES_FACTOR_QUALIFIERS.search(text):
        hints.unqualified_bayes_factor_claim = True
        hints.reasons.append(
            "mentions 'Bayes factor' with no visible proxy/descriptive/approximate "
            "qualifier distinguishing it from a formal marginal-likelihood Bayes factor"
        )

    if _EMPIRICAL_TERMS.search(text) and not _PROVENANCE_TERMS.search(text):
        hints.empirical_claim_missing_provenance_terms = True
        hints.reasons.append(
            "mentions empirical/real data with no visible provenance terms "
            "(source_kind, dataset_id, checksum, sha256, ...)"
        )

    if _SIGNIFICANCE_TERMS.search(text) and not _CONTROL_TERMS.search(text):
        hints.significance_claim_missing_control_terms = True
        hints.reasons.append(
            "mentions PASS/significant/evidence with no visible control/baseline/"
            "null-control/permutation terms"
        )

    if _STRONG_CLAIM_TERMS.search(text) and not _CLAIM_QUALIFIER_TERMS.search(text):
        hints.strong_claim_missing_qualifier = True
        hints.reasons.append(
            "uses a strong claim verb (confirms/demonstrates/proves/establishes) with "
            "no visible qualifier limiting its scope"
        )

    return hints


def touches_scientific_paths(changed_files: tuple[str, ...] | None) -> bool:
    if not changed_files:
        return False
    return any(
        path == prefix or path.startswith(prefix + "/")
        for path in changed_files
        for prefix in SCIENTIFIC_PATH_PREFIXES
    )
