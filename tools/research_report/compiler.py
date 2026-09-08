"""Deterministic compilation of the unified research-state report.

``compile_report`` is the single entry point: it resolves a manifest of
input evidence documents, normalizes each into a report section, computes
the cross-cutting sections (dependency graph, conflicts, synthetic-vs-
empirical distinction, recommended merge order, final recommendation), and
returns one JSON-serializable dict. See docs/research/report_contract.md
for the full contract and docs/research/report_contract.md#guardrails for
the labeling rules enforced here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.research_report import manifest as manifest_mod
from tools.research_report.graph import build_dependency_edges, find_cycles, recommended_merge_order, topological_layers
from tools.research_report.sections import (
    build_benchmark_summary,
    build_capability_snapshot,
    build_dataset_provenance,
    build_falsification,
    build_interoperability,
    build_merge_gate,
    build_pr_reconciliation,
    build_pr_retirement,
    build_test_runner,
    build_topology_validation,
)
from tools.research_report.versions import COMPILER_VERSION, REPORT_SCHEMA_VERSION


def _changed_file_ownership(pr_entries: list[dict[str, Any]]) -> dict[str, Any]:
    file_to_prs: dict[str, list[int]] = {}
    for entry in pr_entries:
        for path in entry["changed_files"]:
            file_to_prs.setdefault(path, []).append(entry["pr_number"])
    ownership = {path: sorted(prs) for path, prs in sorted(file_to_prs.items())}
    overlaps = {path: prs for path, prs in ownership.items() if len(prs) > 1}
    return {"by_file": ownership, "overlapping_files": overlaps}


def _contradictions(
    pr_entries: list[dict[str, Any]],
    retirement_decisions: list[dict[str, Any]],
    merge_gate_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    pr_by_number = {e["pr_number"]: e for e in pr_entries}

    for decision in retirement_decisions:
        pr = pr_by_number.get(decision["pr_number"])
        if pr is None:
            continue
        if decision["action"] == "retire" and pr["state"] == "open" and pr["superseded_by_pr"] is None:
            conflicts.append(
                {
                    "kind": "contradictory_pr_status",
                    "pr_number": decision["pr_number"],
                    "detail": "pr_retirement recommends retiring a PR that reconciliation reports as open with no superseding PR recorded",
                }
            )
        if decision["action"] == "superseded" and decision["superseded_by"] is not None:
            if pr["superseded_by_pr"] != decision["superseded_by"]:
                conflicts.append(
                    {
                        "kind": "contradictory_pr_status",
                        "pr_number": decision["pr_number"],
                        "detail": (
                            f"pr_retirement says superseded_by={decision['superseded_by']} but "
                            f"reconciliation says superseded_by_pr={pr['superseded_by_pr']}"
                        ),
                    }
                )

    for decision in merge_gate_decisions:
        pr = pr_by_number.get(decision["pr_number"])
        if pr is None:
            continue
        if decision["decision"] == "allow" and pr["state"] != "open":
            conflicts.append(
                {
                    "kind": "contradictory_pr_status",
                    "pr_number": decision["pr_number"],
                    "detail": f"merge_gate allows PR #{decision['pr_number']} but reconciliation reports state={pr['state']}",
                }
            )

    return sorted(conflicts, key=lambda c: (c["kind"], c["pr_number"]))


def _synthetic_vs_empirical(
    datasets: list[dict[str, Any]],
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    def tally(items: list[dict[str, Any]], id_key: str) -> dict[str, Any]:
        return {
            "synthetic": sorted(i[id_key] for i in items if i["data_mode"] == "synthetic"),
            "empirical": sorted(i[id_key] for i in items if i["data_mode"] == "empirical"),
            "unknown": sorted(i[id_key] for i in items if i["data_mode"] == "unknown"),
        }

    return {
        "datasets": tally(datasets, "dataset_id"),
        "falsification_results": tally(falsification_results, "hypothesis_id"),
        "topology_checks": tally(topology_checks, "name"),
        "guardrail": "Entries are grouped strictly by their own declared data_mode field; synthetic data is never re-labeled empirical.",
    }


def _scientific_limitations(
    falsification_results: list[dict[str, Any]],
    topology_checks: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
) -> list[str]:
    limitations = [
        "This report aggregates evidence documents as-provided; it does not independently re-run or re-verify any pipeline.",
        "A PASS verdict reflects the declared threshold check in the source artifact, not an independent statistical review.",
    ]
    if any(r["data_mode"] == "synthetic" for r in falsification_results):
        limitations.append("One or more falsification results are derived from synthetic data and do not constitute empirical validation.")
    if any(c["data_mode"] == "synthetic" for c in topology_checks):
        limitations.append("One or more topology validation checks are derived from synthetic data and do not constitute empirical validation.")
    if any(d["data_mode"] == "synthetic" for d in datasets):
        limitations.append("One or more datasets in scope are synthetic and are not a substitute for empirical replication.")
    if any(not r["is_formal_bayes_factor"] and r["metric_type"] != "unspecified_metric" for r in falsification_results):
        limitations.append("Falsification metrics reported as proxy quantities (e.g. proxy_K) are not formal Bayes factors and must not be interpreted as such.")
    return limitations


def _final_release_recommendation(
    *,
    status: str,
    cycles: list[list[int]],
    conflicts: list[dict[str, Any]],
    recommended_order: list[int],
) -> str:
    if status == "partial":
        return "incomplete_insufficient_data"
    if cycles:
        return "hold_dependency_cycle"
    if conflicts:
        return "hold_unresolved_conflicts"
    if recommended_order:
        return "proceed_with_recommended_merge_order"
    return "no_action_no_eligible_prs"


def compile_report(
    manifest_path: Path,
    *,
    now: str | None = None,
    repo: str | None = None,
    base_ref: str | None = None,
    base_commit: str | None = None,
) -> dict[str, Any]:
    """Compile the unified research-state report from a manifest of inputs.

    ``now`` should be an explicit ISO-8601 timestamp for deterministic/test
    use; when omitted, the current UTC time is used (making that one field,
    and only that field, non-deterministic across runs -- guardrail #10).
    """
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    loaded = manifest_mod.load_manifest(manifest_path)

    pr_section, pr_nodes = build_pr_reconciliation(loaded[manifest_mod.RECONCILIATION])
    capability_section = build_capability_snapshot(loaded[manifest_mod.CAPABILITY_SNAPSHOT])
    dataset_section = build_dataset_provenance(loaded[manifest_mod.DATASET_PROVENANCE])
    falsification_section = build_falsification(loaded[manifest_mod.FALSIFICATION])
    performance_section = build_benchmark_summary(loaded[manifest_mod.PERFORMANCE_BENCHMARK])
    memory_section = build_benchmark_summary(loaded[manifest_mod.MEMORY_EVIDENCE])
    interoperability_section = build_interoperability(loaded[manifest_mod.INTEROPERABILITY])
    topology_section = build_topology_validation(loaded[manifest_mod.TOPOLOGY_VALIDATION])
    test_runner_section = build_test_runner(loaded[manifest_mod.TEST_RUNNER])
    merge_gate_section = build_merge_gate(loaded[manifest_mod.MERGE_GATE])
    pr_retirement_section = build_pr_retirement(loaded[manifest_mod.PR_RETIREMENT])

    edges = build_dependency_edges(pr_nodes)
    cycles = find_cycles(edges)
    layers = topological_layers([n.number for n in pr_nodes], edges)
    order, excluded = recommended_merge_order(pr_nodes)

    ownership = _changed_file_ownership(pr_section["pull_requests"])
    contradictions = _contradictions(
        pr_section["pull_requests"], pr_retirement_section["decisions"], merge_gate_section["decisions"]
    )
    conflicts: list[dict[str, Any]] = list(contradictions)
    for cycle in cycles:
        conflicts.append({"kind": "dependency_cycle", "pr_numbers": cycle, "detail": f"dependency cycle: {' -> '.join(str(n) for n in cycle)}"})
    for path, prs in ownership["overlapping_files"].items():
        conflicts.append({"kind": "duplicate_ownership", "path": path, "pr_numbers": prs, "detail": f"{path} is changed by multiple PRs: {prs}"})
    conflicts.sort(key=lambda c: (c["kind"], str(c.get("pr_number", c.get("pr_numbers", c.get("path", ""))))))

    synthetic_vs_empirical = _synthetic_vs_empirical(
        dataset_section["datasets"], falsification_section["results"], topology_section["checks"]
    )
    limitations = _scientific_limitations(
        falsification_section["results"], topology_section["checks"], dataset_section["datasets"]
    )

    all_sections = [
        loaded[key] for key in manifest_mod.INPUT_SECTIONS
    ]
    overall_status = "complete" if all(r.ok for r in all_sections) else "partial"
    completeness = {
        key: {"available": loaded[key].ok, "error": loaded[key].error} for key in manifest_mod.INPUT_SECTIONS
    }

    final_recommendation = _final_release_recommendation(
        status=overall_status, cycles=cycles, conflicts=conflicts, recommended_order=order
    )

    report: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "generated_at": generated_at,
        "status": overall_status,
        "completeness": completeness,
        "repository_and_baseline": {
            "repo": repo,
            "base_ref": base_ref,
            "base_commit": base_commit,
        },
        "pull_requests": pr_section,
        "dependency_and_stacking_graph": {
            "edges": {str(k): sorted(v) for k, v in sorted(edges.items())},
            "layers": layers,
            "cycles": cycles,
        },
        "changed_file_ownership": ownership,
        "ci_and_infrastructure_status": {
            "test_runner": test_runner_section,
            "pr_ci_status_counts": {
                status: sum(1 for e in pr_section["pull_requests"] if e["ci_status"] == status)
                for status in ("passed", "failed", "pending", "not_started", "skipped", "unknown")
            },
        },
        "performance_evidence": performance_section,
        "memory_evidence": memory_section,
        "interoperability_status": interoperability_section,
        "dataset_provenance": dataset_section,
        "topology_validation_status": topology_section,
        "falsification_status": falsification_section,
        "synthetic_versus_empirical_distinction": synthetic_vs_empirical,
        "scientific_limitations": limitations,
        "unresolved_conflicts": conflicts,
        "recommended_merge_order": {
            "order": order,
            "excluded": {str(k): v for k, v in sorted(excluded.items())},
        },
        "final_release_recommendation": final_recommendation,
        "capability_snapshot": capability_section,
        "merge_gate_decisions": merge_gate_section,
        "pr_retirement_decisions": pr_retirement_section,
        "provenance": {
            "manifest_path": str(manifest_path),
            "source_checksums": {
                key: {"path": loaded[key].path, "sha256": loaded[key].sha256} for key in manifest_mod.INPUT_SECTIONS
            },
        },
    }
    return report
