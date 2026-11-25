"""Validator for migration-wave artifact packs and reports."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

from tools.benchmarking.migration_wave.schema import (
    EVIDENCE_CLASS,
    FORBIDDEN_PHRASES,
    REQUIRED_OUTPUT_FILES,
    SCHEMA_VERSION,
    TARGET_NAMES,
    VARIANT_NAMES,
)


def _finite(obj: Any, path: str, violations: List[str]) -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            violations.append(f"non_finite:{path}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _finite(value, f"{path}.{key}", violations)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _finite(value, f"{path}[{index}]", violations)


def _scan_forbidden(text: str, violations: List[str], label: str) -> None:
    lowered = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            violations.append(f"forbidden:{label}:{phrase}")


def validate_report(report: Dict[str, Any]) -> Dict[str, Any]:
    violations: List[str] = []
    if report.get("schema") != SCHEMA_VERSION and report.get("schema_version") != SCHEMA_VERSION:
        violations.append("schema_mismatch")
    if report.get("evidence_class") != EVIDENCE_CLASS:
        violations.append("evidence_class_mismatch")
    if report.get("synthetic") is not True:
        violations.append("synthetic_flag_missing")
    config = report.get("config") or {}
    if config.get("max_workers") not in (1, None):
        violations.append("unbounded_workers")
    for row in report.get("results") or []:
        if row.get("variant") not in VARIANT_NAMES:
            violations.append(f"unknown_variant:{row.get('variant')}")
        if row.get("target") not in TARGET_NAMES:
            violations.append(f"unknown_target:{row.get('target')}")
        tel = row.get("telemetry")
        if tel:
            for key in ("rss_after_bytes", "tracemalloc_peak_bytes"):
                if key in tel and tel[key] == 0:
                    violations.append(f"zero_metric:{row.get('variant')}:{row.get('target')}:{key}")
        if row.get("evidence_class") != EVIDENCE_CLASS:
            violations.append(f"row_evidence_class:{row.get('variant')}:{row.get('target')}")
    blob = json.dumps(report, allow_nan=False, default=str)
    _scan_forbidden(blob, violations, "report")
    _finite(report, "$", violations)
    lowered = blob.lower()
    if "amazonaws.com" in lowered or "dandiarchive" in lowered:
        violations.append("remote_data_reference")
    if report.get("network_used") is True or report.get("remote_data_accessed") is True:
        violations.append("network_used")
    return {
        "ok": not violations,
        "violations": violations,
        "evidence_class": EVIDENCE_CLASS,
        "schema": SCHEMA_VERSION,
    }


def validate_root(root: str | Path) -> Dict[str, Any]:
    root = Path(root)
    violations: List[str] = []
    for rel in REQUIRED_OUTPUT_FILES:
        if not (root / rel).exists():
            violations.append(f"missing:{rel}")
    report_path = root / "migration_wave_report.json"
    report_result: Dict[str, Any] = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_result = validate_report(report)
        violations.extend(report_result.get("violations") or [])
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json"}:
            _scan_forbidden(path.read_text(encoding="utf-8", errors="replace"), violations, str(path.name))
    return {
        "ok": not violations,
        "violations": violations,
        "root": str(root),
        "evidence_class": EVIDENCE_CLASS,
        "report": report_result,
    }
