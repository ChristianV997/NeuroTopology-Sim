"""Per-input-contract normalization into report sections.

Each ``build_*`` function takes the raw ``LoadResult`` for one input
contract (see docs/reporting/mobile_report_contract.md) and returns a
JSON-serializable dict shaped like::

    {
        "available": bool,
        "source_path": str | None,
        "source_format": str | None,
        "checksum": str | None,   # local sha256 -- see guardrails.checksum_source_label
        "error": str | None,
        ... contract-specific normalized fields ...
    }

An unavailable or malformed input never raises: it comes back with
``available: False`` and an ``error`` explaining why, so the overall
report can still be compiled as "partial".
"""
from __future__ import annotations

from typing import Any

from tools.mobile_report.evidence_loader import LoadResult
from tools.mobile_report.graph import PRNode
from tools.mobile_report.guardrails import (
    metric_label,
    normalize_author_test_results,
    normalize_block_reason,
    normalize_checksum_source,
    normalize_ci_status,
    normalize_claim_class,
    normalize_data_mode,
    normalize_implementation_report,
    normalize_memory_kind,
    normalize_merge_status,
    normalize_metric_family,
    normalize_scientific_pass,
    normalize_status_category,
    normalize_value_class,
    normalize_verification_existence,
    normalize_verification_merge_status,
    safe_bool,
    safe_int,
    safe_number,
)


def _base(result: LoadResult) -> dict[str, Any]:
    return {
        "available": result.ok,
        "source_path": result.path,
        "source_format": result.format,
        "checksum": result.sha256,
        "error": result.error,
    }


def _items(result: LoadResult, list_key: str) -> list[Any]:
    if not result.ok or not isinstance(result.data, dict):
        return []
    raw = result.data.get(list_key)
    return raw if isinstance(raw, list) else []


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _str_list(value: Any) -> list[str]:
    return sorted({v for v in value if isinstance(v, str)}) if isinstance(value, list) else []


_INTEGRATION_STATUS = {"merged_to_main", "integrated_only", "not_integrated", "unknown"}


def build_reconciliation(result: LoadResult) -> tuple[dict[str, Any], list[PRNode]]:
    section = _base(result)
    nodes: list[PRNode] = []
    entries: list[dict[str, Any]] = []
    for item in _items(result, "pull_requests"):
        if not isinstance(item, dict) or "pr_number" not in item:
            continue
        number = safe_int(item.get("pr_number"))
        if number is None:
            continue
        depends_on_raw = item.get("depends_on")
        depends_on = tuple(sorted({d for d in (safe_int(x) for x in depends_on_raw) if d is not None})) if isinstance(depends_on_raw, list) else ()
        integration_status = item.get("integration_status")
        integration_status = integration_status if integration_status in _INTEGRATION_STATUS else "unknown"

        node = PRNode(
            number=number,
            branch=_str_or_none(item.get("branch")),
            base_branch=_str_or_none(item.get("base_branch")),
            parent_pr=safe_int(item.get("parent_pr")),
            merge_status=normalize_merge_status(item.get("merge_status")),
            status_category=normalize_status_category(item.get("status_category")),
            mergeable=safe_bool(item.get("mergeable")),
            ci_status=normalize_ci_status(item.get("ci_status")),
            superseded_by_pr=safe_int(item.get("superseded_by_pr")),
            depends_on=depends_on,
        )
        nodes.append(node)
        entries.append(
            {
                "pr_number": node.number,
                "branch": node.branch,
                "base_branch": node.base_branch,
                "parent_pr": node.parent_pr,
                "merge_status": node.merge_status,
                "status_category": node.status_category,
                "is_draft": safe_bool(item.get("is_draft")),
                "integration_status": integration_status,
                "mergeable": node.mergeable,
                "ci_status": node.ci_status,
                "superseded_by_pr": node.superseded_by_pr,
                "depends_on": list(node.depends_on),
                "changed_files": _str_list(item.get("changed_files")),
            }
        )

    entries.sort(key=lambda e: e["pr_number"])
    nodes.sort(key=lambda n: n.number)
    section["pull_requests"] = entries
    section["by_merge_status"] = {
        status: sorted(e["pr_number"] for e in entries if e["merge_status"] == status)
        for status in ("open", "merged", "draft", "branch_only", "blocked", "unverified", "closed", "unknown")
    }
    return section, nodes


def build_agent_contributions(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    contributions = []
    for item in _items(result, "contributions"):
        if not isinstance(item, dict) or "id" not in item:
            continue
        verification = item.get("verification_status") if isinstance(item.get("verification_status"), dict) else {}
        research = item.get("research_classification") if isinstance(item.get("research_classification"), dict) else {}
        contributions.append(
            {
                "id": str(item["id"]),
                "title": _str_or_none(item.get("title")),
                "agent": _str_or_none(item.get("agent")),
                "branch": _str_or_none(item.get("branch")),
                "pr_number": safe_int(item.get("pr_number")),
                "section": _str_or_none(item.get("section")),
                "merge_status": normalize_merge_status(item.get("merge_status")),
                "is_draft": safe_bool(item.get("is_draft")),
                "changed_file_count": safe_int(item.get("changed_file_count")),
                "additions": safe_int(item.get("additions")),
                "deletions": safe_int(item.get("deletions")),
                "verification_status": {
                    "existence": normalize_verification_existence(verification.get("existence")),
                    "merge_status": normalize_verification_merge_status(verification.get("merge_status")),
                    "scientific_pass": normalize_scientific_pass(verification.get("scientific_pass")),
                    "author_test_results": normalize_author_test_results(verification.get("author_test_results")),
                    "implementation_report": normalize_implementation_report(verification.get("implementation_report")),
                },
                "research_classification": {
                    "value_class": normalize_value_class(research.get("value_class")),
                    "claim_class": normalize_claim_class(research.get("claim_class")),
                    "data_mode": normalize_data_mode(research.get("data_mode")),
                    "empirical_pass_allowed": safe_bool(research.get("empirical_pass_allowed")) or False,
                },
                "limitations": _str_list(item.get("limitations")),
            }
        )
    contributions.sort(key=lambda c: c["id"])
    section["contributions"] = contributions
    return section


def build_dashboard_isolation(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    data = result.data if result.ok and isinstance(result.data, dict) else {}
    ok = data.get("ok")
    section["ok"] = ok if isinstance(ok, bool) else None
    section["scanned_files"] = safe_int(data.get("scanned_files"))
    section["violations"] = _str_list(data.get("violations"))
    section["evidence"] = _str_or_none(data.get("evidence"))
    return section


def build_test_runner(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    jobs = []
    for item in _items(result, "jobs"):
        if not isinstance(item, dict) or "name" not in item:
            continue
        jobs.append(
            {
                "name": str(item["name"]),
                "status": normalize_ci_status(item.get("status")),
                "block_reason": normalize_block_reason(item.get("block_reason")),
                "passed": safe_int(item.get("passed")),
                "failed": safe_int(item.get("failed")),
                "skipped": safe_int(item.get("skipped")),
                "duration_s": safe_number(item.get("duration_s")),
            }
        )
    jobs.sort(key=lambda j: j["name"])
    section["jobs"] = jobs
    section["counts_by_status"] = {
        status: sum(1 for j in jobs if j["status"] == status)
        for status in ("passed", "failed", "pending", "not_started", "timed_out", "skipped", "unknown")
    }
    section["totals"] = {
        "passed": sum(j["passed"] or 0 for j in jobs),
        "failed": sum(j["failed"] or 0 for j in jobs),
        "skipped": sum(j["skipped"] or 0 for j in jobs),
    }
    return section


def build_benchmark_summary(result: LoadResult, *, memory_fields: bool = False) -> dict[str, Any]:
    """Shared shape for "performance_benchmark" and "memory_evidence"."""
    section = _base(result)
    benchmarks = []
    for item in _items(result, "benchmarks"):
        if not isinstance(item, dict) or "name" not in item:
            continue
        entry = {
            "name": str(item["name"]),
            "metric": _str_or_none(item.get("metric")),
            "value": safe_number(item.get("value")),
            "unit": _str_or_none(item.get("unit")),
            "baseline_value": safe_number(item.get("baseline_value")),
            "regression_pct": safe_number(item.get("regression_pct")),
            "status": item.get("status") if item.get("status") in ("pass", "fail") else "unknown",
        }
        if memory_fields:
            entry["kind"] = normalize_memory_kind(item.get("kind"))
            entry["independently_verified"] = safe_bool(item.get("independently_verified"))
        benchmarks.append(entry)
    benchmarks.sort(key=lambda b: b["name"])
    section["benchmarks"] = benchmarks
    return section


def build_dataset_provenance(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    datasets = []
    for item in _items(result, "datasets"):
        if not isinstance(item, dict) or "dataset_id" not in item:
            continue
        datasets.append(
            {
                "dataset_id": str(item["dataset_id"]),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "source": _str_or_none(item.get("source")),
                "license": _str_or_none(item.get("license")),
                "checksum": _str_or_none(item.get("checksum")),
                "checksum_source": normalize_checksum_source(item.get("checksum_source")),
                "n_subjects": safe_int(item.get("n_subjects")),
                "notes": _str_or_none(item.get("notes")),
            }
        )
    datasets.sort(key=lambda d: d["dataset_id"])
    section["datasets"] = datasets
    return section


def build_topology_validation(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    checks = []
    for item in _items(result, "checks"):
        if not isinstance(item, dict) or "name" not in item:
            continue
        verdict = item.get("verdict") if item.get("verdict") in ("PASS", "FAIL") else "unknown"
        checks.append(
            {
                "name": str(item["name"]),
                "metric_family": normalize_metric_family(item.get("metric_family")),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "metric_value": safe_number(item.get("metric_value")),
                "unit": _str_or_none(item.get("unit")),
                "verdict": verdict,
                "notes": _str_or_none(item.get("notes")),
            }
        )
    checks.sort(key=lambda c: c["name"])
    section["checks"] = checks
    return section


def build_falsification(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    entries = []
    for item in _items(result, "results"):
        if not isinstance(item, dict) or "hypothesis_id" not in item:
            continue
        metric = metric_label(item.get("metric_type"))
        verdict = item.get("verdict") if item.get("verdict") in ("PASS", "FAIL", "INCONCLUSIVE") else "unknown"
        entries.append(
            {
                "hypothesis_id": str(item["hypothesis_id"]),
                "claim_class": normalize_claim_class(item.get("claim_class")),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "verdict": verdict,
                "metric_value": safe_number(item.get("metric_value")),
                "unit": _str_or_none(item.get("unit")),
                **metric,
                "notes": _str_or_none(item.get("notes")),
            }
        )
    entries.sort(key=lambda e: e["hypothesis_id"])
    section["results"] = entries
    return section


def build_merge_gate(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    decisions = []
    for item in _items(result, "decisions"):
        if not isinstance(item, dict) or "pr_number" not in item:
            continue
        pr_number = safe_int(item.get("pr_number"))
        if pr_number is None:
            continue
        decisions.append(
            {
                "pr_number": pr_number,
                "decision": item.get("decision") if item.get("decision") in ("allow", "block", "hold") else "unknown",
                "block_reason": normalize_block_reason(item.get("block_reason")),
                "reason": _str_or_none(item.get("reason")),
            }
        )
    decisions.sort(key=lambda d: d["pr_number"])
    section["decisions"] = decisions
    return section
