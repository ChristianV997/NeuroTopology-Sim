"""Adapter-only boundary to the existing artifact-lineage package."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def lineage_summary(output_root: Path) -> dict[str, Any]:
    try:
        from tools.simulation_artifacts.extractor import extract_run
        report = extract_run(output_root)
        return {"adapter": "simulation_artifacts", "status": report.get("status"), "report_sha256": report.get("report_sha256")}
    except Exception as exc:
        return {"adapter": "simulation_artifacts", "status": "UNAVAILABLE", "error": str(exc)}
