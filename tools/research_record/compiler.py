"""Deterministic compilation of the research record.

``compile_record`` is the single entry point: it resolves a manifest of
local JSON/YAML/CSV evidence documents, normalizes each into a report
section, computes the cross-cutting sections (stacking graph, conflicts,
blockers, next actions, final recommendation), and returns one
JSON-serializable dict. See docs/reporting/research_record_contract.md
for the full contract, its 15 strict rules, and their code locations.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.research_record import epistemic, manifest as manifest_mod
from tools.research_record.graph import (
    build_dependency_edges,
    find_cycles,
    find_duplicate_violations,
    find_stacked_parent_violations,
    recommended_merge_order,
    topological_layers,
)
from tools.research_record.guardrails import INCOMPLETE_EVIDENCE
from tools.research_record.sections import (
    build_agent_contributions,
    build_artifact_references,
    build_benchmark_summary,
    build_blocker_reports,
    build_cohort_readiness,
    build_dashboard_isolation,
    build_dataset_provenance,
    build_falsification,
    build_merge_gate,
    build_operator_notes,
    build_reconciliation,
    build_release_manifest,
    build_scientific_gate_reports,
    build_test_runner,
    build_topology_validation,
)
from tools.research_record.versions import COMPILER_VERSION, INPUT_CONTRACT_VERSION, REPORT_SCHEMA_VERSION

_INFRA_STATUS_CATEGORIES = {"CI_BLOCKED", "BILLING_BLOCKED"}
_WEAK_CLAIM_CLASSES = {"synthetic", "proxy", "unsupported"}
_SCIENTIFIC_VERDICT_VALUES = {"PASS", "FAIL", "INCONCLUSIVE", "TIMEOUT", "unknown"}


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


def _integration_head_verification(envelope: dict[str, Any], integration_commit: str | None) -> dict[str, Any]:
    """A local merge commit does not prove a main-branch merge (rule 1), and a
    branch does not prove a PR merge (rule 2) -- so an ``--integration-commit``
    CLI value is never, on its own, "verified". It is only verified when an
    independently-sourced document (``evidence_source: github_api``) corroborates
    it -- exactly the same evidence class evidence_schema.yaml itself requires
    before recording a PR as merged.
    """
    if not integration_commit:
        return {"commit": None, "verified": False, "reason": "no integration_commit was supplied"}
    if envelope["evidence_source"] != "github_api":
        return {
            "commit": integration_commit,
            "verified": False,
            "reason": "no independently-sourced (evidence_source=github_api) document is available to corroborate this commit",
        }
    if envelope["baseline_commit"] != integration_commit:
        return {
            "commit": integration_commit,
            "verified": False,
            "reason": f"agent_contributions baseline_commit ({envelope['baseline_commit']!r}) does not match the declared integration_commit",
        }
    return {
        "commit": integration_commit,
        "verified": True,
        "reason": "agent_contributions envelope (evidence_source=github_api) baseline_commit matches the declared integration_commit",
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


def _merged_but_not_actually_merged_conflicts(pr_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for pr in pr_entries:
        if pr["merge_status"] != "merged":
            continue
        if pr["is_draft"] is True:
            conflicts.append(
                {
                    "kind": "open_pr_represented_as_merged",
                    "pr_number": pr["pr_number"],
                    "detail": f"PR #{pr['pr_number']} is recorded merge_status=merged while is_draft=true -- a draft cannot be merged",
                }
            )
        if pr["integration_status"] in ("integrated_only", "not_integrated"):
            conflicts.append(
                {
                    "kind": "open_pr_represented_as_merged",
                    "pr_number": pr["pr_number"],
                    "detail": (
                        f"PR #{pr['pr_number']} is recorded merge_status=merged but integration_status="
                        f"{pr['integration_status']!r} -- a local merge commit / integration branch presence does not prove a main-branch merge (rules 1-2)"
                    ),
                }
            )
        if pr["is_ancestor_of_target"] is False:
            conflicts.append(
                {
                    "kind": "open_pr_represented_as_merged",
                    "pr_number": pr["pr_number"],
                    "detail": f"PR #{pr['pr_number']} is recorded merge_status=merged but is_ancestor_of_target=false -- its branch is not actually in the target branch's history",
                }
            )
        if pr["superseded_by_pr"] is not None:
            conflicts.append(
                {
                    "kind": "superseded_but_merged",
                    "pr_number": pr["pr_number"],
                    "detail": f"PR #{pr['pr_number']} is recorded merge_status=merged and also superseded_by_pr={pr['superseded_by_pr']}",
                }
            )
    return conflicts


def _synthetic_and_proxy_pass_conflicts(
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
    scientific_gates: list[dict[str, Any]],
    contributions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rules 4/5: a proxy Bayes factor is not formal evidence, and synthetic
    results cannot be empirical evidence -- neither may be reported as a
    scientific PASS. TIMEOUT verdicts are excluded here on purpose (rule 8:
    a timeout is not a scientific outcome at all, so it cannot be a
    synthetic-PASS violation either -- see engineering_status instead)."""
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
    for gate in scientific_gates:
        if gate["claim_class"] in _WEAK_CLAIM_CLASSES and gate["verdict"] == "PASS":
            conflicts.append(
                {
                    "kind": "synthetic_pass_claim",
                    "id": gate["gate_id"],
                    "detail": f"scientific gate {gate['gate_id']!r} claims verdict=PASS with claim_class={gate['claim_class']!r}, which cannot establish a scientific PASS",
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


def _stale_integration_commit_conflicts(envelope: dict[str, Any], integration_commit: str | None) -> list[dict[str, Any]]:
    if not integration_commit or not envelope["baseline_commit"]:
        return []
    if envelope["baseline_commit"] == integration_commit:
        return []
    return [
        {
            "kind": "stale_integration_commit",
            "id": "agent_contributions",
            "detail": (
                f"agent_contributions evidence was generated against baseline_commit={envelope['baseline_commit']!r}, "
                f"which differs from the reported integration_commit={integration_commit!r}; treat its rows as "
                "potentially outdated relative to this record"
            ),
        }
    ]


def _changed_file_ownership(pr_entries: list[dict[str, Any]]) -> tuple[dict[str, list[int]], list[dict[str, Any]]]:
    file_to_prs: dict[str, list[int]] = {}
    for entry in pr_entries:
        for path in entry["changed_files"]:
            file_to_prs.setdefault(path, []).append(entry["pr_number"])
    ownership = {path: sorted(prs) for path, prs in sorted(file_to_prs.items())}
    conflicts = [
        {"kind": "duplicate_ownership", "id": path, "pr_numbers": prs, "detail": f"{path} is changed by multiple PRs: {prs}"}
        for path, prs in ownership.items()
        if len(prs) > 1
    ]
    return ownership, conflicts


def _duplicate_superseded_decisions(pr_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = []
    for entry in pr_entries:
        if entry["superseded_by_pr"] is not None:
            action = f"close_as_superseded_by_pr_{entry['superseded_by_pr']}"
        elif entry["duplicate_of_pr"] is not None:
            action = f"close_as_duplicate_of_pr_{entry['duplicate_of_pr']}"
        elif entry["mergeable"] is False or entry["merge_status"] == "blocked":
            action = "manual_review_required"
        else:
            continue
        decisions.append(
            {
                "pr_number": entry["pr_number"],
                "superseded_by_pr": entry["superseded_by_pr"],
                "duplicate_of_pr": entry["duplicate_of_pr"],
                "recommended_action": action,
            }
        )
    decisions.sort(key=lambda d: d["pr_number"])
    return decisions


def _pr_buckets(pr_entries: list[dict[str, Any]]) -> dict[str, list[int]]:
    return {
        "open": sorted(p["pr_number"] for p in pr_entries if p["merge_status"] == "open" and p["is_draft"] is not True),
        "draft": sorted(p["pr_number"] for p in pr_entries if p["is_draft"] is True),
        "closed": sorted(p["pr_number"] for p in pr_entries if p["merge_status"] == "closed"),
        "merged": sorted(p["pr_number"] for p in pr_entries if p["merge_status"] == "merged"),
        "integrated_only": sorted(p["pr_number"] for p in pr_entries if p["integration_status"] == "integrated_only"),
    }


def _engineering_status(
    pr_entries: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    dashboard: dict[str, Any],
    topology_checks: list[dict[str, Any]],
    falsification_results: list[dict[str, Any]],
    *,
    all_engineering_inputs_available: bool,
) -> dict[str, Any]:
    ci_broken_jobs = sorted(j["name"] for j in jobs if j["status"] in ("failed", "timed_out"))
    scientific_check_timeouts = sorted(
        [c["name"] for c in topology_checks if c["verdict"] == "TIMEOUT"]
        + [r["hypothesis_id"] for r in falsification_results if r["verdict"] == "TIMEOUT"]
    )
    billing_blocked_jobs = sorted(j["name"] for j in jobs if j["block_reason"] == "billing")
    infrastructure_blocked_jobs = sorted(j["name"] for j in jobs if j["block_reason"] == "infrastructure")
    ci_blocked_prs = sorted(p["pr_number"] for p in pr_entries if p["status_category"] == "CI_BLOCKED")
    billing_blocked_prs = sorted(p["pr_number"] for p in pr_entries if p["status_category"] == "BILLING_BLOCKED")

    blocked = bool(
        ci_broken_jobs or scientific_check_timeouts or billing_blocked_jobs or infrastructure_blocked_jobs
        or ci_blocked_prs or billing_blocked_prs or dashboard["ok"] is False
    )
    label = "blocked" if blocked else ("unknown" if not all_engineering_inputs_available else "clear")

    return {
        "label": label,
        "ci_broken_jobs": ci_broken_jobs,
        "scientific_check_timeouts": scientific_check_timeouts,
        "billing_blocked_jobs": billing_blocked_jobs,
        "infrastructure_blocked_jobs": infrastructure_blocked_jobs,
        "ci_blocked_prs": ci_blocked_prs,
        "billing_blocked_prs": billing_blocked_prs,
        "dashboard_isolation_ok": dashboard["ok"],
    }


def _scientific_status(
    topology_checks: list[dict[str, Any]],
    falsification_results: list[dict[str, Any]],
    cohorts: list[dict[str, Any]],
    synthetic_pass_violation_count: int,
    *,
    all_scientific_inputs_available: bool,
) -> dict[str, Any]:
    def _verdict_counts(items: list[dict[str, Any]]) -> dict[str, int]:
        counts = {"PASS": 0, "FAIL": 0, "INCONCLUSIVE": 0, "TIMEOUT": 0, "unknown": 0}
        for item in items:
            counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
        return counts

    topology_family_counts = {
        family: _verdict_counts([c for c in topology_checks if c["metric_family"] == family])
        for family in ("graph_beta_1", "spatial_charge", "other", "unclassified")
        if any(c["metric_family"] == family for c in topology_checks)
    }
    falsification_counts = _verdict_counts(falsification_results)
    cohort_ready = sum(1 for c in cohorts if c["ready"])
    cohort_not_ready = sum(1 for c in cohorts if not c["ready"])

    if synthetic_pass_violation_count:
        label = "blocked"
    elif not all_scientific_inputs_available:
        label = "unknown"
    elif cohort_not_ready or falsification_counts["FAIL"] or any(c.get("FAIL", 0) for c in topology_family_counts.values()):
        label = "not_yet_established"
    else:
        label = "clear"

    return {
        "label": label,
        "topology_family_verdict_counts": topology_family_counts,
        "falsification_verdict_counts": falsification_counts,
        "cohort_ready_count": cohort_ready,
        "cohort_not_ready_count": cohort_not_ready,
        "synthetic_pass_claim_violations": synthetic_pass_violation_count,
    }


def _scientific_limitations(
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
    cohorts: list[dict[str, Any]],
    envelope_warnings: list[str],
) -> list[str]:
    limitations = [
        "This record aggregates evidence documents as-provided; it does not independently re-run or re-verify any pipeline.",
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
        limitations.append("This record contains both graph_beta_1 (connectivity-graph) and spatial_charge (field-topology) checks; a PASS on one is not evidence for the other.")
    if any(c["verdict"] == "TIMEOUT" for c in topology_checks) or any(r["verdict"] == "TIMEOUT" for r in falsification_results):
        limitations.append("One or more scientific checks timed out; a timeout produced no result and must not be read as PASS, FAIL, or INCONCLUSIVE.")
    if any(not c["ready"] for c in cohorts):
        limitations.append("One or more cohorts are not yet ready (insufficient subjects, unpaired, or non-empirical data_mode); readiness is derived by this compiler, not sourced verbatim.")
    limitations.extend(f"Source inventory warning: {w}" for w in envelope_warnings)
    return limitations


def _classify_epistemic_items(
    *,
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
    scientific_gates: list[dict[str, Any]],
    contributions: list[dict[str, Any]],
    performance_benchmarks: list[dict[str, Any]],
    memory_benchmarks: list[dict[str, Any]],
    test_jobs: list[dict[str, Any]],
    pr_entries: list[dict[str, Any]],
    dashboard: dict[str, Any],
    operator_notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify every claim/fact this record carries into one of the nine
    epistemic labels (epistemic.py). This is the single place that decides
    the label -- nothing downstream re-derives it, so "never promote an
    engineering PASS to a scientific PASS" holds by construction: engineering
    fact / benchmark result items never carry a ``verdict`` field, so they
    can never feed _scientific_verdict()."""
    items: list[dict[str, Any]] = []

    for r in falsification_results:
        items.append(
            {
                "label": epistemic.classify_scientific_item(claim_class=r["claim_class"], data_mode=r["data_mode"], is_formal=r["is_formal_bayes_factor"]),
                "source": "falsification",
                "id": r["hypothesis_id"],
                "summary": f"{r['hypothesis_id']}: {r['metric_display_label']} = {r['metric_value']}",
                "verdict": r["verdict"],
            }
        )
    for c in topology_checks:
        # Topology checks carry only data_mode, not their own claim_class --
        # map it onto the same vocabulary classify_scientific_item expects.
        topology_claim_class = c["data_mode"] if c["data_mode"] in ("synthetic", "proxy", "empirical") else (
            "unavailable" if c["data_mode"] in ("local-unknown", "unknown") else "none"
        )
        items.append(
            {
                "label": epistemic.classify_scientific_item(claim_class=topology_claim_class, data_mode=c["data_mode"], is_formal=False),
                "source": "topology_validation",
                "id": c["name"],
                "summary": f"{c['name']} ({c['metric_family']}): {c['metric_value']} {c['unit'] or ''}".strip(),
                "verdict": c["verdict"],
            }
        )
    for g in scientific_gates:
        items.append(
            {
                "label": epistemic.classify_scientific_item(claim_class=g["claim_class"], data_mode=g["data_mode"], is_formal=False),
                "source": "scientific_gate_reports",
                "id": g["gate_id"],
                "summary": g["description"] or g["gate_id"],
                "verdict": g["verdict"],
            }
        )
    for c in contributions:
        rc = c["research_classification"]
        items.append(
            {
                "label": epistemic.classify_contribution(claim_class=rc["claim_class"], value_class=rc["value_class"]),
                "source": "agent_contributions",
                "id": c["id"],
                "summary": c["title"] or c["id"],
                "verdict": None,
            }
        )
    for b in performance_benchmarks:
        items.append({"label": epistemic.BENCHMARK_RESULT, "source": "performance_benchmark", "id": b["name"], "summary": f"{b['name']} = {b['value']} {b['unit'] or ''}".strip(), "verdict": None})
    for b in memory_benchmarks:
        items.append({"label": epistemic.BENCHMARK_RESULT, "source": "memory_evidence", "id": b["name"], "summary": f"{b['name']} = {b['value']} {b['unit'] or ''}".strip(), "verdict": None})
    for j in test_jobs:
        items.append({"label": epistemic.ENGINEERING_FACT, "source": "test_runner", "id": j["name"], "summary": f"job {j['name']!r} status={j['status']}", "verdict": None})
    for p in pr_entries:
        items.append({"label": epistemic.ENGINEERING_FACT, "source": "reconciliation", "id": str(p["pr_number"]), "summary": f"PR #{p['pr_number']} merge_status={p['merge_status']}", "verdict": None})
    if dashboard["ok"] is not None:
        items.append({"label": epistemic.ENGINEERING_FACT, "source": "dashboard_isolation", "id": "dashboard_isolation", "summary": f"dashboard isolation ok={dashboard['ok']}", "verdict": None})
    for n in operator_notes:
        items.append({"label": epistemic.classify_operator_note(n["declared_epistemic_label"]), "source": "operator_notes", "id": n["note"][:80], "summary": n["note"], "verdict": None})

    items.sort(key=lambda i: (i["label"], i["source"], i["id"]))
    return items


def _scientific_verdict(items: list[dict[str, Any]]) -> str:
    """Roll up a single top-level scientific verdict from only the items
    labeled "formal statistical evidence" or "empirical observation" --
    the only two labels rule 5 permits to ever say PASS/FAIL (never
    "engineering fact"/"benchmark result", and never a synthetic/proxy/
    unsupported/speculative claim)."""
    eligible = [
        i for i in items
        if i["label"] in epistemic.SCIENTIFIC_VERDICT_ELIGIBLE_LABELS and i["verdict"] in ("PASS", "FAIL", "INCONCLUSIVE")
    ]
    if not eligible:
        return "NOT_APPLICABLE"
    if any(i["verdict"] == "FAIL" for i in eligible):
        return "FAIL"
    if any(i["verdict"] == "PASS" for i in eligible):
        return "PASS"
    return "INCONCLUSIVE"


def _final_conclusions(*, engineering_label: str, scientific_verdict_value: str, final_recommendation: str, blocker_count: int) -> dict[str, Any]:
    """Deliberately hedged: this section states engineering/process
    conclusions only. It does not itself constitute scientific evidence,
    and must never be read as one, regardless of what scientific_verdict
    says -- scientific_verdict summarizes what the aggregated evidence
    documents claim, not an independent finding by this compiler."""
    return {
        "engineering_conclusion": f"Engineering/process status: {engineering_label}; {blocker_count} unresolved blocker(s); release recommendation {final_recommendation}.",
        "scientific_conclusion_caveat": (
            "This record does not itself constitute scientific evidence. The scientific_verdict field above "
            f"({scientific_verdict_value!r}) reflects only the declared threshold checks in the formal/empirical-labeled "
            "source artifacts it aggregates; it is not an independent statistical finding and requires independent "
            "scientific review before being treated as evidence of anything."
        ),
    }


def _canonical_checksum(record_without_checksum: dict[str, Any]) -> str:
    """A checksum of the record's own deterministic content (everything
    except this field itself), so a consumer can verify the record was not
    altered after compilation. Deterministic only when ``now`` was pinned;
    otherwise generated_at makes each run's checksum unique by design."""
    canonical = json.dumps(record_without_checksum, sort_keys=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _next_actions(
    conflicts: list[dict[str, Any]],
    cycles: list[list[int]],
    stacked_violations: list[dict[str, Any]],
    duplicate_violations: list[dict[str, Any]],
    excluded: dict[int, str],
) -> list[str]:
    actions: list[str] = []
    for cycle in cycles:
        actions.append(f"Resolve dependency cycle among PRs: {' -> '.join(str(n) for n in cycle)}.")
    for violation in stacked_violations:
        actions.append(f"Investigate stacking issue for PR #{violation['pr_number']}: {violation['detail']}.")
    for violation in duplicate_violations:
        actions.append(f"Resolve {violation['kind']} for PR #{violation['pr_number']}: {violation['detail']}.")
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
    duplicate_violations: list[dict[str, Any]],
    pr_entries: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    dashboard: dict[str, Any],
    scientific_check_timed_out: bool,
    order: list[int],
) -> str:
    if status == "partial":
        return INCOMPLETE_EVIDENCE

    # synthetic_pass_claim is a scientific-integrity violation; everything
    # else below (billing, CI failures/timeouts, a scientific check that
    # itself timed out) is an engineering/infrastructure concern (rule 12
    # / rule 8) and must never be routed to BLOCKED_BY_SCIENTIFIC_VALIDATION.
    if any(c["kind"] == "synthetic_pass_claim" for c in conflicts):
        return "BLOCKED_BY_SCIENTIFIC_VALIDATION"

    infra_blocked = any(p["status_category"] in _INFRA_STATUS_CATEGORIES for p in pr_entries)
    ci_broken = any(j["status"] in ("failed", "timed_out") for j in jobs)
    billing_conflict = any(c["kind"] == "billing_not_pass" for c in conflicts)
    if infra_blocked or ci_broken or billing_conflict or scientific_check_timed_out or dashboard["ok"] is False:
        return "BLOCKED_BY_CI"

    missing_branches = any(p["merge_status"] in ("branch_only", "unverified") for p in pr_entries) or bool(
        [v for v in stacked_violations if v["kind"] == "stacked_parent_missing"]
    )
    if missing_branches:
        return "BLOCKED_BY_MISSING_BRANCHES"

    if cycles or conflicts or duplicate_violations:
        return "BLOCKED_BY_CI"

    if order:
        return "READY_FOR_MERGE_REVIEW"
    return "READY_FOR_REVIEW"


def compile_record(
    manifest_path: Path,
    *,
    now: str | None = None,
    repo: str | None = None,
    origin_main_commit: str | None = None,
    integration_ref: str | None = None,
    integration_commit: str | None = None,
) -> dict[str, Any]:
    """Compile the research record from a manifest of local evidence inputs.

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
    cohort_section = build_cohort_readiness(loaded[manifest_mod.COHORT_READINESS])
    topology_section = build_topology_validation(loaded[manifest_mod.TOPOLOGY_VALIDATION])
    falsification_section = build_falsification(loaded[manifest_mod.FALSIFICATION])
    merge_gate_section = build_merge_gate(loaded[manifest_mod.MERGE_GATE])
    release_manifest_section = build_release_manifest(loaded[manifest_mod.RELEASE_MANIFEST])
    scientific_gate_section = build_scientific_gate_reports(loaded[manifest_mod.SCIENTIFIC_GATE_REPORTS])
    blocker_reports_section = build_blocker_reports(loaded[manifest_mod.BLOCKER_REPORTS])
    artifact_references_section = build_artifact_references(loaded[manifest_mod.ARTIFACT_REFERENCES])
    operator_notes_section = build_operator_notes(loaded[manifest_mod.OPERATOR_NOTES])

    edges = build_dependency_edges(pr_nodes)
    cycles = find_cycles(edges)
    layers = topological_layers([n.number for n in pr_nodes], edges)
    order, excluded = recommended_merge_order(pr_nodes)
    stacked_violations = find_stacked_parent_violations(pr_nodes)
    duplicate_violations = find_duplicate_violations(pr_nodes)

    envelope = _envelope(loaded[manifest_mod.AGENT_CONTRIBUTIONS])
    verified_head = _integration_head_verification(envelope, integration_commit)

    conflicts: list[dict[str, Any]] = []
    conflicts += _merger_summary_conflicts(reconciliation_section["pull_requests"], agent_contributions_section["contributions"])
    conflicts += _merged_but_not_actually_merged_conflicts(reconciliation_section["pull_requests"])
    synthetic_pass_conflicts = _synthetic_and_proxy_pass_conflicts(
        falsification_section["results"], topology_section["checks"], scientific_gate_section["gates"], agent_contributions_section["contributions"]
    )
    conflicts += synthetic_pass_conflicts
    conflicts += _billing_not_pass_conflicts(test_runner_section["jobs"], agent_contributions_section["contributions"])
    conflicts += _stale_integration_commit_conflicts(envelope, integration_commit)
    changed_file_ownership, ownership_conflicts = _changed_file_ownership(reconciliation_section["pull_requests"])
    conflicts += ownership_conflicts
    for cycle in cycles:
        conflicts.append({"kind": "dependency_cycle", "id": ",".join(str(n) for n in cycle), "pr_numbers": cycle, "detail": f"dependency cycle: {' -> '.join(str(n) for n in cycle)}"})
    for violation in stacked_violations:
        conflicts.append({**violation, "id": str(violation["pr_number"])})
    for violation in duplicate_violations:
        conflicts.append({**violation, "id": str(violation["pr_number"])})
    conflicts.sort(key=lambda c: (c["kind"], str(c.get("id", ""))))

    duplicate_superseded_decisions = _duplicate_superseded_decisions(reconciliation_section["pull_requests"])
    pr_buckets = _pr_buckets(reconciliation_section["pull_requests"])
    branch_ancestry = [
        {"pr_number": p["pr_number"], "branch": p["branch"], "is_ancestor_of_target": p["is_ancestor_of_target"]}
        for p in reconciliation_section["pull_requests"]
    ]
    stacked_relationships = [
        {"pr_number": pr_number, "depends_on": sorted(deps)} for pr_number, deps in sorted(edges.items()) if deps
    ]

    all_sections = [loaded[key] for key in manifest_mod.INPUT_SECTIONS]
    overall_status = "complete" if all(r.ok for r in all_sections) else "partial"
    completeness = {key: {"available": loaded[key].ok, "error": loaded[key].error} for key in manifest_mod.INPUT_SECTIONS}

    scientific_check_timed_out = any(c["verdict"] == "TIMEOUT" for c in topology_section["checks"]) or any(
        r["verdict"] == "TIMEOUT" for r in falsification_section["results"]
    )

    # "unknown" (rather than a possibly-overconfident "clear") whenever any
    # of the axis's relevant inputs is missing -- engineering/scientific
    # status must not claim more confidence than the evidence supports.
    all_engineering_inputs_available = (
        loaded[manifest_mod.RECONCILIATION].ok and loaded[manifest_mod.TEST_RUNNER].ok and loaded[manifest_mod.DASHBOARD_ISOLATION].ok
    )
    all_scientific_inputs_available = (
        loaded[manifest_mod.TOPOLOGY_VALIDATION].ok and loaded[manifest_mod.FALSIFICATION].ok and loaded[manifest_mod.COHORT_READINESS].ok
    )

    engineering_status = _engineering_status(
        reconciliation_section["pull_requests"],
        test_runner_section["jobs"],
        dashboard_section,
        topology_section["checks"],
        falsification_section["results"],
        all_engineering_inputs_available=all_engineering_inputs_available,
    )
    scientific_status = _scientific_status(
        topology_section["checks"],
        falsification_section["results"],
        cohort_section["cohorts"],
        len(synthetic_pass_conflicts),
        all_scientific_inputs_available=all_scientific_inputs_available,
    )

    unresolved_blockers = list(conflicts)
    if dashboard_section["ok"] is False:
        unresolved_blockers.append(
            {"kind": "dashboard_isolation_violation", "id": "dashboard_isolation", "detail": f"{len(dashboard_section['violations'])} forbidden-import violation(s) found"}
        )
    for b in blocker_reports_section["blockers"]:
        unresolved_blockers.append(
            {"kind": "reported_blocker", "id": b["blocker_id"], "severity": b["severity"], "source": b["source"], "detail": b["description"], "origin": "reported"}
        )

    epistemic_items = _classify_epistemic_items(
        falsification_results=falsification_section["results"],
        topology_checks=topology_section["checks"],
        scientific_gates=scientific_gate_section["gates"],
        contributions=agent_contributions_section["contributions"],
        performance_benchmarks=performance_section["benchmarks"],
        memory_benchmarks=memory_section["benchmarks"],
        test_jobs=test_runner_section["jobs"],
        pr_entries=reconciliation_section["pull_requests"],
        dashboard=dashboard_section,
        operator_notes=operator_notes_section["notes"],
    )
    scientific_verdict_value = _scientific_verdict(epistemic_items)

    final_recommendation = _final_release_recommendation(
        status=overall_status,
        conflicts=conflicts,
        cycles=cycles,
        stacked_violations=stacked_violations,
        duplicate_violations=duplicate_violations,
        pr_entries=reconciliation_section["pull_requests"],
        jobs=test_runner_section["jobs"],
        dashboard=dashboard_section,
        scientific_check_timed_out=scientific_check_timed_out,
        order=order,
    )

    next_actions = _next_actions(conflicts, cycles, stacked_violations, duplicate_violations, excluded)
    next_actions += [f"Address reported blocker {b['blocker_id']!r} (severity={b['severity']}): {b['description']}." for b in blocker_reports_section["blockers"]]
    next_actions = sorted(set(next_actions))

    limitations = _scientific_limitations(
        falsification_section["results"], topology_section["checks"], cohort_section["cohorts"], envelope["required_warnings"]
    )

    failed_jobs = sorted(j["name"] for j in test_runner_section["jobs"] if j["status"] == "failed")
    failed_ci_prs = sorted(p["pr_number"] for p in reconciliation_section["pull_requests"] if p["ci_status"] == "failed")

    final_conclusions = _final_conclusions(
        engineering_label=engineering_status["label"],
        scientific_verdict_value=scientific_verdict_value,
        final_recommendation=final_recommendation,
        blocker_count=len(unresolved_blockers),
    )

    record: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "compiler_version": COMPILER_VERSION,
        "generated_at": generated_at,
        "status": overall_status,
        "completeness": completeness,
        "repository_identity": {"repo": repo},
        "origin_main_commit": origin_main_commit,
        "integration_branch_and_verified_head": {
            "integration_ref": integration_ref,
            **verified_head,
            "agent_contributions_envelope": envelope,
        },
        "agent_contribution_table": agent_contributions_section,
        "pr_state": reconciliation_section,
        "pr_buckets": pr_buckets,
        "branch_ancestry": branch_ancestry,
        "stacked_dependencies": {"edges": stacked_relationships, "layers": layers, "violations": stacked_violations},
        "duplicate_superseded_decisions": duplicate_superseded_decisions,
        "changed_file_ownership": changed_file_ownership,
        "conflicts": conflicts,
        "ci_status": {
            "test_runner": test_runner_section,
            "pr_ci_status_counts": {
                status: sum(1 for p in reconciliation_section["pull_requests"] if p["ci_status"] == status)
                for status in ("passed", "failed", "pending", "not_started", "timed_out", "skipped", "unknown")
            },
        },
        "billing_runner_status": {
            "billing_blocked_jobs": engineering_status["billing_blocked_jobs"],
            "infrastructure_blocked_jobs": engineering_status["infrastructure_blocked_jobs"],
            "billing_blocked_prs": engineering_status["billing_blocked_prs"],
            "ci_blocked_prs": engineering_status["ci_blocked_prs"],
        },
        "test_totals": test_runner_section["totals"],
        "failures": {"failed_jobs": failed_jobs, "failed_ci_prs": failed_ci_prs},
        "timeouts": {
            "test_jobs": sorted(j["name"] for j in test_runner_section["jobs"] if j["status"] == "timed_out"),
            "scientific_checks": engineering_status["scientific_check_timeouts"],
        },
        "performance_evidence": performance_section,
        "memory_evidence": memory_section,
        "provenance": dataset_section,
        "cohort_readiness": cohort_section,
        "topology_readiness": topology_section,
        "falsification_semantics": falsification_section,
        "scientific_limitations": limitations,
        "dashboard_isolation": dashboard_section,
        "engineering_status": engineering_status,
        "scientific_status": scientific_status,
        "unresolved_blockers": unresolved_blockers,
        "next_actions": next_actions,
        "next_priorities": next_actions,
        "final_release_recommendation": final_recommendation,
        "recommended_merge_order": {"order": order, "excluded": {str(k): v for k, v in sorted(excluded.items())}},
        "merge_gate_decisions": merge_gate_section,
        "release_manifest": release_manifest_section,
        "scientific_gate_reports": scientific_gate_section,
        "blocker_reports": blocker_reports_section,
        "artifact_references": artifact_references_section,
        "operator_notes": operator_notes_section,
        "epistemic_classification": {
            "items": epistemic_items,
            "confirmed_engineering_facts": [i for i in epistemic_items if i["label"] == epistemic.ENGINEERING_FACT],
            "benchmark_results": [i for i in epistemic_items if i["label"] == epistemic.BENCHMARK_RESULT],
            "hypotheses": [i for i in epistemic_items if i["label"] == epistemic.HYPOTHESIS],
            "speculation": [i for i in epistemic_items if i["label"] == epistemic.SPECULATION],
            "unsupported_claims": [i for i in epistemic_items if i["label"] == epistemic.UNSUPPORTED_CLAIM],
            "synthetic_demonstrations": [i for i in epistemic_items if i["label"] == epistemic.SYNTHETIC_DEMONSTRATION],
            "empirical_observations": [i for i in epistemic_items if i["label"] == epistemic.EMPIRICAL_OBSERVATION],
            "proxy_inferences": [i for i in epistemic_items if i["label"] == epistemic.PROXY_INFERENCE],
            "formal_statistical_evidence": [i for i in epistemic_items if i["label"] == epistemic.FORMAL_STATISTICAL_EVIDENCE],
        },
        "scientific_verdict": scientific_verdict_value,
        "final_conclusions": final_conclusions,
        "record_provenance": {
            "manifest_path": str(manifest_path),
            "source_checksums": {
                key: {"path": loaded[key].path, "sha256": loaded[key].sha256, "checksum_scope": "local"} for key in manifest_mod.INPUT_SECTIONS
            },
        },
    }
    record["canonical_checksum"] = _canonical_checksum(record)
    return record
