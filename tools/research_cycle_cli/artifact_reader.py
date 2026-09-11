"""Read-only reader for the simulation-artifact extractor's report output.

Shape mirrored from ``tools/simulation_artifacts/extractor.py``'s
``extract_run()`` return value (Batch 1 / codex, read-only, not
imported). Each report is one already-exported JSON file (as written by
``scripts/export_simulation_evidence.py``) -- this module never scans a
run directory or a dataset itself, only the reports pointed at it
explicitly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.research_cycle_cli.guardrails import ARTIFACT_RUN_STATUSES, EVIDENCE_CLASSES, INVALID_JSON, Diagnostic


@dataclass(frozen=True)
class ArtifactReportSnapshot:
    ok: bool
    reports: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    sources_read: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)


def _normalize_report(raw: Any, *, source: str, diagnostics: list[Diagnostic]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        diagnostics.append(Diagnostic(INVALID_JSON, source, f"artifact report must be a JSON object, got {type(raw).__name__}", None))
        return None

    status = raw.get("status")
    if status is not None and status not in ARTIFACT_RUN_STATUSES:
        diagnostics.append(Diagnostic("unknown_vocabulary_value", source, f"status {status!r} is not one of {sorted(ARTIFACT_RUN_STATUSES)}", None))

    manifest = raw.get("artifact_manifest") if isinstance(raw.get("artifact_manifest"), dict) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    duplicates = manifest.get("duplicate_content") if isinstance(manifest.get("duplicate_content"), list) else []
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    evidence_class = evidence.get("evidence_class")
    if evidence_class is not None and evidence_class not in EVIDENCE_CLASSES and evidence_class != "synthetic_demo_only":
        diagnostics.append(Diagnostic("unknown_vocabulary_value", source, f"evidence_class {evidence_class!r} is not a recognized evidence class", None))
    diagnostics_field = raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {}
    provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}

    return {
        "source_path": source,
        "run_directory": raw.get("run_directory") if isinstance(raw.get("run_directory"), str) else manifest.get("run_directory"),
        "status": status if status in ARTIFACT_RUN_STATUSES else "unknown",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "duplicate_content": duplicates,
        "evidence_class": evidence_class,
        "synthetic": bool(evidence.get("synthetic")) if isinstance(evidence.get("synthetic"), bool) else None,
        "run_id": provenance.get("run_id") if isinstance(provenance.get("run_id"), str) else None,
        "missing": [v for v in diagnostics_field.get("missing", []) if isinstance(v, str)] if isinstance(diagnostics_field.get("missing"), list) else [],
        "stale": [v for v in diagnostics_field.get("stale", []) if isinstance(v, str)] if isinstance(diagnostics_field.get("stale"), list) else [],
        "partial": [v for v in diagnostics_field.get("partial", []) if isinstance(v, str)] if isinstance(diagnostics_field.get("partial"), list) else [],
        "failed": [v for v in diagnostics_field.get("failed", []) if isinstance(v, str)] if isinstance(diagnostics_field.get("failed"), list) else [],
        "conflicting": [v for v in diagnostics_field.get("conflicting", []) if isinstance(v, str)] if isinstance(diagnostics_field.get("conflicting"), list) else [],
        "report_sha256": raw.get("report_sha256") if isinstance(raw.get("report_sha256"), str) else None,
    }


def _read_one(path: Path, diagnostics: list[Diagnostic]) -> dict[str, Any] | None:
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        diagnostics.append(Diagnostic(INVALID_JSON, source, f"could not read file: {exc}", None))
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        diagnostics.append(Diagnostic(INVALID_JSON, source, f"not valid JSON: {exc}", None))
        return None
    return _normalize_report(parsed, source=source, diagnostics=diagnostics)


def read_artifact_reports(*, report_paths: list[Path] | None = None, reports_dir: Path | None = None) -> ArtifactReportSnapshot:
    """Reads every explicitly-named report file, plus every ``*.json``
    file directly inside ``reports_dir`` (non-recursive -- an explicit,
    single-level listing of already-exported reports, not a dataset
    scan)."""
    candidate_paths: list[Path] = list(report_paths or [])
    if reports_dir is not None:
        if not reports_dir.is_dir():
            return ArtifactReportSnapshot(ok=False, diagnostics=[Diagnostic("missing_source", str(reports_dir), "artifacts directory not found", None)])
        candidate_paths.extend(sorted(reports_dir.glob("*.json")))

    if not candidate_paths:
        return ArtifactReportSnapshot(ok=False, diagnostics=[Diagnostic("missing_source", "artifact_reports", "not_provided", None)])

    diagnostics: list[Diagnostic] = []
    reports: list[dict[str, Any]] = []
    sources_read: list[str] = []
    sources_failed: list[str] = []
    for path in candidate_paths:
        if not path.is_file():
            diagnostics.append(Diagnostic("missing_source", str(path), "file_not_found", None))
            sources_failed.append(str(path))
            continue
        report = _read_one(path, diagnostics)
        if report is not None:
            reports.append(report)
            sources_read.append(str(path))
        else:
            sources_failed.append(str(path))

    reports.sort(key=lambda r: r["source_path"])
    return ArtifactReportSnapshot(ok=True, reports=reports, diagnostics=diagnostics, sources_read=sources_read, sources_failed=sources_failed)
