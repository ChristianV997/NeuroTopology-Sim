"""Read-only reader for the scientific claim gate's report output.

Shape mirrored from ``tools/research_claim_gate/gate.py``'s
``ClaimGateResult.to_dict()`` (Batch 1 / codex, read-only, not imported).
Accepts either a single JSON array/object or a JSONL file (one JSON
object per line), matching ``scripts/validate_research_claim.py``'s own
``--jsonl`` convention.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.research_cycle_cli.guardrails import (
    CLAIM_GATE_DECISIONS,
    CLAIM_GATE_SEVERITIES,
    EVIDENCE_CLASSES,
    INVALID_JSON,
    Diagnostic,
)


@dataclass(frozen=True)
class ClaimGateSnapshot:
    ok: bool
    path: str | None
    error: str | None
    results: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _normalize_result(raw: Any, *, source: str, diagnostics: list[Diagnostic]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        diagnostics.append(Diagnostic(INVALID_JSON, source, f"claim gate result must be a JSON object, got {type(raw).__name__}", None))
        return None
    claim_id = raw.get("claim_id") if isinstance(raw.get("claim_id"), str) else None
    decision = raw.get("decision")
    if decision is not None and decision not in CLAIM_GATE_DECISIONS:
        diagnostics.append(Diagnostic("unknown_vocabulary_value", source, f"decision {decision!r} is not one of {sorted(CLAIM_GATE_DECISIONS)}", claim_id))
    severity = raw.get("severity")
    if severity is not None and severity not in CLAIM_GATE_SEVERITIES:
        diagnostics.append(Diagnostic("unknown_vocabulary_value", source, f"severity {severity!r} is not one of {sorted(CLAIM_GATE_SEVERITIES)}", claim_id))
    evidence_class = raw.get("evidence_class")
    if evidence_class is not None and evidence_class not in EVIDENCE_CLASSES:
        diagnostics.append(Diagnostic("unknown_vocabulary_value", source, f"evidence_class {evidence_class!r} is not one of {sorted(EVIDENCE_CLASSES)}", claim_id))
    return {
        "claim_id": claim_id,
        "decision": decision if decision in CLAIM_GATE_DECISIONS else "unknown",
        "severity": severity if severity in CLAIM_GATE_SEVERITIES else "unknown",
        "claim_class": raw.get("claim_class") if isinstance(raw.get("claim_class"), str) else None,
        "evidence_class": evidence_class if evidence_class in EVIDENCE_CLASSES else None,
        "data_mode": raw.get("data_mode") if isinstance(raw.get("data_mode"), str) else None,
        "provenance_status": raw.get("provenance_status") if isinstance(raw.get("provenance_status"), str) else "unknown",
        "scientific_eligibility": raw.get("scientific_eligibility") if isinstance(raw.get("scientific_eligibility"), bool) else None,
        "scientific_pass": raw.get("scientific_pass") if isinstance(raw.get("scientific_pass"), bool) else None,
        "reason_codes": [r for r in raw.get("reason_codes", []) if isinstance(r, str)] if isinstance(raw.get("reason_codes"), list) else [],
    }


def read_claim_gate_report(path: Path | None, *, jsonl: bool = False) -> ClaimGateSnapshot:
    if path is None:
        return ClaimGateSnapshot(ok=False, path=None, error="not_provided")
    if not path.is_file():
        return ClaimGateSnapshot(ok=False, path=str(path), error="file_not_found")

    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ClaimGateSnapshot(ok=False, path=source, error=f"read_error: {exc}")

    diagnostics: list[Diagnostic] = []
    raw_results: list[Any] = []

    if jsonl or path.suffix.lower() == ".jsonl":
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                raw_results.append(json.loads(line))
            except json.JSONDecodeError as exc:
                diagnostics.append(Diagnostic(INVALID_JSON, source, f"line {line_number} is not valid JSON: {exc}", None))
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return ClaimGateSnapshot(ok=False, path=source, error=f"invalid_json: {exc}")
        raw_results = parsed if isinstance(parsed, list) else [parsed]

    results = []
    for raw in raw_results:
        normalized = _normalize_result(raw, source=source, diagnostics=diagnostics)
        if normalized is not None:
            results.append(normalized)

    return ClaimGateSnapshot(ok=True, path=source, error=None, results=results, diagnostics=diagnostics)
