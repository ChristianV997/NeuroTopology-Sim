"""Pure query functions answering the operator questions this CLI exists
for. Every function takes already-loaded, already-parsed data (never a
file path, never a database connection) and returns plain, JSON-safe
data structures -- no query here performs I/O, so they are trivially
testable and cannot themselves violate the read-only guarantee.
"""
from __future__ import annotations

from typing import Any

from tools.research_cycle_cli.guardrails import (
    CYCLE_GROUP_ACTIVE,
    CYCLE_GROUP_BLOCKED,
    CYCLE_GROUP_FAILED,
    CYCLE_GROUP_INCOMPLETE,
    EVIDENCE_CLASSES,
)

_PROVENANCE_REASON_CODES = {"MISSING_PROVENANCE", "INCOMPLETE_PROVENANCE", "INVALID_PROVENANCE"}


def classify_cycles(cycles: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Which cycles are frozen / active / blocked / failed / incomplete.

    "frozen" comes from the ledger's own ``finalized`` flag, independent
    of ``status`` -- a cycle can be finalized in any terminal status, so
    "frozen" and the status-based groups are not mutually exclusive; a
    cycle appears in every group its data actually supports.
    """
    groups: dict[str, list[str]] = {"frozen": [], "active": [], "blocked": [], "failed": [], "incomplete": [], "other": []}
    for cycle in cycles:
        cycle_id = cycle["cycle_id"]
        status = cycle.get("status")
        if cycle.get("finalized"):
            groups["frozen"].append(cycle_id)
        if status in CYCLE_GROUP_ACTIVE:
            groups["active"].append(cycle_id)
        elif status in CYCLE_GROUP_BLOCKED:
            groups["blocked"].append(cycle_id)
        elif status in CYCLE_GROUP_FAILED:
            groups["failed"].append(cycle_id)
        elif status in CYCLE_GROUP_INCOMPLETE:
            groups["incomplete"].append(cycle_id)
        elif status != "FINALIZED":
            groups["other"].append(cycle_id)
    return {k: sorted(v) for k, v in groups.items()}


def claims_missing_provenance(records: list[dict[str, Any]], claim_gate_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A claim lacks provenance when its own ``evidence_ids`` is empty, an
    ``evidence_ids`` entry does not resolve to a real evidence/source
    record in the same ledger snapshot, or a correlated claim-gate result
    reports one of the gate's own provenance reason codes."""
    evidence_ids_known = {r["payload"]["evidence_id"] for r in records if r["record_type"] == "evidence_record" and r.get("payload") and "evidence_id" in r["payload"]}
    gate_by_claim_id = {r["claim_id"]: r for r in claim_gate_results if r.get("claim_id")}

    flagged = []
    for record in records:
        if record["record_type"] != "claim" or not record.get("payload"):
            continue
        payload = record["payload"]
        claim_id = payload.get("claim_id", record["record_id"])
        evidence_ids = payload.get("evidence_ids") if isinstance(payload.get("evidence_ids"), list) else []
        reasons: list[str] = []
        if not evidence_ids:
            reasons.append("evidence_ids is empty")
        unresolved = [e for e in evidence_ids if e not in evidence_ids_known]
        if unresolved:
            reasons.append(f"evidence_ids references unresolved evidence record(s): {sorted(unresolved)}")
        gate_result = gate_by_claim_id.get(claim_id)
        if gate_result is not None:
            gate_reasons = set(gate_result.get("reason_codes", [])) & _PROVENANCE_REASON_CODES
            if gate_reasons:
                reasons.append(f"claim gate reported {sorted(gate_reasons)}")
        if reasons:
            flagged.append({"claim_id": claim_id, "cycle_id": record["cycle_id"], "reasons": reasons})
    flagged.sort(key=lambda f: f["claim_id"])
    return flagged


def hypotheses_without_experiment(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hypothesis_ids = {r["payload"]["hypothesis_id"]: r for r in records if r["record_type"] == "hypothesis" and r.get("payload") and "hypothesis_id" in r["payload"]}
    targeted: set[str] = set()
    for record in records:
        if record["record_type"] != "experiment_spec" or not record.get("payload"):
            continue
        for hyp_id in record["payload"].get("hypothesis_ids", []) if isinstance(record["payload"].get("hypothesis_ids"), list) else []:
            targeted.add(hyp_id)
    missing = sorted(hyp_id for hyp_id in hypothesis_ids if hyp_id not in targeted)
    return [{"hypothesis_id": hyp_id, "cycle_id": hypothesis_ids[hyp_id]["cycle_id"]} for hyp_id in missing]


def runs_missing_artifacts(records: list[dict[str, Any]], artifact_reports: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Two-way check: which ledger runs have no correlated artifact
    report (never invented -- a run with no correlatable report is
    reported as missing, not assumed fine), and which artifact reports
    correlate to no known ledger run (orphan artifacts)."""
    run_records = [r for r in records if r["record_type"] == "run_record" and r.get("payload")]
    manifest_run_ids = {r["payload"]["run_record_id"] for r in records if r["record_type"] == "artifact_manifest" and r.get("payload") and "run_record_id" in r["payload"]}
    report_run_ids = {report["run_id"] for report in artifact_reports if report.get("run_id")}

    runs_without = []
    for record in run_records:
        run_record_id = record["payload"].get("run_record_id", record["record_id"])
        if run_record_id in manifest_run_ids or run_record_id in report_run_ids:
            continue
        runs_without.append({"run_record_id": run_record_id, "cycle_id": record["cycle_id"]})

    ledger_run_ids = {record["payload"].get("run_record_id", record["record_id"]) for record in run_records}
    orphans = []
    for report in artifact_reports:
        run_id = report.get("run_id")
        if run_id is None or run_id in ledger_run_ids or run_id in manifest_run_ids:
            continue
        orphans.append({"source_path": report["source_path"], "run_id": run_id, "run_directory": report.get("run_directory")})

    runs_without.sort(key=lambda r: r["run_record_id"])
    orphans.sort(key=lambda r: r["source_path"])
    return {"runs_without_artifacts": runs_without, "orphan_artifact_reports": orphans}


def artifacts_without_validation(records: list[dict[str, Any]], artifact_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated_manifest_ids: set[str] = set()
    for record in records:
        if record["record_type"] != "validation_report" or not record.get("payload"):
            continue
        for manifest_id in record["payload"].get("artifact_manifest_ids", []) if isinstance(record["payload"].get("artifact_manifest_ids"), list) else []:
            validated_manifest_ids.add(manifest_id)

    flagged = []
    for record in records:
        if record["record_type"] != "artifact_manifest" or not record.get("payload"):
            continue
        manifest_id = record["payload"].get("artifact_manifest_id", record["record_id"])
        if manifest_id not in validated_manifest_ids:
            flagged.append({"artifact_manifest_id": manifest_id, "cycle_id": record["cycle_id"]})
    flagged.sort(key=lambda f: f["artifact_manifest_id"])
    return flagged


def evidence_class_breakdown(records: list[dict[str, Any]], claim_gate_results: list[dict[str, Any]], artifact_reports: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Counts every record's evidence_class, kept in strictly separate
    buckets per source -- never merged into one ambiguous total, so
    synthetic/proxy/descriptive/formal evidence always stays visibly
    labeled and traceable to where it came from."""
    ledger_counts = {label: 0 for label in sorted(EVIDENCE_CLASSES)}
    for record in records:
        payload = record.get("payload") or {}
        label = payload.get("evidence_class")
        if label in EVIDENCE_CLASSES:
            ledger_counts[label] += 1

    claim_gate_counts = {label: 0 for label in sorted(EVIDENCE_CLASSES)}
    for result in claim_gate_results:
        label = result.get("evidence_class")
        if label in EVIDENCE_CLASSES:
            claim_gate_counts[label] += 1

    artifact_counts: dict[str, int] = {}
    for report in artifact_reports:
        label = report.get("evidence_class") or "unlabeled"
        artifact_counts[label] = artifact_counts.get(label, 0) + 1

    return {"ledger_records": ledger_counts, "claim_gate_results": claim_gate_counts, "artifact_reports": artifact_counts}


def duplicates_and_superseded(records: list[dict[str, Any]], artifact_reports: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_hash: dict[str, list[str]] = {}
    for record in records:
        record_hash = record.get("record_hash")
        if record_hash:
            by_hash.setdefault(record_hash, []).append(record["record_id"])
    duplicate_records = [{"record_hash": h, "record_ids": sorted(ids)} for h, ids in sorted(by_hash.items()) if len(ids) > 1]

    by_type = {}
    for record in records:
        by_type.setdefault(record["record_id"], record)
    superseded = []
    for record in records:
        payload = record.get("payload") or {}
        for parent_id in payload.get("parent_ids", []) if isinstance(payload.get("parent_ids"), list) else []:
            parent = by_type.get(parent_id)
            if parent is not None and parent["record_type"] == record["record_type"]:
                superseded.append({"superseded_record_id": parent_id, "superseded_by_record_id": record["record_id"], "record_type": record["record_type"]})
    superseded.sort(key=lambda s: (s["record_type"], s["superseded_record_id"]))

    duplicate_files = []
    for report in artifact_reports:
        for dup in report.get("duplicate_content", []):
            if isinstance(dup, dict) and isinstance(dup.get("paths"), list) and len(dup["paths"]) > 1:
                duplicate_files.append({"source_path": report["source_path"], "sha256": dup.get("sha256"), "paths": sorted(dup["paths"])})

    return {"duplicate_ledger_records": duplicate_records, "superseded_ledger_records": superseded, "duplicate_artifact_files": duplicate_files}


def stale_outputs(artifact_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surfaces each artifact report's own ``stale`` diagnostic (already
    computed by the extractor from a manifest diff) -- this CLI does not
    invent its own staleness heuristic on top of data that doesn't carry
    a comparable timestamp."""
    flagged = []
    for report in artifact_reports:
        if report.get("stale"):
            flagged.append({"source_path": report["source_path"], "run_directory": report.get("run_directory"), "stale_paths": sorted(report["stale"])})
    flagged.sort(key=lambda f: f["source_path"])
    return flagged


def compute_blockers(
    *,
    cycle_groups: dict[str, list[str]],
    missing_provenance: list[dict[str, Any]],
    hyps_without_experiment: list[dict[str, Any]],
    runs_missing: dict[str, list[dict[str, Any]]],
    missing_validation: list[dict[str, Any]],
    claim_gate_results: list[dict[str, Any]],
    ledger_diagnostics: list[Any],
    claim_gate_diagnostics: list[Any],
    artifact_diagnostics: list[Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for cycle_id in cycle_groups["blocked"]:
        blockers.append({"kind": "cycle_blocked", "id": cycle_id, "detail": f"cycle {cycle_id!r} has ledger status BLOCKED"})
    for cycle_id in cycle_groups["failed"]:
        blockers.append({"kind": "cycle_failed", "id": cycle_id, "detail": f"cycle {cycle_id!r} has ledger status FAILED"})
    for item in missing_provenance:
        blockers.append({"kind": "missing_provenance", "id": item["claim_id"], "detail": "; ".join(item["reasons"])})
    for item in hyps_without_experiment:
        blockers.append({"kind": "hypothesis_without_experiment", "id": item["hypothesis_id"], "detail": f"hypothesis {item['hypothesis_id']!r} has no experiment_spec targeting it"})
    for item in runs_missing["runs_without_artifacts"]:
        blockers.append({"kind": "run_missing_artifacts", "id": item["run_record_id"], "detail": f"run {item['run_record_id']!r} has no correlated artifact manifest or report"})
    for item in missing_validation:
        blockers.append({"kind": "artifact_missing_validation", "id": item["artifact_manifest_id"], "detail": f"artifact manifest {item['artifact_manifest_id']!r} has no validation_report referencing it"})
    for result in claim_gate_results:
        if result["decision"] in ("CLAIM_REJECTED", "CLAIM_PROVENANCE_INVALID"):
            blockers.append({"kind": "claim_gate_rejection", "id": result.get("claim_id") or "(unknown)", "detail": f"claim gate decision={result['decision']!r}"})
    for diag in list(ledger_diagnostics) + list(claim_gate_diagnostics) + list(artifact_diagnostics):
        if diag.kind in ("invalid_json", "invalid_database"):
            blockers.append({"kind": diag.kind, "id": diag.record_id or diag.source, "detail": diag.detail})
    blockers.sort(key=lambda b: (b["kind"], str(b["id"])))
    return blockers
