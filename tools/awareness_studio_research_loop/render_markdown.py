"""Render the paper-ready Markdown draft (requirement 6).

Every substantive claim/result/hypothesis line is rendered as
``- [ID] text`` so ``gates.gate_paper_claims_link_evidence`` can verify,
after the fact, that every cited ID is a real evidence/hypothesis/
experiment id this orchestrator actually loaded (requirement 4's ninth
gate: "every paper claim links to an evidence record").

This module never asserts a scientific conclusion on its own: strong
language is only ever rendered verbatim when the underlying record is
evidence_class="formal" AND has an "approved" human-review decision;
otherwise the text is rendered with an explicit hedge and the violation
is recorded (see ``check_unsupported_promotion``).
"""
from __future__ import annotations

from typing import Any

from tools.awareness_studio_research_loop.guardrails import contains_causal_language, find_forbidden_phrases


def check_unsupported_promotion(*, text: str, evidence_class: str, review_decision: str | None, check_causal: bool = True) -> dict[str, Any] | None:
    """Requirement 7: never use forbidden strong-claim language, or
    unqualified causal language, unless the record is formal evidence
    AND has an approved human-review decision.

    ``check_causal`` should be False for hypothesis *statements* --
    hypothesizing a causal relationship ("we hypothesize X causes Y") is
    ordinary, licensed scientific language before any evidence exists;
    only a claim of proven causation (in Results/Literature Background)
    needs the causal-language guard.
    """
    forbidden = find_forbidden_phrases(text)
    causal = check_causal and contains_causal_language(text)
    if not forbidden and not causal:
        return None
    is_licensed = evidence_class == "formal" and review_decision == "approved"
    if is_licensed:
        return None
    reasons = []
    if forbidden:
        reasons.append(f"forbidden phrase(s) {forbidden}")
    if causal:
        reasons.append("unqualified causal language")
    return {
        "kind": "unsupported_promotion",
        "detail": f"text uses {' and '.join(reasons)} but evidence_class={evidence_class!r} and review_decision={review_decision!r} do not license it",
    }


def _hedge(text: str, violation: dict[str, Any] | None) -> str:
    if violation is None:
        return text
    return f"{text} [UNVERIFIED CLAIM -- {violation['detail']}]"


def render_paper_draft(context: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Returns (markdown_text, unsupported_promotion_violations)."""
    violations: list[dict[str, Any]] = []
    lines: list[str] = []

    lines.append("# Research Cycle -- Paper Draft")
    lines.append("")
    lines.append(
        "> This draft is machine-compiled from the evidence records listed below. It is not itself "
        "scientific evidence, and no statement in it should be read as an independently certified "
        "scientific conclusion. The orchestrator that generated it proposes and organizes research "
        "direction; it does not certify scientific truth."
    )
    lines.append("")

    lines.append("## Research Question")
    lines.append("")
    lines.append(context["research_question"] or "_not supplied in cycle_config_")
    lines.append("")

    lines.append("## Literature Background")
    lines.append("")
    for claim in context["claims"]:
        source = context["sources_by_id"].get(claim["source_id"])
        citation = source["title"] if source and source["title"] else claim["source_id"]
        violation = check_unsupported_promotion(text=claim["claim_text"], evidence_class=claim["claim_status"], review_decision=context["review_decision_for"]("claim", claim["claim_id"]))
        if violation:
            violations.append({**violation, "id": claim["claim_id"]})
        text = _hedge(claim["claim_text"], violation)
        lines.append(f"- [{claim['claim_id']}] {text} ({citation}; claim_status={claim['claim_status']})")
    if not context["claims"]:
        lines.append("_no literature claims supplied_")
    lines.append("")

    lines.append("## Hypotheses")
    lines.append("")
    for hyp in context["hypotheses"]:
        state, reasons = context["cycle_state_for"](hyp["hypothesis_id"])
        lines.append(f"- [{hyp['hypothesis_id']}] {hyp['statement']} -- cycle_state={state}")
        lines.append(f"  - null_prediction: {hyp['null_prediction'] or '_missing_'}")
    if not context["hypotheses"]:
        lines.append("_no hypotheses supplied_")
    lines.append("")

    lines.append("## Methods")
    lines.append("")
    for plan in context["plans"]:
        metrics = ", ".join(f"{m['name']} ({m['unit'] or 'no unit'}, {m['feature_family'] or 'no family'})" for m in plan["metrics"]) or "_no metrics declared_"
        lines.append(f"- [{plan['experiment_id']}] hypothesis={plan['hypothesis_id']}, dataset={plan['dataset_id']}, metrics: {metrics}")
        lines.append(f"  - falsification_criterion: {plan['falsification_criterion'] or '_missing_'}")
    if not context["plans"]:
        lines.append("_no experiment plans supplied_")
    lines.append("")

    lines.append("## Preregistered Predictions")
    lines.append("")
    preregistered = [p for p in context["plans"] if p["preregistered"]]
    for plan in preregistered:
        lines.append(f"- [{plan['experiment_id']}] preregistered, held_out_split_locked={plan['held_out_split_locked']}")
    if not preregistered:
        lines.append("_none preregistered_")
    lines.append("")

    lines.append("## Results")
    lines.append("")
    for execution in context["executions"]:
        ledger_row = context["ledger_row_for"](execution["experiment_id"])
        evidence_class = ledger_row["scientific_status"] if ledger_row else "unknown"
        for metric in execution["metric_values"]:
            text = f"{metric['name']} = {metric['value']} {metric['unit'] or ''}".strip()
            violation = check_unsupported_promotion(text=text, evidence_class=evidence_class, review_decision=context["review_decision_for"]("experiment", execution["experiment_id"]))
            if violation:
                violations.append({**violation, "id": execution["experiment_id"]})
            rendered = _hedge(text, violation)
            lines.append(f"- [{execution['experiment_id']}] {rendered} (data_mode={execution['data_mode']}, evidence_class={evidence_class})")
    if not context["executions"]:
        lines.append("_no execution results supplied_")
    lines.append("")

    lines.append("## Null Controls")
    lines.append("")
    for null_test in context["null_tests"]:
        lines.append(f"- [{null_test['experiment_id']}] method={null_test['method']}, verdict={null_test['verdict']}")
    if not context["null_tests"]:
        lines.append("_no null/surrogate validation supplied_")
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    for item in context["limitations"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Alternative Explanations")
    lines.append("")
    if context["theory_state"]["alternative_explanations"]:
        for item in context["theory_state"]["alternative_explanations"]:
            lines.append(f"- {item}")
    else:
        lines.append("_none supplied in theory_state_")
    lines.append("")

    lines.append("## Theory Revision")
    lines.append("")
    revision_hypotheses = [h for h in context["hypotheses"] if context["cycle_state_for"](h["hypothesis_id"])[0] == "THEORY_REVISION_REQUIRED"]
    for hyp in revision_hypotheses:
        _, reasons = context["cycle_state_for"](hyp["hypothesis_id"])
        lines.append(f"- [{hyp['hypothesis_id']}] requires theory revision: {'; '.join(reasons)}")
    if not revision_hypotheses:
        lines.append("_no hypotheses currently require theory revision_")
    lines.append("")
    lines.append("Contradictory evidence this theory_state must continue to account for:")
    for claim_id in context["theory_state"]["contradictory_evidence_ids"]:
        lines.append(f"- [{claim_id}]")
    if not context["theory_state"]["contradictory_evidence_ids"]:
        lines.append("_none declared_")
    lines.append("")

    lines.append("## Unresolved Questions")
    lines.append("")
    unresolved = [h for h in context["hypotheses"] if context["cycle_state_for"](h["hypothesis_id"])[0] in ("INCONCLUSIVE", "VALIDATION_PENDING", "EXECUTION_PENDING")]
    for hyp in unresolved:
        state, reasons = context["cycle_state_for"](hyp["hypothesis_id"])
        lines.append(f"- [{hyp['hypothesis_id']}] {state}: {'; '.join(reasons)}")
    if not unresolved:
        lines.append("_none_")
    lines.append("")

    lines.append("## Claims Requiring Human Review")
    lines.append("")
    review_required = [h for h in context["hypotheses"] if context["cycle_state_for"](h["hypothesis_id"])[0] == "HUMAN_REVIEW_REQUIRED"]
    for hyp in review_required:
        _, reasons = context["cycle_state_for"](hyp["hypothesis_id"])
        lines.append(f"- [{hyp['hypothesis_id']}] {'; '.join(reasons)}")
    if not review_required:
        lines.append("_none currently pending human review_")
    lines.append("")

    return "\n".join(lines) + "\n", violations
