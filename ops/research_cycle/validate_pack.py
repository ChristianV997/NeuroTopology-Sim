"""Validate the operator-pack catalog document. Does not invent science gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.research_cycle import CATALOG_SCHEMA
from ops.research_cycle.catalog import load_catalog
from ops.research_cycle.json_util import json_safe

REQUIRED_STEP_IDS: tuple[str, ...] = (
    "repository_state",
    "schema_validation",
    "research_plan_audit",
    "claim_gate",
    "artifact_manifest",
    "evidence_graph",
    "cache_policy",
    "simulation_campaign",
    "release_evidence",
    "targeted_tests",
    "finite_json_no_network",
)


def validate_catalog_document(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    catalog = None
    try:
        catalog = load_catalog(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        return json_safe({"ok": False, "errors": errors, "step_count": 0, "schema_version": None})

    if catalog.schema_version != CATALOG_SCHEMA:
        errors.append(f"schema_version {catalog.schema_version!r} != {CATALOG_SCHEMA!r}")
    ids = [step.id for step in catalog.steps]
    for required in REQUIRED_STEP_IDS:
        if required not in ids:
            errors.append(f"missing required step {required}")
    orders = [step.order for step in catalog.steps]
    if orders != sorted(orders):
        errors.append("required steps are not in increasing order")
    for step in catalog.steps:
        if step.timeout_s <= 0:
            errors.append(f"{step.id}: timeout_s must be > 0")
        if step.kind == "external" and not step.argv_template:
            errors.append(f"{step.id}: external step missing argv")
        if step.kind == "builtin" and not step.builtin:
            errors.append(f"{step.id}: builtin step missing builtin name")
        if step.network:
            errors.append(f"{step.id}: network=true is not allowed in this pack")
    return json_safe(
        {
            "ok": not errors,
            "errors": errors,
            "step_count": len(catalog.steps),
            "optional_count": len(catalog.optional_steps),
            "schema_version": catalog.schema_version,
            "required_step_ids": list(REQUIRED_STEP_IDS),
        }
    )
