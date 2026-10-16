"""Clearly marked synthetic fixture producers for Batch 3 offline integration.

These producers exist only when a local fixture is required or when an optional
upstream component is absent. Reports must label them as fixture producers /
substitutes and must never claim the real upstream producer executed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from tools.batch3_offline_integration.serialization import sha256_hex

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_REQUEST_NAME = "workflow_request.json"

PRODUCER_LABEL = "fixture_producer"
SUBSTITUTE_LABEL = "fixture_substitute"


def _read_fixture(name: str) -> Dict[str, Any]:
    path = FIXTURE_DIR / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixture root must be an object")
    return data


def load_workflow_request(
    *,
    fixture_name: str = DEFAULT_REQUEST_NAME,
    override: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Load the synthetic workflow request fixture (no network, no downloads)."""
    payload = _read_fixture(fixture_name)
    if override:
        merged = dict(payload)
        merged.update(dict(override))
        payload = merged
    return {
        "producer": PRODUCER_LABEL,
        "fixture_name": fixture_name,
        "fixture_sha256": sha256_hex(payload),
        "request": payload,
        "actual_upstream_producer_ran": False,
        "notes": "Local synthetic fixture only; no empirical data and no participant identifiers.",
    }


def synthetic_registry_payload() -> Dict[str, Any]:
    """Minimal synthetic hypothesis/plan payload for ResearchCycleRegistry."""
    return {
        "producer": PRODUCER_LABEL,
        "actual_upstream_producer_ran": False,
        "hypothesis": {
            "hypothesis_id": "HYP-B3-SYN-001",
            "precise_claim": "Offline integration stage order is deterministic for synthetic fixtures.",
            "construct_definitions": {"stage_order": "allowlisted stage sequence"},
            "operational_variables": {"workflow_ok": "bool"},
            "predicted_direction": "workflow_ok remains True when required stages succeed",
            "null_prediction": "workflow_ok is False if any required stage fails",
            "alternative_explanations": ["nondeterministic clock leakage", "unordered stage execution"],
            "falsification_criterion": "Rerun checksum mismatch or out-of-order stage records",
            "min_sample_size_or_power": {"n": 1, "note": "engineering_fixture"},
            "preregistration_reference": "batch3-offline-integration-fixture",
            "data_requirements": ["local_synthetic_fixture"],
            "analysis_plan": "Compare deterministic checksums across two harness reruns",
            "provenance": {"source": "batch3_offline_integration_fixture"},
            "epistemic_label": "computational_model",
            "status": "proposed",
        },
        "plan": {
            "plan_id": "PLAN-B3-SYN-001",
            "hypothesis_id": "HYP-B3-SYN-001",
            "domain": "null_and_surrogate",
            "design_type": "synthetic_fixture",
            "variables": {"workflow_ok": "bool"},
            "target_sample_size": 1,
            "power_analysis": {"method": "not_applicable_engineering"},
            "analysis_protocol": "deterministic_checksum_comparison",
            "data_source": "local_fixture",
            "is_synthetic": True,
            "provenance": {"source": "batch3_offline_integration_fixture"},
        },
    }


def substitute_artifact_lineage(*, missing_dependency: str, reason: str) -> Dict[str, Any]:
    """Return a marked substitute when optional extract_run cannot run."""
    return {
        "producer": SUBSTITUTE_LABEL,
        "actual_upstream_producer_ran": False,
        "missing_dependency": missing_dependency,
        "reason": reason,
        "status": "FIXTURE_SUBSTITUTED",
        "schema_version": "NeuroTopology.Batch3FixtureSubstitute.v1",
        "evidence_class": "ENGINEERING_ONLY",
        "notes": (
            "Optional upstream artifact lineage was not executed. "
            "This object is a clearly marked fixture substitute only."
        ),
    }


def synthetic_release_bundle(cycle_id: str = "rc-batch3-offline-001") -> Dict[str, Any]:
    """Minimal synthetic release bundle for evaluate_research_cycle_release."""
    return {
        "cycle_id": cycle_id,
        "dataset_id": "synthetic-batch3-offline-001",
        "data_mode": "synthetic",
        "synthetic": True,
        "proxy": False,
        "empirical": False,
        "evidence_class": "SYNTHETIC_ONLY",
        "provenance": {
            "run_id": "run-batch3-offline-001",
            "dataset_id": "synthetic-batch3-offline-001",
            "source": "batch3_offline_integration_fixture",
        },
        "metrics": {"workflow_stage_count": 7},
        "artifacts": [],
        "validation": {"status": "engineering_ok", "scientific_pass": False},
        "network_accessed": False,
        "full_dataset_download": False,
        "limitations": [
            "Synthetic engineering fixture for offline integration only.",
            "Not empirical neuroscience evidence.",
        ],
    }
