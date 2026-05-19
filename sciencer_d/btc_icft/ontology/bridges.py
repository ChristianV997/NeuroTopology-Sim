"""
Bridge registry loader and validator (O2).

The bridge registry encodes allowed claims between ontology layers and the
artifacts/controls/falsifiers required to promote each bridge.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sciencer_d.btc_icft.ontology.safe_language import find_forbidden_phrases
from sciencer_d.btc_icft.ontology.schema import (
    ONTOLOGY_LAYERS,
    BridgeClaim,
    OntologyLayer,
)


def load_bridge_registry(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"bridge registry not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def bridge_to_dict(bridge: BridgeClaim) -> dict:
    return bridge.to_dict()


def _bridge_from_dict(d: dict) -> BridgeClaim:
    return BridgeClaim(
        bridge_id=d["bridge_id"],
        source_layer=d["source_layer"],
        target_layer=d["target_layer"],
        allowed_claim=d.get("allowed_claim", ""),
        forbidden_claims=list(d.get("forbidden_claims", []) or []),
        required_artifacts=list(d.get("required_artifacts", []) or []),
        required_controls=list(d.get("required_controls", []) or []),
        falsifiers=list(d.get("falsifiers", []) or []),
        alternative_explanations=list(d.get("alternative_explanations", []) or []),
        promotion_thresholds=dict(d.get("promotion_thresholds", {}) or {}),
        always_quarantined=bool(d.get("always_quarantined", False)),
    )


def parse_bridges(registry: dict) -> list[BridgeClaim]:
    return [_bridge_from_dict(b) for b in registry.get("bridges", [])]


def validate_bridge_registry(registry: dict) -> list[str]:
    """Return list of validation errors. Empty = valid."""
    errors: list[str] = []
    bridges = registry.get("bridges", [])
    if not isinstance(bridges, list) or not bridges:
        errors.append("bridges list missing or empty")
        return errors

    seen_ids: set[str] = set()
    for idx, b in enumerate(bridges):
        bid = b.get("bridge_id", "")
        if not bid:
            errors.append(f"bridge[{idx}] missing bridge_id")
            continue
        if bid in seen_ids:
            errors.append(f"duplicate bridge_id: {bid}")
        seen_ids.add(bid)

        src = b.get("source_layer", "")
        tgt = b.get("target_layer", "")
        if src not in ONTOLOGY_LAYERS:
            errors.append(f"{bid}: invalid source_layer '{src}'")
        if tgt not in ONTOLOGY_LAYERS:
            errors.append(f"{bid}: invalid target_layer '{tgt}'")

        allowed = b.get("allowed_claim", "")
        if not allowed or not str(allowed).strip():
            errors.append(f"{bid}: allowed_claim is empty")
        else:
            hits = find_forbidden_phrases(allowed)
            if hits:
                errors.append(f"{bid}: allowed_claim contains forbidden phrase(s): {hits}")

        for field_name in ("required_artifacts", "required_controls",
                           "falsifiers", "alternative_explanations",
                           "forbidden_claims"):
            if field_name not in b:
                errors.append(f"{bid}: missing field '{field_name}'")
            elif not isinstance(b[field_name], list):
                errors.append(f"{bid}: field '{field_name}' must be a list")

        # If target is ontology candidate, must default to quarantine
        # unless independent evidence requirements are explicitly set.
        if tgt == OntologyLayer.O_ONTOLOGY_CANDIDATE:
            thresholds = b.get("promotion_thresholds", {}) or {}
            always_q = bool(b.get("always_quarantined", False))
            independent_required = bool(
                thresholds.get("requires_independent_dataset")
                and thresholds.get("requires_mechanism_evidence")
            )
            if not always_q and not independent_required:
                errors.append(
                    f"{bid}: ontology-target bridge must default to quarantine "
                    "unless independent_dataset + mechanism_evidence are required"
                )
    return errors


def summarize_bridge_status(
    bridge: BridgeClaim,
    available_artifacts: set[str],
    available_controls: set[str],
    run_mode: str,
) -> dict:
    """Compute a status summary for a single bridge given available evidence."""
    missing_artifacts = [a for a in bridge.required_artifacts if a not in available_artifacts]
    missing_controls = [c for c in bridge.required_controls if c not in available_controls]

    if bridge.always_quarantined:
        status = "quarantined"
        reason = "bridge is permanently quarantined by registry policy"
    elif run_mode in ("mock_e2e", "mock-e2e") and bridge.promotion_thresholds.get("requires_real_execution"):
        status = "blocked_pending_real_execution"
        reason = "real execution required for promotion; current run is mock_e2e"
    elif missing_artifacts or missing_controls:
        status = "blocked_pending_evidence"
        reason = "missing required artifacts/controls"
    elif bridge.promotion_thresholds.get("requires_human_review"):
        status = "blocked_pending_review"
        reason = "human review required for promotion"
    elif bridge.promotion_thresholds.get("requires_independent_mechanism_evidence"):
        status = "blocked_pending_independent_mechanism_evidence"
        reason = "independent mechanism evidence required"
    else:
        status = "promotable_to_allowed_claim"
        reason = "required artifacts and controls present"

    return {
        "bridge_id": bridge.bridge_id,
        "source_layer": bridge.source_layer,
        "target_layer": bridge.target_layer,
        "allowed_claim": bridge.allowed_claim,
        "status": status,
        "reason": reason,
        "missing_artifacts": missing_artifacts,
        "missing_controls": missing_controls,
        "always_quarantined": bridge.always_quarantined,
    }
