"""Deterministic compilation of the mobile research-state report.

``compile_report`` is the single entry point: it resolves a manifest of
local JSON/YAML/CSV evidence documents, normalizes each into a report
section, computes the cross-cutting sections (stacking graph, conflicts,
blockers, next actions, final recommendation), and returns one
JSON-serializable dict. See docs/reporting/mobile_report_contract.md for
the full contract and its guardrail list.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.mobile_report import manifest as manifest_mod
from tools.mobile_report.graph import (
    build_dependency_edges,
    find_cycles,
    find_stacked_parent_violations,
    recommended_merge_order,
    topological_layers,
)
from tools.mobile_report.guardrails import INCOMPLETE_EVIDENCE
from tools.mobile_report.sections import (
    build_agent_contributions,
    build_benchmark_summary,
    build_dashboard_isolation,
    build_dataset_provenance,
    build_falsification,
    build_merge_gate,
    build_reconciliation,
    build_test_runner,
    build_topology_validation,
)
from tools.mobile_report.versions import COMPILER_VERSION, REPORT_SCHEMA_VERSION

_INFRA_STATUS_CATEGORIES = {"CI_BLOCKED", "BILLING_BLOCKED"}
_WEAK_CLAIM_CLASSES = {"synthetic", "proxy", "unsupported"}


def _envelope(agent_contributions_result) -> dict[str, Any]:
    data = agent_contributions_result.data if agent_contributions_result.ok and isinstance(agent_contributions_result.data, dict) else {}
    warnings = data.get("required_warnings")
    return {
        "repository": data.get("repository") if isinstance(data.get("repository"), str) else None,
        "baseline_commit": data.get("baseline_commit") if isinstance(data.get("baseline_commit"), str) else None,
        "evidence_source": data.get("evidence_source") if isinstance(data.get("evidence_source"), str) else None,
        "inventory_is_not_evidence": bool(data.get("inventory_is_not_evidence")) if "inventory_is_not_evidence" in data else None,
        "merger_instruction": data.get("merger_instruction") if isinstance(data.get("merger_instruction"), str) else None,
        "required_warnings": sorted({w for w in warnings if isinstance(w, str)}) if isinstance(warnings, list) else [],
    }


def _merger_summary_conflicts(pr_entries: list[dict[str, Any]], contributions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    contributions_by_pr = {c["pr_number"]: c for c in contributions if c["pr_number"] is not None}
    for pr in pr_entries:
        contribution = contributions_by_pr.get(pr["pr_number"])
        if contribution is None:
            continue
        if contribution["merge_status"] != pr["merge_status"]:
            conflicts.append(
                {
                    "kind": "conflicting_merger_summary",
                    "pr_number": pr["pr_number"],
                    "detail": (
                        f"reconciliation reports merge_status={pr['merge_status']!r} for PR #{pr['pr_number']} "
                        f"but agent_contributions reports merge_status={contribution['merge_status']!r}"
                    ),
                }
            )
    return conflicts


def _merged_but_draft_or_unintegrated_conflicts(pr_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for pr in pr_entries:
        if pr["merge_status"] == "merged" and pr["is_draft"] is True:
            conflicts.append(
                {
                    "kind": "open_pr_represented_as_merged",
                    "pr_number": pr["pr_number"],
                    "detail": f"PR #{pr['pr_number']} is recorded merge_status=merged while is_draft=true -- a draft cannot be merged",
                }
            )
        if pr["merge_status"] == "merged" and pr["integration_status"] in ("integrated_only", "not_integrated"):
            conflicts.append(
                {
                    "kind": "open_pr_represented_as_merged",
                    "pr_number": pr["pr_number"],
                    "detail": (
                        f"PR #{pr['pr_number']} is recorded merge_status=merged but integration_status="
                        f"{pr['integration_status']!r} -- being present in an integration branch is not the same as being merged"
                    ),
                }
            )
        if pr["merge_status"] == "merged" and pr["superseded_by_pr"] is not None:
            conflicts.append(
                {
                    "kind": "superseded_but_merged",
                    "pr_number": pr["pr_number"],
                    "detail": f"PR #{pr['pr_number']} is recorded merge_status=merged and also superseded_by_pr={pr['superseded_by_pr']}",
                }
            )
    return conflicts


def _synthetic_pass_conflicts(
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
    contributions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for result in falsification_results:
        if result["claim_class"] in _WEAK_CLAIM_CLASSES and result["verdict"] == "PASS":
            conflicts.append(
                {
                    "kind": "synthetic_pass_claim",
                    "id": result["hypothesis_id"],
                    "detail": f"falsification result {result['hypothesis_id']!r} claims verdict=PASS with claim_class={result['claim_class']!r}, which cannot establish a scientific PASS",
                }
            )
    for check in topology_checks:
        if check["data_mode"] in ("synthetic", "proxy") and check["verdict"] == "PASS":
            conflicts.append(
                {
                    "kind": "synthetic_pass_claim",
                    "id": check["name"],
                    "detail": f"topology check {check['name']!r} claims verdict=PASS with data_mode={check['data_mode']!r}, which cannot establish a scientific PASS",
                }
            )
    for contribution in contributions:
        rc = contribution["research_classification"]
        if rc["claim_class"] in _WEAK_CLAIM_CLASSES and (
            rc["empirical_pass_allowed"] or contribution["verification_status"]["scientific_pass"] in ("claimed", "pass")
        ):
            conflicts.append(
                {
                    "kind": "synthetic_pass_claim",
                    "id": contribution["id"],
                    "detail": f"contribution {contribution['id']!r} has claim_class={rc['claim_class']!r} but claims empirical_pass_allowed or a scientific_pass",
                }
            )
    return conflicts


def _billing_not_pass_conflicts(jobs: list[dict[str, Any]], contributions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for job in jobs:
        if job["block_reason"] == "billing" and job["status"] == "passed":
            conflicts.append(
                {
                    "kind": "billing_not_pass",
                    "id": job["name"],
                    "detail": f"test job {job['name']!r} is marked block_reason=billing but status=passed -- a billing block cannot be a passing test result",
                }
            )
    for contribution in contributions:
        if contribution["verification_status"]["author_test_results"] == "verified_pass" and "BILLING" in " ".join(
            contribution["limitations"]
        ).upper():
            conflicts.append(
                {
                    "kind": "billing_not_pass",
                    "id": contribution["id"],
                    "detail": f"contribution {contribution['id']!r} claims author_test_results=verified_pass while its own limitations mention billing",
                }
            )
    return conflicts


def _outdated_commit_conflicts(envelope: dict[str, Any], integration_commit: str | None) -> list[dict[str, Any]]:
    if not integration_commit or not envelope["baseline_commit"]:
        return []
    if envelope["baseline_commit"] == integration_commit:
        return []
    return [
        {
            "kind": "outdated_intermediate_commit",
            "id": "agent_contributions",
            "detail": (
                f"agent_contributions evidence was generated against baseline_commit={envelope['baseline_commit']!r}, "
                f"which differs from the reported integration_commit={integration_commit!r}; treat its rows as "
                "potentially outdated relative to this report"
            ),
        }
    ]


def _changed_file_overlap_conflicts(pr_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    file_to_prs: dict[str, list[int]] = {}
    for entry in pr_entries:
        for path in entry["changed_files"]:
            file_to_prs.setdefault(path, []).append(entry["pr_number"])
    conflicts = []
    for path, prs in sorted(file_to_prs.items()):
        if len(prs) > 1:
            conflicts.append({"kind": "duplicate_ownership", "id": path, "pr_numbers": sorted(prs), "detail": f"{path} is changed by multiple PRs: {sorted(prs)}"})
    return conflicts


def _billing_infrastructure_status(pr_entries: list[dict[str, Any]], jobs: list[dict[str, Any]], dashboard: dict[str, Any]) -> dict[str, Any]:
    return {
        "ci_blocked_prs": sorted(p["pr_number"] for p in pr_entries if p["status_category"] == "CI_BLOCKED"),
        "billing_blocked_prs": sorted(p["pr_number"] for p in pr_entries if p["status_category"] == "BILLING_BLOCKED"),
        "billing_blocked_jobs": sorted(j["name"] for j in jobs if j["block_reason"] == "billing"),
        "infrastructure_blocked_jobs": sorted(j["name"] for j in jobs if j["block_reason"] == "infrastructure"),
        "dashboard_isolation_ok": dashboard["ok"],
    }


def _scientific_limitations(
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
    envelope_warnings: list[str],
) -> list[str]:
    limitations = [
        "This report aggregates evidence documents as-provided; it does not independently re-run or re-verify any pipeline.",
        "A PASS verdict reflects the declared threshold check in the source artifact, not an independent statistical review.",
        "A locally-computed checksum proves this compiler read the stated bytes; it is not independent verification of the underlying claim.",
    ]
    if any(r["claim_class"] in _WEAK_CLAIM_CLASSES for r in falsification_results):
        limitations.append("One or more falsification results are proxy/synthetic/unsupported claim_class and do not constitute formal empirical evidence.")
    if any(c["data_mode"] in ("synthetic", "proxy") for c in topology_checks):
        limitations.append("One or more topology validation checks are synthetic/proxy data_mode and do not constitute empirical validation.")
    if any(not r["is_formal_bayes_factor"] and r["metric_type"] != "unspecified_metric" for r in falsification_results):
        limitations.append("Falsification metrics reported as proxy quantities are not formal Bayes factors and must not be interpreted as such.")
    if any(c["metric_family"] == "graph_beta_1" for c in topology_checks) and any(c["metric_family"] == "spatial_charge" for c in topology_checks):
        limitations.append("This report contains both graph_beta_1 (connectivity-graph) and spatial_charge (field-topology) checks; a PASS on one is not evidence for the other.")
    limitations.extend(f"Source inventory warning: {w}" for w in envelope_warnings)
    return limitations


def _next_actions(conflicts: list[dict[str, Any]], cycles: list[list[int]], stacked_violations: list[dict[str, Any]], excluded: dict[int, str]) -> list[str]:
    actions: list[str] = []
    for cycle in cycles:
        actions.append(f"Resolve dependency cycle among PRs: {' -> '.join(str(n) for n in cycle)}.")
    for violation in stacked_violations:
        actions.append(f"Investigate stacking issue for PR #{violation['pr_number']}: {violation['detail']}.")
    for conflict in conflicts:
        actions.append(f"Resolve {conflict['kind']} conflict: {conflict['detail']}.")
    for pr, reason in sorted(excluded.items()):
        if reason.startswith("ci_") or reason in ("not_mergeable",):
            actions.append(f"Re-run or fix CI for PR #{pr} (currently excluded: {reason}).")
    return sorted(set(actions))


def _final_release_recommendation(
    *,
    status: str,
    conflicts: list[dict[str, Any]],
    cycles: list[list[int]],
    stacked_violations: list[dict[str, Any]],
    pr_entries: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    dashboard: dict[str, Any],
    order: list[int],
) -> str:
    if status == "partial":
        return INCOMPLETE_EVIDENCE

    # synthetic_pass_claim is a scientific-integrity violation (a weak
    # claim_class dressed up as PASS); billing_not_pass is an
    # infrastructure-integrity violation (a billing block dressed up as a
    # passing test) -- the two must route to different recommendations, or
    # this waterfall would itself blur the infrastructure-vs-scientific
    # distinction the rest of the compiler enforces.
    if any(c["kind"] == "synthetic_pass_claim" for c in conflicts):
        return "BLOCKED_BY_SCIENTIFIC_VALIDATION"

    infra_blocked = any(p["status_category"] in _INFRA_STATUS_CATEGORIES for p in pr_entries)
    ci_broken = any(j["status"] in ("failed", "timed_out") for j in jobs)
    billing_conflict = any(c["kind"] == "billing_not_pass" for c in conflicts)
    if infra_blocked or ci_broken or billing_conflict or dashboard["ok"] is False:
        return "BLOCKED_BY_CI"

    missing_branches = any(p["merge_status"] in ("branch_only", "unverified") for p in pr_entries) or bool(
        [v for v in stacked_violations if v["kind"] == "stacked_parent_missing"]
    )
    if missing_branches:
        return "BLOCKED_BY_MISSING_BRANCHES"

    if cycles or conflicts:
        return "BLOCKED_BY_CI"

    if order:
        return "READY_FOR_MERGE_REVIEW"
    return "READY_FOR_REVIEW"


def compile_report(
    manifest_path: Path,
    *,
    now: str | None = None,
    repo: str | None = None,
    integration_ref: str | None = None,
    integration_commit: str | None = None,
) -> dict[str, Any]:
    """Compile the mobile research-state report from a manifest of inputs.

    ``now`` should be an explicit ISO-8601 timestamp for deterministic/test
    use; when omitted, the current UTC time is used (making that one field,
    and only that field, non-deterministic across runs).
    """
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    loaded = manifest_mod.load_manifest(manifest_path)

    reconciliation_section, pr_nodes = build_reconciliation(loaded[manifest_mod.RECONCILIATION])
    agent_contributions_section = build_agent_contributions(loaded[manifest_mod.AGENT_CONTRIBUTIONS])
    dashboard_section = build_dashboard_isolation(loaded[manifest_mod.DASHBOARD_ISOLATION])
    test_runner_section = build_test_runner(loaded[manifest_mod.TEST_RUNNER])
    performance_section = build_benchmark_summary(loaded[manifest_mod.PERFORMANCE_BENCHMARK])
    memory_section = build_benchmark_summary(loaded[manifest_mod.MEMORY_EVIDENCE], memory_fields=True)
    dataset_section = build_dataset_provenance(loaded[manifest_mod.DATASET_PROVENANCE])
    topology_section = build_topology_validation(loaded[manifest_mod.TOPOLOGY_VALIDATION])
    falsification_section = build_falsification(loaded[manifest_mod.FALSIFICATION])
    merge_gate_section = build_merge_gate(loaded[manifest_mod.MERGE_GATE])

    edges = build_dependency_edges(pr_nodes)
    cycles = find_cycles(edges)
    layers = topological_layers([n.number for n in pr_nodes], edges)
    order, excluded = recommended_merge_order(pr_nodes)
    stacked_violations = find_stacked_parent_violations(pr_nodes)

    envelope = _envelope(loaded[manifest_mod.AGENT_CONTRIBUTIONS])

    conflicts: list[dict[str, Any]] = []
    conflicts += _merger_summary_conflicts(reconciliation_section["pull_requests"], agent_contributions_section["contributions"])
    conflicts += _merged_but_draft_or_unintegrated_conflicts(reconciliation_section["pull_requests"])
    conflicts += _synthetic_pass_conflicts(falsification_section["results"], topology_section["checks"], agent_contributions_section["contributions"])
    conflicts += _billing_not_pass_conflicts(test_runner_section["jobs"], agent_contributions_section["contributions"])
    conflicts += _outdated_commit_conflicts(envelope, integration_commit)
    conflicts += _changed_file_overlap_conflicts(reconciliation_section["pull_requests"])
    for cycle in cycles:
        conflicts.append({"kind": "dependency_cycle", "id": ",".join(str(n) for n in cycle), "pr_numbers": cycle, "detail": f"dependency cycle: {' -> '.join(str(n) for n in cycle)}"})
    for violation in stacked_violations:
        conflicts.append({**violation, "id": str(violation["pr_number"])})
    conflicts.sort(key=lambda c: (c["kind"], str(c.get("id", ""))))

    superseded_work = [
        {"pr_number": p["pr_number"], "superseded_by_pr": p["superseded_by_pr"]}
        for p in reconciliation_section["pull_requests"]
        if p["superseded_by_pr"] is not None
    ]

    stacked_relationships = [
        {"pr_number": pr_number, "depends_on": sorted(deps)} for pr_number, deps in sorted(edges.items()) if deps
    ]

    all_sections = [loaded[key] for key in manifest_mod.INPUT_SECTIONS]
    overall_status = "complete" if all(r.ok for r in all_sections) else "partial"
    completeness = {key: {"available": loaded[key].ok, "error": loaded[key].error} for key in manifest_mod.INPUT_SECTIONS}

    billing_infrastructure_status = _billing_infrastructure_status(
        reconciliation_section["pull_requests"], test_runner_section["jobs"], dashboard_section
    )

    unresolved_blockers = list(conflicts)
    if dashboard_section["ok"] is False:
        unresolved_blockers.append(
            {"kind": "dashboard_isolation_violation", "id": "dashboard_isolation", "detail": f"{len(dashboard_section['violations'])} forbidden-import violation(s) found"}
        )

    final_recommendation = _final_release_recommendation(
        status=overall_status,
        conflicts=conflicts,
        cycles=cycles,
        stacked_violations=stacked_violations,
        pr_entries=reconciliation_section["pull_requests"],
        jobs=test_runner_section["jobs"],
        dashboard=dashboard_section,
        order=order,
    )

    next_actions = _next_actions(conflicts, cycles, stacked_violations, excluded)

    limitations = _scientific_limitations(falsification_section["results"], topology_section["checks"], envelope["required_warnings"])

    report: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "generated_at": generated_at,
        "status": overall_status,
        "completeness": completeness,
        "repository_and_integration_commit": {
            "repo": repo,
            "integration_ref": integration_ref,
            "integration_commit": integration_commit,
            "agent_contributions_envelope": envelope,
        },
        "agent_contribution_table": agent_contributions_section,
        "pr_state": reconciliation_section,
        "merge_status_by_category": reconciliation_section["by_merge_status"],
        "stacked_relationships": {"edges": stacked_relationships, "layers": layers, "violations": stacked_violations},
        "superseded_work": superseded_work,
        "conflicts": conflicts,
        "ci_status": {
            "test_runner": test_runner_section,
            "pr_ci_status_counts": {
                status: sum(1 for p in reconciliation_section["pull_requests"] if p["ci_status"] == status)
                for status in ("passed", "failed", "pending", "not_started", "timed_out", "skipped", "unknown")
            },
        },
        "billing_infrastructure_status": billing_infrastructure_status,
        "test_totals": test_runner_section["totals"],
        "timeouts": {
            "test_jobs": sorted(j["name"] for j in test_runner_section["jobs"] if j["status"] == "timed_out"),
        },
        "performance_evidence": performance_section,
        "memory_evidence": memory_section,
        "provenance_status": dataset_section,
        "topology_validation_status": topology_section,
        "falsification_status": falsification_section,
        "scientific_limitations": limitations,
        "dashboard_isolation": dashboard_section,
        "unresolved_blockers": unresolved_blockers,
        "exact_next_actions": next_actions,
        "final_release_recommendation": final_recommendation,
        "recommended_merge_order": {"order": order, "excluded": {str(k): v for k, v in sorted(excluded.items())}},
        "merge_gate_decisions": merge_gate_section,
        "provenance": {
            "manifest_path": str(manifest_path),
            "source_checksums": {
                key: {"path": loaded[key].path, "sha256": loaded[key].sha256, "checksum_scope": "local"} for key in manifest_mod.INPUT_SECTIONS
            },
        },
    }
    return report
