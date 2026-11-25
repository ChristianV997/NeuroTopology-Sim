"""Orchestrates the read-only inspection: loads whatever sources were
explicitly given (never discovers them), runs every query, and returns
one JSON-serializable inspection report plus an exit code.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.research_cycle_cli import queries
from tools.research_cycle_cli.artifact_reader import read_artifact_reports
from tools.research_cycle_cli.claim_gate_reader import read_claim_gate_report
from tools.research_cycle_cli.guardrails import Diagnostic
from tools.research_cycle_cli.ledger_reader import read_ledger
from tools.research_cycle_cli.versions import COMPILER_VERSION, REPORT_SCHEMA_VERSION

EXIT_CLEAN = 0
EXIT_INCOMPLETE = 1
EXIT_INVALID = 2
EXIT_BLOCKED = 3

_INVALID_DIAGNOSTIC_KINDS = {"invalid_json", "invalid_database"}


def compile_inspection(
    *,
    ledger_db: Path | None,
    claim_gate_report: Path | None,
    claim_gate_jsonl: bool = False,
    artifact_reports: list[Path] | None = None,
    artifacts_dir: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    ledger = read_ledger(ledger_db)
    claim_gate = read_claim_gate_report(claim_gate_report, jsonl=claim_gate_jsonl)
    artifacts = read_artifact_reports(report_paths=artifact_reports, reports_dir=artifacts_dir)

    # A whole-file parse/open failure (as opposed to a per-record one) is
    # reported via each reader's own `.error` string, not its diagnostics
    # list -- promote the invalid ones here so "invalid" is detected
    # uniformly regardless of whether the failure was file-level or
    # record-level.
    _INVALID_ERROR_PREFIXES = ("invalid_json", "sqlite_open_error", "sqlite_query_error")
    source_level_diagnostics: list[Diagnostic] = []
    if ledger.error is not None and ledger.error.startswith(_INVALID_ERROR_PREFIXES):
        source_level_diagnostics.append(Diagnostic("invalid_database" if "sqlite" in ledger.error else "invalid_json", ledger.path or "ledger_db", ledger.error, None))
    if claim_gate.error is not None and claim_gate.error.startswith(_INVALID_ERROR_PREFIXES):
        source_level_diagnostics.append(Diagnostic("invalid_json", claim_gate.path or "claim_gate_report", claim_gate.error, None))

    cycle_groups = queries.classify_cycles(ledger.cycles)
    missing_provenance = queries.claims_missing_provenance(ledger.records, claim_gate.results)
    hyps_without_experiment = queries.hypotheses_without_experiment(ledger.records)
    runs_missing = queries.runs_missing_artifacts(ledger.records, artifacts.reports)
    missing_validation = queries.artifacts_without_validation(ledger.records, artifacts.reports)
    evidence_breakdown = queries.evidence_class_breakdown(ledger.records, claim_gate.results, artifacts.reports)
    dup_superseded = queries.duplicates_and_superseded(ledger.records, artifacts.reports)
    stale = queries.stale_outputs(artifacts.reports)
    blockers = queries.compute_blockers(
        cycle_groups=cycle_groups,
        missing_provenance=missing_provenance,
        hyps_without_experiment=hyps_without_experiment,
        runs_missing=runs_missing,
        missing_validation=missing_validation,
        claim_gate_results=claim_gate.results,
        ledger_diagnostics=list(ledger.diagnostics) + source_level_diagnostics,
        claim_gate_diagnostics=claim_gate.diagnostics,
        artifact_diagnostics=artifacts.diagnostics,
    )

    all_diagnostics = list(ledger.diagnostics) + list(claim_gate.diagnostics) + list(artifacts.diagnostics) + source_level_diagnostics

    any_invalid = any(d.kind in _INVALID_DIAGNOSTIC_KINDS for d in all_diagnostics)
    any_missing_source = not ledger.ok or not claim_gate.ok or not artifacts.ok
    any_incomplete_signal = bool(missing_provenance or hyps_without_experiment or runs_missing["runs_without_artifacts"] or runs_missing["orphan_artifact_reports"] or missing_validation or stale)

    if any_invalid:
        exit_code = EXIT_INVALID
    elif blockers:
        exit_code = EXIT_BLOCKED
    elif any_missing_source or any_incomplete_signal:
        exit_code = EXIT_INCOMPLETE
    else:
        exit_code = EXIT_CLEAN

    report: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "generated_at": generated_at,
        "exit_code": exit_code,
        "sources": {
            "ledger_db": {"available": ledger.ok, "path": ledger.path, "error": ledger.error},
            "claim_gate_report": {"available": claim_gate.ok, "path": claim_gate.path, "error": claim_gate.error},
            "artifact_reports": {"available": artifacts.ok, "read": artifacts.sources_read, "failed": artifacts.sources_failed},
        },
        "diagnostics": [d.to_dict() for d in all_diagnostics],
        "cycles": {"groups": cycle_groups, "records": ledger.cycles},
        "claims": {
            "missing_provenance": missing_provenance,
            "ledger_claims": [r for r in ledger.records if r["record_type"] == "claim"],
            "claim_gate_results": claim_gate.results,
        },
        "hypotheses": {
            "without_experiment": hyps_without_experiment,
            "ledger_hypotheses": [r for r in ledger.records if r["record_type"] == "hypothesis"],
        },
        "artifacts": {
            "runs_without_artifacts": runs_missing["runs_without_artifacts"],
            "orphan_artifact_reports": runs_missing["orphan_artifact_reports"],
            "missing_validation": missing_validation,
            "reports": artifacts.reports,
        },
        "graph": {"links": ledger.links, "records_by_id": {r["record_id"]: {"record_type": r["record_type"], "cycle_id": r["cycle_id"]} for r in ledger.records}},
        "evidence_class_breakdown": evidence_breakdown,
        "duplicates_and_superseded": dup_superseded,
        "stale_outputs": stale,
        "blockers": blockers,
    }
    canonical = json.dumps(report, sort_keys=True, allow_nan=False)
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report
