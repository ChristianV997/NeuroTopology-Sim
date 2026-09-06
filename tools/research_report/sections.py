"""Per-input-contract normalization into report sections.

Each ``build_*`` function takes the raw ``LoadResult`` for one input contract
(see docs/research/report_contract.md) and returns a JSON-serializable dict
shaped like::

    {
        "available": bool,
        "source_path": str | None,
        "checksum": str | None,
        "error": str | None,
        ... contract-specific normalized fields ...
    }

An unavailable or malformed input never raises: it comes back with
``available: False`` and an ``error`` explaining why, so the overall report
can still be compiled as "partial" (guardrail #12).
"""
from __future__ import annotations

from typing import Any

from tools.research_report.graph import PRNode
from tools.research_report.guardrails import (
    describe_metric,
    normalize_ci_status,
    normalize_data_mode,
    normalize_pr_state,
    normalize_test_job_status,
    safe_number,
)
from tools.research_report.json_safe import LoadResult


def _base(result: LoadResult) -> dict[str, Any]:
    return {
        "available": result.ok,
        "source_path": result.path,
        "checksum": result.sha256,
        "error": result.error,
    }


def _items(result: LoadResult, list_key: str) -> list[Any]:
    if not result.ok or not isinstance(result.data, dict):
        return []
    raw = result.data.get(list_key)
    return raw if isinstance(raw, list) else []


def build_pr_reconciliation(result: LoadResult) -> tuple[dict[str, Any], list[PRNode]]:
    section = _base(result)
    nodes: list[PRNode] = []
    entries: list[dict[str, Any]] = []
    for item in _items(result, "pull_requests"):
        if not isinstance(item, dict) or "pr_number" not in item:
            continue
        try:
            number = int(item["pr_number"])
        except (TypeError, ValueError):
            continue
        depends_on_raw = item.get("depends_on")
        depends_on = tuple(
            int(x) for x in depends_on_raw if isinstance(x, (int, float)) and not isinstance(x, bool)
        ) if isinstance(depends_on_raw, list) else ()
        superseded_by_pr = item.get("superseded_by_pr")
        superseded_by_pr = int(superseded_by_pr) if isinstance(superseded_by_pr, (int, float)) and not isinstance(superseded_by_pr, bool) else None
        mergeable = item.get("mergeable")
        mergeable = mergeable if isinstance(mergeable, bool) else None
        state = normalize_pr_state(item.get("state"))
        ci_status = normalize_ci_status(item.get("ci_status"))
        branch = item.get("branch") if isinstance(item.get("branch"), str) else None
        base_branch = item.get("base_branch") if isinstance(item.get("base_branch"), str) else None
        changed_files_raw = item.get("changed_files")
        changed_files = sorted({f for f in changed_files_raw if isinstance(f, str)}) if isinstance(changed_files_raw, list) else []

        node = PRNode(
            number=number,
            branch=branch,
            base_branch=base_branch,
            state=state,
            mergeable=mergeable,
            ci_status=ci_status,
            superseded_by_pr=superseded_by_pr,
            depends_on=depends_on,
        )
        nodes.append(node)
        entries.append(
            {
                "pr_number": number,
                "branch": branch,
                "base_branch": base_branch,
                "state": state,
                "mergeable": mergeable,
                "ci_status": ci_status,
                "superseded_by_pr": superseded_by_pr,
                "depends_on": list(depends_on),
                "changed_files": changed_files,
            }
        )

    entries.sort(key=lambda e: e["pr_number"])
    nodes.sort(key=lambda n: n.number)
    section["pull_requests"] = entries
    section["by_state"] = {
        state: sorted(e["pr_number"] for e in entries if e["state"] == state)
        for state in ("open", "merged", "draft", "closed", "unknown")
    }
    return section, nodes


def build_capability_snapshot(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    capabilities = []
    for item in _items(result, "capabilities"):
        if not isinstance(item, dict) or "name" not in item:
            continue
        capabilities.append(
            {
                "name": str(item["name"]),
                "status": item.get("status") if item.get("status") in ("available", "unavailable", "degraded") else "unknown",
                "backend": item.get("backend") if isinstance(item.get("backend"), str) else None,
                "notes": item.get("notes") if isinstance(item.get("notes"), str) else None,
            }
        )
    capabilities.sort(key=lambda c: c["name"])
    section["capabilities"] = capabilities
    return section


def build_interoperability(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    adapters = []
    for item in _items(result, "adapters"):
        if not isinstance(item, dict) or "name" not in item:
            continue
        adapters.append(
            {
                "name": str(item["name"]),
                "status": item.get("status") if item.get("status") in ("supported", "unsupported", "partial") else "unknown",
                "contract_version": item.get("contract_version") if isinstance(item.get("contract_version"), str) else None,
                "notes": item.get("notes") if isinstance(item.get("notes"), str) else None,
            }
        )
    adapters.sort(key=lambda a: a["name"])
    section["adapters"] = adapters
    return section


def build_dataset_provenance(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    datasets = []
    for item in _items(result, "datasets"):
        if not isinstance(item, dict) or "dataset_id" not in item:
            continue
        n_subjects = item.get("n_subjects")
        n_subjects = int(n_subjects) if isinstance(n_subjects, (int, float)) and not isinstance(n_subjects, bool) else None
        datasets.append(
            {
                "dataset_id": str(item["dataset_id"]),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "source": item.get("source") if isinstance(item.get("source"), str) else None,
                "license": item.get("license") if isinstance(item.get("license"), str) else None,
                "checksum": item.get("checksum") if isinstance(item.get("checksum"), str) else None,
                "n_subjects": n_subjects,
                "notes": item.get("notes") if isinstance(item.get("notes"), str) else None,
            }
        )
    datasets.sort(key=lambda d: d["dataset_id"])
    section["datasets"] = datasets
    return section


def build_falsification(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    entries = []
    for item in _items(result, "results"):
        if not isinstance(item, dict) or "hypothesis_id" not in item:
            continue
        metric = describe_metric(item.get("metric_type"), item.get("metric_value"), item.get("unit"))
        verdict = item.get("verdict") if item.get("verdict") in ("PASS", "FAIL", "INCONCLUSIVE") else "unknown"
        entries.append(
            {
                "hypothesis_id": str(item["hypothesis_id"]),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "verdict": verdict,
                **metric,
                "notes": item.get("notes") if isinstance(item.get("notes"), str) else None,
            }
        )
    entries.sort(key=lambda e: e["hypothesis_id"])
    section["results"] = entries
    return section


def build_benchmark_summary(result: LoadResult) -> dict[str, Any]:
    """Shared shape for both "performance_benchmark" and "memory_evidence"."""
    section = _base(result)
    benchmarks = []
    for item in _items(result, "benchmarks"):
        if not isinstance(item, dict) or "name" not in item:
            continue
        benchmarks.append(
            {
                "name": str(item["name"]),
                "metric": item.get("metric") if isinstance(item.get("metric"), str) else None,
                "value": safe_number(item.get("value")),
                "unit": item.get("unit") if isinstance(item.get("unit"), str) else None,
                "baseline_value": safe_number(item.get("baseline_value")),
                "regression_pct": safe_number(item.get("regression_pct")),
                "status": item.get("status") if item.get("status") in ("pass", "fail") else "unknown",
            }
        )
    benchmarks.sort(key=lambda b: b["name"])
    section["benchmarks"] = benchmarks
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
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "Qabs": safe_number(item.get("Qabs")),
                "I_mean": safe_number(item.get("I_mean")),
                "verdict": verdict,
                "notes": item.get("notes") if isinstance(item.get("notes"), str) else None,
            }
        )
    checks.sort(key=lambda c: c["name"])
    section["checks"] = checks
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
                "status": normalize_test_job_status(item.get("status")),
                "passed": _safe_int(item.get("passed")),
                "failed": _safe_int(item.get("failed")),
                "skipped": _safe_int(item.get("skipped")),
                "duration_s": safe_number(item.get("duration_s")),
            }
        )
    jobs.sort(key=lambda j: j["name"])
    section["jobs"] = jobs
    section["counts_by_status"] = {
        status: sum(1 for j in jobs if j["status"] == status)
        for status in ("passed", "failed", "error", "not_started", "skipped", "unknown")
    }
    return section


def _safe_int(value: Any) -> int | None:
    number = safe_number(value)
    return int(number) if number is not None else None


def build_merge_gate(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    decisions = []
    for item in _items(result, "decisions"):
        if not isinstance(item, dict) or "pr_number" not in item:
            continue
        try:
            pr_number = int(item["pr_number"])
        except (TypeError, ValueError):
            continue
        decisions.append(
            {
                "pr_number": pr_number,
                "decision": item.get("decision") if item.get("decision") in ("allow", "block", "hold") else "unknown",
                "reason": item.get("reason") if isinstance(item.get("reason"), str) else None,
            }
        )
    decisions.sort(key=lambda d: d["pr_number"])
    section["decisions"] = decisions
    return section


def build_pr_retirement(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    decisions = []
    for item in _items(result, "decisions"):
        if not isinstance(item, dict) or "pr_number" not in item:
            continue
        try:
            pr_number = int(item["pr_number"])
        except (TypeError, ValueError):
            continue
        superseded_by = item.get("superseded_by")
        superseded_by = int(superseded_by) if isinstance(superseded_by, (int, float)) and not isinstance(superseded_by, bool) else None
        decisions.append(
            {
                "pr_number": pr_number,
                "action": item.get("action") if item.get("action") in ("retire", "keep", "superseded") else "unknown",
                "superseded_by": superseded_by,
                "reason": item.get("reason") if isinstance(item.get("reason"), str) else None,
            }
        )
    decisions.sort(key=lambda d: d["pr_number"])
    section["decisions"] = decisions
    return section
