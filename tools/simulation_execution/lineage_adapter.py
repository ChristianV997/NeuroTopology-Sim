"""Adapter boundary to the existing simulation-artifact lineage interface."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def extract_lineage(run_dir: Path) -> dict[str, Any]:
    """Call the existing extractor without importing it into execution internals."""
    try:
        from tools.simulation_artifacts.extractor import extract_run
        report = extract_run(run_dir)
        return {"status": report.get("status"), "report_sha256": report.get("report_sha256"), "adapter": "simulation_artifacts"}
    except Exception as exc:  # lineage is an optional reporting adapter
        return {"status": "UNAVAILABLE", "error": str(exc), "adapter": "simulation_artifacts"}
