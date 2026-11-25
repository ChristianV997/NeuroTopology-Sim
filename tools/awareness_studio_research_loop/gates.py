"""The nine mandatory gates (requirement 4). Each ``gate_*`` function
returns a list of violation dicts (empty means the gate passed for every
record it examined); nothing here executes code or fetches anything --
every check is a pure function over already-loaded, normalized records.
"""
from __future__ import annotations

from typing import Any


def gate_claim_provenance(claims: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every claim has source provenance: a resolvable source_id whose
    source record carries a non-empty source_checksum."""
    sources_by_id = {s["source_id"]: s for s in sources}
    violations = []
    for claim in claims:
        source = sources_by_id.get(claim["source_id"])
        if source is None:
            violations.append({"gate": "claim_provenance", "id": claim["claim_id"], "detail": f"claim {claim['claim_id']!r} references source_id {claim['source_id']!r}, which was not found"})
        elif not source["source_checksum"]:
            violations.append({"gate": "claim_provenance", "id": claim["claim_id"], "detail": f"claim {claim['claim_id']!r}'s source {claim['source_id']!r} has no source_checksum"})
    return violations


def gate_null_prediction(hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every hypothesis has a null prediction."""
    return [
        {"gate": "null_prediction", "id": h["hypothesis_id"], "detail": f"hypothesis {h['hypothesis_id']!r} has no null_prediction"}
        for h in hypotheses
        if not h["null_prediction"]
    ]


def gate_falsification_criterion(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every experiment has a falsification criterion."""
    return [
        {"gate": "falsification_criterion", "id": p["experiment_id"], "detail": f"experiment {p['experiment_id']!r} has no falsification_criterion"}
        for p in plans
        if not p["falsification_criterion"]
    ]


def gate_metric_units_and_families(plans: list[dict[str, Any]], executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every metric has a declared unit and feature family (on the plan),
    and every reported metric value carries a unit (on the execution)."""
    violations = []
    for plan in plans:
        for metric in plan["metrics"]:
            if not metric["unit"] or not metric["feature_family"]:
                violations.append(
                    {"gate": "metric_units_and_families", "id": f"{plan['experiment_id']}:{metric['name']}", "detail": f"metric {metric['name']!r} in experiment {plan['experiment_id']!r} is missing unit and/or feature_family"}
                )
    for execution in executions:
        for metric in execution["metric_values"]:
            if not metric["unit"]:
                violations.append(
                    {"gate": "metric_units_and_families", "id": f"{execution['experiment_id']}:{metric['name']}", "detail": f"reported metric value {metric['name']!r} for experiment {execution['experiment_id']!r} has no unit"}
                )
    return violations


def gate_dataset_checksum(plans: list[dict[str, Any]], executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every empirical result has a dataset checksum (declared on its
    plan) and recorded output checksums (on its execution)."""
    plans_by_id = {p["experiment_id"]: p for p in plans}
    violations = []
    for execution in executions:
        if execution["data_mode"] != "empirical":
            continue
        plan = plans_by_id.get(execution["experiment_id"])
        if plan is None or not plan["dataset_checksum"]:
            violations.append({"gate": "dataset_checksum", "id": execution["experiment_id"], "detail": f"empirical execution {execution['experiment_id']!r} has no dataset_checksum on its experiment plan"})
        if not execution["output_checksums"]:
            violations.append({"gate": "dataset_checksum", "id": execution["experiment_id"], "detail": f"empirical execution {execution['experiment_id']!r} recorded no output_checksums"})
    return violations


def gate_locked_holdout(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every predictive result has a locked held-out split."""
    return [
        {"gate": "locked_holdout", "id": p["experiment_id"], "detail": f"predictive experiment {p['experiment_id']!r} does not have held_out_split_locked=true"}
        for p in plans
        if p["is_predictive"] and p["held_out_split_locked"] is not True
    ]


def gate_synthetic_not_promoted(executions: list[dict[str, Any]], validation_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every synthetic result remains synthetic: a validation report must
    never describe a synthetic execution's experiment as empirical."""
    synthetic_experiment_ids = {e["experiment_id"] for e in executions if e["data_mode"] == "synthetic"}
    violations = []
    for report in validation_reports:
        if report["experiment_id"] in synthetic_experiment_ids and report["data_mode"] == "empirical":
            violations.append(
                {
                    "gate": "synthetic_not_promoted",
                    "id": report["report_id"],
                    "detail": f"validation report {report['report_id']!r} claims data_mode=empirical for experiment {report['experiment_id']!r}, whose own execution is data_mode=synthetic",
                }
            )
    return violations


def gate_theory_contradictions_preserved(theory_state: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every theory update preserves contradictory evidence: a
    contradictory_evidence_id the theory itself names must still be a
    known claim, never silently dropped."""
    known_claim_ids = {c["claim_id"] for c in claims}
    return [
        {"gate": "theory_contradictions_preserved", "id": claim_id, "detail": f"theory_state names {claim_id!r} as contradictory evidence, but it is not among the loaded claims"}
        for claim_id in theory_state["contradictory_evidence_ids"]
        if claim_id not in known_claim_ids
    ]


def gate_paper_claims_link_evidence(markdown: str, known_ids: set[str]) -> list[dict[str, Any]]:
    """Every paper claim links to an evidence record: every ``- [ID] ...``
    bullet the paper draft renders must cite an ID this compiler actually
    loaded. Run against the fully rendered draft as a self-check."""
    import re

    violations = []
    for match in re.finditer(r"^- \[([^\]]+)\]", markdown, flags=re.MULTILINE):
        cited_id = match.group(1)
        if cited_id not in known_ids:
            violations.append({"gate": "paper_claims_link_evidence", "id": cited_id, "detail": f"paper draft cites {cited_id!r}, which is not a known evidence/hypothesis/experiment id"})
    return violations


def evaluate_all_gates(
    *,
    claims: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    validation_reports: list[dict[str, Any]],
    theory_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    checks = {
        "claim_provenance": gate_claim_provenance(claims, sources),
        "null_prediction": gate_null_prediction(hypotheses),
        "falsification_criterion": gate_falsification_criterion(plans),
        "metric_units_and_families": gate_metric_units_and_families(plans, executions),
        "dataset_checksum": gate_dataset_checksum(plans, executions),
        "locked_holdout": gate_locked_holdout(plans),
        "synthetic_not_promoted": gate_synthetic_not_promoted(executions, validation_reports),
        "theory_contradictions_preserved": gate_theory_contradictions_preserved(theory_state, claims),
    }
    return {name: {"passed": len(violations) == 0, "violations": violations} for name, violations in checks.items()}
