"""Load the shared root result adapter without colliding with app-local tools."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


_MODULE_NAME = "neurotopology_shared_real_results_adapter"


def _adapter_path() -> Path | None:
    """Locate the optional repository adapter without assuming a container layout."""
    configured = os.getenv("NEUROTOPOLOGY_REPOSITORY_ROOT")
    candidates = ([Path(configured)] if configured else []) + [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        path = candidate / "tools" / "command_center" / "real_results_adapter.py"
        if path.is_file():
            return path
    return None


def _adapter():
    module = sys.modules.get(_MODULE_NAME)
    if module is not None:
        return module
    adapter_path = _adapter_path()
    if adapter_path is None:
        return None
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Command Center adapter at {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _unavailable_results() -> dict[str, Any]:
    """Return an explicit no-artifact state; never fabricate empirical subjects."""
    return {
        "schema_version": "command-center-real-results/v1",
        "status": "not_available",
        "dataset": "ds005620",
        "evidence_state": "no_local_empirical_artifacts",
        "claim_scope": "research_hypothesis_not_clinical_or_physical_proof",
        "state_order": [],
        "state_summaries": [],
        "subject_summaries": [],
        "windows": [],
        "source_artifacts": [],
        "failure_registry": [],
        "metric_provenance": {},
        "data_quality": {"window_count": 0, "subject_count": 0, "warning_window_count": 0, "level_t_artifact_count": 0},
        "spatial_artifact": {"status": "unavailable", "reason": "No repository empirical artifact adapter is available in this deployment."},
    }


def build_real_results() -> dict[str, Any]:
    adapter = _adapter()
    return adapter.build_real_results() if adapter is not None else _unavailable_results()


def build_visualization_payload() -> dict[str, Any]:
    adapter = _adapter()
    if adapter is not None:
        return adapter.build_visualization_payload()
    results = _unavailable_results()
    return {"schema_version": "cortex-viewer/v1", "dataset": results["dataset"], "frames": [], "phase_space": [], "subject_summaries": [], "spatial_artifact": results["spatial_artifact"], "source_artifacts": []}


def build_command_center_registry() -> dict[str, Any]:
    adapter = _adapter()
    if adapter is not None:
        registry = adapter.build_command_center_registry()
        results = adapter.build_real_results()
        registry["data_mode"] = "artifact_backed" if results.get("status") == "available" else "unavailable"
        return registry
    return {"schema_version": "command-center-registry/v1", "data_mode": "unavailable", "dataset_registry": [], "artifact_registry": [], "metric_registry": [], "failure_registry": [], "run_history": [], "proposed_runs": [], "command_registry": [{"id": "refresh-empirical-status", "label": "Refresh empirical status", "endpoint": "/command-center/status", "kind": "read_only", "execution_allowed": False}], "guardrails": {"pipeline_execution": "blocked_from_ui"}}


def get_downloadable_artifact(artifact_id: str):
    adapter = _adapter()
    return adapter.get_downloadable_artifact(artifact_id) if adapter is not None else None


def build_vortex_field_payload() -> dict[str, Any]:
    adapter = _adapter()
    if adapter is not None:
        return adapter.build_vortex_field_payload()
    return {
        "status": "unavailable",
        "reason": "No repository empirical artifact adapter is available in this deployment.",
    }


def build_mapper_graph_payload() -> dict[str, Any]:
    adapter = _adapter()
    if adapter is not None:
        return adapter.build_mapper_graph_payload()
    return {
        "status": "unavailable",
        "reason": "No repository empirical artifact adapter is available in this deployment.",
    }


def list_ds000245_subjects() -> list[str]:
    adapter = _adapter()
    return adapter.list_ds000245_subjects() if adapter is not None else []


def get_ds000245_bold_path(subject_id: str):
    adapter = _adapter()
    return adapter.get_ds000245_bold_path(subject_id) if adapter is not None else None
