"""Validator for data-migration effectiveness reports and artifact packs."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List

from tools.benchmarking.data_migration_effectiveness.schema import (
    EVIDENCE_CLASS,
    FORBIDDEN_PHRASES,
    REQUIRED_OUTPUT_FILES,
    SCHEMA_VERSION,
    TARGET_NAMES,
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
    if report.get("schema") != SCHEMA_VERSION:
        violations.append("schema_mismatch")
    if report.get("evidence_class") != EVIDENCE_CLASS:
        violations.append("evidence_class_mismatch")
    if report.get("synthetic") is not True:
        violations.append("synthetic_flag_missing")
    if report.get("scientific_improvement_claimed") is not False:
        violations.append("scientific_improvement_claimed")
    if report.get("network_accessed") is not False:
        violations.append("network_accessed")
    if report.get("full_dataset_download") not in (False, None):
        violations.append("full_dataset_download")
    config = report.get("config") or {}
    if config.get("max_workers") not in (1, None):
        violations.append("unbounded_workers")
    results = report.get("results") or []
    names = {row.get("target") for row in results}
    if results and not names <= set(TARGET_NAMES):
        violations.append("unknown_target")
    for row in results:
        det = row.get("deterministic") or {}
        if "checksum_match" not in det:
            violations.append(f"missing_checksum_match:{row.get('target')}")
        tel = row.get("telemetry")
        if tel:
            for side in ("baseline", "candidate"):
                view = tel.get(side) or {}
                for key in ("rss_after_bytes", "tracemalloc_peak_bytes"):
                    if key in view and view[key] == 0:
                        violations.append(f"zero_metric:{row.get('target')}:{side}:{key}")
        if row.get("evidence_class") != EVIDENCE_CLASS:
            violations.append(f"row_evidence_class:{row.get('target')}")
        if row.get("scientific_improvement_claimed") is True:
            violations.append(f"row_scientific_claim:{row.get('target')}")
    blob = json.dumps(report, allow_nan=False, default=str)
    _scan_forbidden(blob, violations, "report")
    _finite(report, "$", violations)
    lowered = blob.lower()
    if "openneuro.org" in lowered or "amazonaws.com" in lowered or "dandiarchive" in lowered:
        violations.append("remote_data_reference")
    return {
        "ok": not violations,
        "violations": violations,
        "evidence_class": EVIDENCE_CLASS,
        "schema": SCHEMA_VERSION,
    }


def validate_root(root: str | Path) -> Dict[str, Any]:
    base = Path(root)
    violations: List[str] = []
    for rel in REQUIRED_OUTPUT_FILES:
        if not (base / rel).exists():
            violations.append(f"missing:{rel}")
    report_path = base / "data_migration_effectiveness.json"
    report: Dict[str, Any] = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        inner = validate_report(report)
        violations.extend(inner["violations"])
        text = report_path.read_text(encoding="utf-8")
        _scan_forbidden(text, violations, "json")
    md = base / "data_migration_effectiveness.md"
    if md.exists():
        _scan_forbidden(md.read_text(encoding="utf-8"), violations, "markdown")
    return {
        "ok": not violations,
        "violations": violations,
        "root": str(base),
        "evidence_class": EVIDENCE_CLASS,
        "schema": SCHEMA_VERSION,
        "targets": sorted({row.get("target") for row in (report.get("results") or []) if row.get("target")}),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    result = validate_root(args.root)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
