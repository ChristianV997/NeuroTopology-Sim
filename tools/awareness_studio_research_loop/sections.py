"""Per-input-contract normalization into report sections.

Each ``build_*`` function takes the raw ``LoadResult`` for one input
contract (see docs/awareness_studio/research_cycle_orchestration.md) and
returns a JSON-serializable dict with ``available``/``source_path``/
``source_format``/``checksum``/``error`` plus contract-specific
normalized fields. An unavailable or malformed input never raises.
"""
from __future__ import annotations

from typing import Any

from tools.awareness_studio_research_loop.evidence_loader import LoadResult
from tools.awareness_studio_research_loop.guardrails import (
    normalize_claim_class,
    normalize_claim_status,
    normalize_data_mode,
    normalize_dependency_state,
    normalize_evidence_tier,
    normalize_evidence_update_type,
    normalize_execution_status,
    normalize_null_verdict,
    normalize_relationship,
    normalize_review_decision,
    normalize_source_status,
    normalize_verification_status,
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


def _flat(result: LoadResult) -> dict[str, Any]:
    return result.data if result.ok and isinstance(result.data, dict) else {}


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _str_list(value: Any) -> list[str]:
    return sorted({v for v in value if isinstance(v, str)}) if isinstance(value, list) else []


def _str_tuple_preserve_order(value: Any) -> list[str]:
    """Like a list of strings, but order-preserving (not sorted) -- used
    for claim_ids/etc. where the source's own ordering may be meaningful
    and duplicates should still be visible for debugging."""
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def build_literature_evidence(result: LoadResult) -> dict[str, Any]:
    """Owned by Claude A (tools/awareness_studio_research/**) -- consumed
    only via this flat export contract, never by importing that package."""
    section = _base(result)
    data = _flat(result)

    sources = []
    for item in data.get("sources", []) if isinstance(data.get("sources"), list) else []:
        if not isinstance(item, dict) or "source_id" not in item:
            continue
        sources.append(
            {
                "source_id": str(item["source_id"]),
                "title": _str_or_none(item.get("title")),
                "doi": _str_or_none(item.get("doi")),
                "source_checksum": _str_or_none(item.get("source_checksum")),
                "evidence_tier": normalize_evidence_tier(item.get("evidence_tier")),
                "verification_status": normalize_verification_status(item.get("verification_status")),
                "status": normalize_source_status(item.get("status")),
                "limitations": _str_list(item.get("limitations")),
            }
        )
    sources.sort(key=lambda s: s["source_id"])

    claims = []
    for item in data.get("claims", []) if isinstance(data.get("claims"), list) else []:
        if not isinstance(item, dict) or "claim_id" not in item:
            continue
        claims.append(
            {
                "claim_id": str(item["claim_id"]),
                "source_id": _str_or_none(item.get("source_id")),
                "claim_text": _str_or_none(item.get("claim_text")) or "",
                "claim_class": normalize_claim_class(item.get("claim_class")),
                "claim_status": normalize_claim_status(item.get("claim_status")),
                "linked_hypothesis": _str_or_none(item.get("linked_hypothesis")),
            }
        )
    claims.sort(key=lambda c: c["claim_id"])

    hypothesis_links = []
    for item in data.get("hypothesis_links", []) if isinstance(data.get("hypothesis_links"), list) else []:
        if not isinstance(item, dict) or "hypothesis_id" not in item:
            continue
        hypothesis_links.append(
            {
                "hypothesis_id": str(item["hypothesis_id"]),
                "claim_ids": _str_tuple_preserve_order(item.get("claim_ids")),
                "relationship": normalize_relationship(item.get("relationship")),
            }
        )
    hypothesis_links.sort(key=lambda h: h["hypothesis_id"])

    experiment_links = []
    for item in data.get("experiment_links", []) if isinstance(data.get("experiment_links"), list) else []:
        if not isinstance(item, dict) or "experiment_ref" not in item:
            continue
        experiment_links.append(
            {
                "experiment_ref": str(item["experiment_ref"]),
                "claim_ids": _str_tuple_preserve_order(item.get("claim_ids")),
                "relationship": normalize_relationship(item.get("relationship")),
            }
        )
    experiment_links.sort(key=lambda e: e["experiment_ref"])

    evidence_updates = []
    for item in data.get("evidence_updates", []) if isinstance(data.get("evidence_updates"), list) else []:
        if not isinstance(item, dict) or "update_id" not in item:
            continue
        evidence_updates.append(
            {
                "update_id": str(item["update_id"]),
                "entity_type": _str_or_none(item.get("entity_type")),
                "entity_id": _str_or_none(item.get("entity_id")),
                "update_type": normalize_evidence_update_type(item.get("update_type")),
                "reason": _str_or_none(item.get("reason")) or "",
            }
        )
    evidence_updates.sort(key=lambda u: u["update_id"])

    section["sources"] = sources
    section["claims"] = claims
    section["hypothesis_links"] = hypothesis_links
    section["experiment_links"] = experiment_links
    section["evidence_updates"] = evidence_updates
    return section


def build_hypothesis_registry(result: LoadResult) -> dict[str, Any]:
    """Owned by Antigravity C -- consumed only via this JSON contract."""
    section = _base(result)
    hypotheses = []
    for item in _items(result, "hypotheses"):
        if not isinstance(item, dict) or "hypothesis_id" not in item:
            continue
        hypotheses.append(
            {
                "hypothesis_id": str(item["hypothesis_id"]),
                "statement": _str_or_none(item.get("statement")) or "",
                "claim_ids": _str_tuple_preserve_order(item.get("claim_ids")),
                "null_prediction": _str_or_none(item.get("null_prediction")),
                "falsification_criterion": _str_or_none(item.get("falsification_criterion")),
            }
        )
    hypotheses.sort(key=lambda h: h["hypothesis_id"])
    section["hypotheses"] = hypotheses
    return section


def build_experiment_plans(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    plans = []
    for item in _items(result, "plans"):
        if not isinstance(item, dict) or "experiment_id" not in item:
            continue
        raw_metrics = item.get("metrics")
        metrics = []
        if isinstance(raw_metrics, list):
            for m in raw_metrics:
                if not isinstance(m, dict) or "name" not in m:
                    continue
                metrics.append({"name": str(m["name"]), "unit": _str_or_none(m.get("unit")), "feature_family": _str_or_none(m.get("feature_family"))})
        plans.append(
            {
                "experiment_id": str(item["experiment_id"]),
                "hypothesis_id": _str_or_none(item.get("hypothesis_id")),
                "falsification_criterion": _str_or_none(item.get("falsification_criterion")),
                "metrics": metrics,
                "dataset_id": _str_or_none(item.get("dataset_id")),
                "dataset_checksum": _str_or_none(item.get("dataset_checksum")),
                "held_out_split_locked": safe_bool(item.get("held_out_split_locked")),
                "is_predictive": safe_bool(item.get("is_predictive")) or False,
                "preregistered": safe_bool(item.get("preregistered")) or False,
                "synthetic": safe_bool(item.get("synthetic")) or False,
            }
        )
    plans.sort(key=lambda p: p["experiment_id"])
    section["plans"] = plans
    return section


def build_execution_results(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    executions = []
    for item in _items(result, "executions"):
        if not isinstance(item, dict) or "experiment_id" not in item:
            continue
        raw_metric_values = item.get("metric_values")
        metric_values = []
        if isinstance(raw_metric_values, list):
            for m in raw_metric_values:
                if not isinstance(m, dict) or "name" not in m:
                    continue
                metric_values.append({"name": str(m["name"]), "value": safe_number(m.get("value")), "unit": _str_or_none(m.get("unit"))})
        executions.append(
            {
                "experiment_id": str(item["experiment_id"]),
                "status": normalize_execution_status(item.get("status")),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "input_checksums": _str_list(item.get("input_checksums")),
                "output_checksums": _str_list(item.get("output_checksums")),
                "software_commit": _str_or_none(item.get("software_commit")),
                "runtime_seconds": safe_number(item.get("runtime_seconds")),
                "dependency_state": normalize_dependency_state(item.get("dependency_state")),
                "metric_values": metric_values,
            }
        )
    executions.sort(key=lambda e: e["experiment_id"])
    section["executions"] = executions
    return section


def build_null_surrogate_results(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    null_tests = []
    for item in _items(result, "null_tests"):
        if not isinstance(item, dict) or "experiment_id" not in item:
            continue
        null_tests.append(
            {
                "experiment_id": str(item["experiment_id"]),
                "method": _str_or_none(item.get("method")),
                "verdict": normalize_null_verdict(item.get("verdict")),
                "statistic": safe_number(item.get("statistic")),
                "notes": _str_or_none(item.get("notes")),
            }
        )
    null_tests.sort(key=lambda n: n["experiment_id"])
    section["null_tests"] = null_tests
    return section


def build_validation_reports(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    reports = []
    for item in _items(result, "reports"):
        if not isinstance(item, dict) or "report_id" not in item:
            continue
        reports.append(
            {
                "report_id": str(item["report_id"]),
                "experiment_id": _str_or_none(item.get("experiment_id")),
                "claim_status": normalize_claim_status(item.get("claim_status")),
                "data_mode": normalize_data_mode(item.get("data_mode")),
                "verdict": normalize_null_verdict(item.get("verdict")),
                "source": _str_or_none(item.get("source")),
            }
        )
    reports.sort(key=lambda r: r["report_id"])
    section["reports"] = reports
    return section


def build_reviewer_decisions(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    decisions = []
    for item in _items(result, "decisions"):
        if not isinstance(item, dict) or "subject_id" not in item:
            continue
        decisions.append(
            {
                "subject_type": item.get("subject_type") if item.get("subject_type") in ("claim", "hypothesis", "experiment", "paper_claim") else "unknown",
                "subject_id": str(item["subject_id"]),
                "decision": normalize_review_decision(item.get("decision")),
                "reviewer": _str_or_none(item.get("reviewer")),
                "notes": _str_or_none(item.get("notes")),
            }
        )
    decisions.sort(key=lambda d: (d["subject_type"], d["subject_id"]))
    section["decisions"] = decisions
    return section


def build_theory_state(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    data = _flat(result)
    section["theory_id"] = _str_or_none(data.get("theory_id"))
    section["version"] = safe_int(data.get("version"))
    section["statements"] = _str_list(data.get("statements"))
    section["contradictory_evidence_ids"] = _str_list(data.get("contradictory_evidence_ids"))
    section["alternative_explanations"] = _str_list(data.get("alternative_explanations"))
    return section


def build_cycle_config(result: LoadResult) -> dict[str, Any]:
    section = _base(result)
    data = _flat(result)
    section["research_question"] = _str_or_none(data.get("research_question"))
    section["repo"] = _str_or_none(data.get("repo"))
    return section
