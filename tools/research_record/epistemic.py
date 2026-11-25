"""The nine epistemic labels this record classifies every claim into.

These strings are preserved exactly as specified by the record's contract
(spaces, not underscores) -- do not rename them; downstream consumers may
match on the literal label text.

    engineering fact            -- a directly observed system/process state
                                    (CI ran and passed, a PR is merged, a
                                    file exists). No scientific claim.
    benchmark result             -- a measured performance/memory number.
                                    Not itself a scientific claim.
    synthetic demonstration      -- data_mode=synthetic. Demonstrates code
                                    runs; proves nothing empirically.
    empirical observation        -- data_mode=empirical but not a formal
                                    statistical test (e.g. a descriptive
                                    metric on real data).
    proxy inference               -- claim_class=proxy (e.g. an approximate/
                                    descriptive quantity standing in for a
                                    formal one, such as a proxy K that is
                                    not a Bayes factor).
    formal statistical evidence  -- claim_class=empirical AND a recognized
                                    formal metric (currently: a true
                                    metric_type="bayes_factor").
    hypothesis                    -- a claim under test with no evidence
                                    yet (data_mode/claim_class none or
                                    unsupported-but-scientific-in-intent).
    speculation                   -- an assertion with no supporting data
                                    at all (data_mode/claim_class
                                    unavailable, or an operator note with no
                                    declared label).
    unsupported claim             -- claim_class=unsupported, or an operator
                                    note explicitly marked as such.

Rule: "never promote an engineering PASS to a scientific PASS" is enforced
structurally -- only items labeled "formal statistical evidence" or
"empirical observation" ever feed the top-level ``scientific_verdict``
rollup (see compiler.py::_scientific_verdict). "engineering fact" and
"benchmark result" items never carry a scientific verdict at all.
"""
from __future__ import annotations

ENGINEERING_FACT = "engineering fact"
BENCHMARK_RESULT = "benchmark result"
SYNTHETIC_DEMONSTRATION = "synthetic demonstration"
EMPIRICAL_OBSERVATION = "empirical observation"
PROXY_INFERENCE = "proxy inference"
FORMAL_STATISTICAL_EVIDENCE = "formal statistical evidence"
HYPOTHESIS = "hypothesis"
SPECULATION = "speculation"
UNSUPPORTED_CLAIM = "unsupported claim"

EPISTEMIC_LABELS: frozenset[str] = frozenset(
    {
        ENGINEERING_FACT,
        BENCHMARK_RESULT,
        SYNTHETIC_DEMONSTRATION,
        EMPIRICAL_OBSERVATION,
        PROXY_INFERENCE,
        FORMAL_STATISTICAL_EVIDENCE,
        HYPOTHESIS,
        SPECULATION,
        UNSUPPORTED_CLAIM,
    }
)

#: Only these two labels may ever contribute a PASS/FAIL to the top-level
#: scientific_verdict rollup -- see the module docstring's "never promote"
#: rule and compiler.py::_scientific_verdict.
SCIENTIFIC_VERDICT_ELIGIBLE_LABELS = frozenset({FORMAL_STATISTICAL_EVIDENCE, EMPIRICAL_OBSERVATION})


def classify_scientific_item(*, claim_class: str, data_mode: str, is_formal: bool) -> str:
    """Classify one falsification/topology/scientific-gate result.

    ``is_formal`` should be true only for a recognized formal metric (e.g.
    metric_type == "bayes_factor"); everything else is, at best, a proxy or
    observation even when ``claim_class == "empirical"``.
    """
    if claim_class == "unsupported":
        return UNSUPPORTED_CLAIM
    if claim_class == "synthetic" or data_mode == "synthetic":
        return SYNTHETIC_DEMONSTRATION
    if claim_class == "proxy":
        return PROXY_INFERENCE
    if claim_class == "empirical":
        return FORMAL_STATISTICAL_EVIDENCE if is_formal else EMPIRICAL_OBSERVATION
    if claim_class == "unavailable":
        return SPECULATION
    # claim_class in {"none", "unknown"}: a named hypothesis under test with
    # no evidence class declared yet is a hypothesis, not a claim.
    return HYPOTHESIS


def classify_contribution(*, claim_class: str, value_class: str) -> str:
    """Classify one agent-contribution record."""
    if claim_class == "unsupported":
        return UNSUPPORTED_CLAIM
    if claim_class == "synthetic":
        return SYNTHETIC_DEMONSTRATION
    if claim_class == "proxy":
        return PROXY_INFERENCE
    if claim_class == "empirical":
        return EMPIRICAL_OBSERVATION
    if claim_class == "unavailable":
        return SPECULATION
    # claim_class in {"none", "unknown"}: no claim was made. Purely
    # engineering/governance/tooling work is a fact; a "scientific"-tagged
    # contribution with no claim yet is a hypothesis in progress.
    if value_class == "scientific":
        return HYPOTHESIS
    return ENGINEERING_FACT


def classify_operator_note(declared_label: str | None) -> str:
    """An operator note keeps its own declared label if valid; an
    unlabeled human assertion defaults to the most conservative bucket
    (unsupported claim), never to something stronger."""
    if isinstance(declared_label, str) and declared_label in EPISTEMIC_LABELS:
        return declared_label
    return UNSUPPORTED_CLAIM
