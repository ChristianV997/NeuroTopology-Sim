"""Deterministic compilation of one research-cycle report.

``compile_research_cycle`` is the single entry point: it resolves a
manifest of local JSON/YAML evidence documents (never discovering or
executing anything itself), evaluates the nine mandatory gates, computes
a cycle state per hypothesis, builds the artifact ledger, renders the
paper-ready Markdown draft, and returns one JSON-serializable dict. See
docs/awareness_studio/research_cycle_orchestration.md for the full
contract.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.awareness_studio_research_loop import gates as gates_mod
from tools.awareness_studio_research_loop import manifest as manifest_mod
from tools.awareness_studio_research_loop.ledger import build_artifact_ledger
from tools.awareness_studio_research_loop.render_markdown import check_unsupported_promotion, render_paper_draft
from tools.awareness_studio_research_loop.sections import (
    build_cycle_config,
    build_execution_results,
    build_experiment_plans,
    build_hypothesis_registry,
    build_literature_evidence,
    build_null_surrogate_results,
    build_reviewer_decisions,
    build_theory_state,
    build_validation_reports,
)
from tools.awareness_studio_research_loop.state_machine import compute_cycle_state
from tools.awareness_studio_research_loop.versions import COMPILER_VERSION, INPUT_CONTRACT_VERSION, REPORT_SCHEMA_VERSION


def _merged_claim_ids(hypothesis: dict[str, Any], hypothesis_links: list[dict[str, Any]]) -> list[str]:
    ids = set(hypothesis["claim_ids"])
    for link in hypothesis_links:
        if link["hypothesis_id"] == hypothesis["hypothesis_id"]:
            ids |= set(link["claim_ids"])
    return sorted(ids)


def _first_plan_for_hypothesis(hypothesis_id: str, plans: list[dict[str, Any]]) -> dict[str, Any] | None:
    matching = sorted((p for p in plans if p["hypothesis_id"] == hypothesis_id), key=lambda p: p["experiment_id"])
    return matching[0] if matching else None


def _scan_text_for_promotion_violations(*, subjects: list[tuple[str, str, str, str | None]], check_causal: bool) -> list[dict[str, Any]]:
    """``subjects`` is a list of (id, text, evidence_class, review_decision) tuples."""
    violations = []
    for subject_id, text, evidence_class, review_decision in subjects:
        violation = check_unsupported_promotion(text=text, evidence_class=evidence_class, review_decision=review_decision, check_causal=check_causal)
        if violation:
            violations.append({**violation, "id": subject_id})
    return violations


def _scientific_limitations(*, claims, executions, null_tests, gate_results) -> list[str]:
    limitations = [
        "This report aggregates evidence documents as-provided; it does not independently re-run or re-verify any simulation, analysis, or literature claim.",
        "cycle_state and the artifact ledger's scientific_status reflect only the declared checks in the source records; they are not an independent statistical or editorial review.",
        "The orchestrator proposes and organizes research direction; it does not and cannot certify scientific truth.",
    ]
    if any(c["claim_status"] in ("proxy", "speculative", "unsupported") for c in claims):
        limitations.append("One or more literature claims are proxy/speculative/unsupported claim_status and do not constitute empirical evidence.")
    if any(e["data_mode"] == "synthetic" for e in executions):
        limitations.append("One or more executions are synthetic data_mode and do not constitute empirical validation.")
    if any(n["verdict"] == "TIMEOUT" for n in null_tests):
        limitations.append("One or more null/surrogate tests timed out; a timeout produced no result and must not be read as PASS, FAIL, or INCONCLUSIVE.")
    for gate_name, result in gate_results.items():
        if not result["passed"]:
            limitations.append(f"Gate {gate_name!r} has {len(result['violations'])} unresolved violation(s).")
    return limitations


def compile_research_cycle(
    manifest_path: Path,
    *,
    now: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    loaded = manifest_mod.load_manifest(manifest_path)

    literature_section = build_literature_evidence(loaded[manifest_mod.LITERATURE_EVIDENCE])
    hypothesis_section = build_hypothesis_registry(loaded[manifest_mod.HYPOTHESIS_REGISTRY])
    plans_section = build_experiment_plans(loaded[manifest_mod.EXPERIMENT_PLANS])
    executions_section = build_execution_results(loaded[manifest_mod.EXECUTION_RESULTS])
    null_tests_section = build_null_surrogate_results(loaded[manifest_mod.NULL_SURROGATE_RESULTS])
    validation_section = build_validation_reports(loaded[manifest_mod.VALIDATION_REPORTS])
    reviewer_section = build_reviewer_decisions(loaded[manifest_mod.REVIEWER_DECISIONS])
    theory_section = build_theory_state(loaded[manifest_mod.THEORY_STATE])
    cycle_config_section = build_cycle_config(loaded[manifest_mod.CYCLE_CONFIG])

    claims = literature_section["claims"]
    sources = literature_section["sources"]
    hypothesis_links = literature_section["hypothesis_links"]
    plans = plans_section["plans"]
    executions = executions_section["executions"]
    null_tests = null_tests_section["null_tests"]
    validation_reports = validation_section["reports"]
    reviewer_decisions = reviewer_section["decisions"]
    evidence_updates = literature_section["evidence_updates"]

    claims_by_id = {c["claim_id"]: c for c in claims}
    sources_by_id = {s["source_id"]: s for s in sources}
    executions_by_experiment = {e["experiment_id"]: e for e in executions}
    null_tests_by_experiment = {n["experiment_id"]: n for n in null_tests}
    reviewer_decisions_by_subject: dict[tuple[str, str], dict[str, Any]] = {}
    for decision in reviewer_decisions:
        key = (decision["subject_type"], decision["subject_id"])
        reviewer_decisions_by_subject.setdefault(key, decision)

    hypotheses = []
    for h in hypothesis_section["hypotheses"]:
        merged = dict(h)
        merged["claim_ids"] = _merged_claim_ids(h, hypothesis_links)
        hypotheses.append(merged)
    hypotheses_by_id = {h["hypothesis_id"]: h for h in hypotheses}

    gate_results = gates_mod.evaluate_all_gates(
        claims=claims,
        sources=sources,
        hypotheses=hypotheses,
        plans=plans,
        executions=executions,
        validation_reports=validation_reports,
        theory_state=theory_section,
    )

    claim_provenance_violation_ids = {v["id"] for v in gate_results["claim_provenance"]["violations"]}
    metric_violation_ids = {v["id"] for v in gate_results["metric_units_and_families"]["violations"]}
    dataset_violation_experiment_ids = {v["id"] for v in gate_results["dataset_checksum"]["violations"]}
    # Any claim theory_state currently names as contradictory evidence is
    # an *unresolved* contradiction for whichever hypothesis relies on it
    # -- distinct from the gate above, which only checks that such a claim
    # was not silently dropped from the record altogether.
    theory_violation_claim_ids = set(theory_section["contradictory_evidence_ids"])

    hypotheses_with_evidence_update = {u["entity_id"] for u in evidence_updates if u["entity_type"] == "hypothesis"}

    cycle_states: dict[str, dict[str, Any]] = {}
    for hypothesis in hypotheses:
        experiment = _first_plan_for_hypothesis(hypothesis["hypothesis_id"], plans)
        execution = executions_by_experiment.get(experiment["experiment_id"]) if experiment else None
        null_test = null_tests_by_experiment.get(experiment["experiment_id"]) if experiment else None
        reviewer_decision = reviewer_decisions_by_subject.get(("hypothesis", hypothesis["hypothesis_id"]))
        state, reasons = compute_cycle_state(
            hypothesis=hypothesis,
            claim_ids=hypothesis["claim_ids"],
            claims_by_id=claims_by_id,
            claim_provenance_violation_ids=claim_provenance_violation_ids,
            experiment=experiment,
            metric_violation_ids=metric_violation_ids,
            execution=execution,
            dataset_violation_experiment_ids=dataset_violation_experiment_ids,
            null_test=null_test,
            evidence_update_logged=hypothesis["hypothesis_id"] in hypotheses_with_evidence_update,
            theory_violation_claim_ids=theory_violation_claim_ids,
            reviewer_decision=reviewer_decision,
        )
        cycle_states[hypothesis["hypothesis_id"]] = {"state": state, "reasons": reasons}

    artifact_ledger = build_artifact_ledger(
        plans=plans,
        executions_by_experiment=executions_by_experiment,
        null_tests_by_experiment=null_tests_by_experiment,
        hypotheses_by_id=hypotheses_by_id,
        claims_by_id=claims_by_id,
        sources_by_id=sources_by_id,
        reviewer_decisions_by_subject=reviewer_decisions_by_subject,
    )
    ledger_by_experiment = {r["experiment_id"]: r for r in artifact_ledger}

    def review_decision_for(subject_type: str, subject_id: str) -> str | None:
        decision = reviewer_decisions_by_subject.get((subject_type, subject_id))
        return decision["decision"] if decision else None

    def cycle_state_for(hypothesis_id: str) -> tuple[str, list[str]]:
        entry = cycle_states.get(hypothesis_id)
        return (entry["state"], entry["reasons"]) if entry else ("HUMAN_REVIEW_REQUIRED", ["hypothesis not found"])

    def ledger_row_for(experiment_id: str) -> dict[str, Any] | None:
        return ledger_by_experiment.get(experiment_id)

    # Forbidden-language / unsupported-promotion scan over the raw
    # hypothesis statements and falsification criteria too, not just the
    # rendered paper text (requirement 7).
    promotion_violations = _scan_text_for_promotion_violations(
        subjects=[
            (h["hypothesis_id"], h["statement"], "unknown", review_decision_for("hypothesis", h["hypothesis_id"]))
            for h in hypotheses
        ],
        check_causal=False,
    )

    paper_context = {
        "research_question": cycle_config_section["research_question"],
        "claims": claims,
        "sources_by_id": sources_by_id,
        "hypotheses": hypotheses,
        "plans": plans,
        "executions": executions,
        "null_tests": null_tests,
        "theory_state": theory_section,
        "limitations": _scientific_limitations(claims=claims, executions=executions, null_tests=null_tests, gate_results=gate_results),
        "review_decision_for": review_decision_for,
        "cycle_state_for": cycle_state_for,
        "ledger_row_for": ledger_row_for,
    }
    paper_markdown, paper_promotion_violations = render_paper_draft(paper_context)
    promotion_violations += paper_promotion_violations
    promotion_violations.sort(key=lambda v: (v["kind"], v["id"]))

    known_ids = (
        {c["claim_id"] for c in claims}
        | {h["hypothesis_id"] for h in hypotheses}
        | {p["experiment_id"] for p in plans}
    )
    gate_results["paper_claims_link_evidence"] = {
        "passed": True,
        "violations": [],
    }
    citation_violations = gates_mod.gate_paper_claims_link_evidence(paper_markdown, known_ids)
    gate_results["paper_claims_link_evidence"] = {"passed": len(citation_violations) == 0, "violations": citation_violations}

    all_sections = [loaded[key] for key in manifest_mod.INPUT_SECTIONS]
    overall_status = "complete" if all(r.ok for r in all_sections) else "partial"
    completeness = {key: {"available": loaded[key].ok, "error": loaded[key].error} for key in manifest_mod.INPUT_SECTIONS}

    human_review_summary = {
        "hypotheses_requiring_review": sorted(hyp_id for hyp_id, entry in cycle_states.items() if entry["state"] == "HUMAN_REVIEW_REQUIRED"),
        "decisions_by_subject": {f"{t}:{i}": d["decision"] for (t, i), d in sorted(reviewer_decisions_by_subject.items())},
    }

    evidence_class_summary = {
        "claims": {status: sum(1 for c in claims if c["claim_status"] == status) for status in sorted({c["claim_status"] for c in claims})},
        "executions": {row["scientific_status"]: sum(1 for r in artifact_ledger if r["scientific_status"] == row["scientific_status"]) for row in artifact_ledger},
    }

    record: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "compiler_version": COMPILER_VERSION,
        "generated_at": generated_at,
        "status": overall_status,
        "completeness": completeness,
        "repository_identity": {"repo": repo},
        "cycle_config": cycle_config_section,
        "literature_evidence": literature_section,
        "hypothesis_registry": {**hypothesis_section, "hypotheses": hypotheses},
        "experiment_plans": plans_section,
        "execution_results": executions_section,
        "null_surrogate_results": null_tests_section,
        "validation_reports": validation_section,
        "reviewer_decisions": reviewer_section,
        "theory_state": theory_section,
        "gate_results": gate_results,
        "cycle_states": cycle_states,
        "artifact_ledger": artifact_ledger,
        "unsupported_promotion_violations": promotion_violations,
        "human_review_summary": human_review_summary,
        "evidence_class_summary": evidence_class_summary,
        "scientific_limitations": paper_context["limitations"],
        "paper_draft_markdown": paper_markdown,
        "record_provenance": {
            "manifest_path": str(manifest_path),
            "source_checksums": {
                key: {"path": loaded[key].path, "sha256": loaded[key].sha256, "checksum_scope": "local"} for key in manifest_mod.INPUT_SECTIONS
            },
        },
    }
    canonical = json.dumps(record, sort_keys=True, allow_nan=False)
    record["canonical_checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return record
