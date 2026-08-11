"""Deterministic aggregation from EvidenceBundleV1 (+ its referenced
TransitionRecordV1/PhaseSpaceCoordinateV1 files) into report summary tables.

Every function here reads already-computed artifacts and counts/groups
them. None of them recompute a scientific metric, run an estimator, or
invent a value for a field that is absent -- an absent field is reported as
absent (e.g. `feature_set_id: None`, an empty axis list), never guessed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATUS_VALUES: tuple[str, ...] = ("estimated", "insufficient_data", "not_applicable", "failed_validation")
CONFIDENCE_VALUES: tuple[str, ...] = ("none", "low", "moderate", "high")
NULL_CONTROL_STATUSES: tuple[str, ...] = ("passed", "failed", "not_provided", "not_applicable", "mixed")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_transition_records(repo_root: Path, transition_record_paths: list[str]) -> list[dict[str, Any]]:
    """Read every TransitionRecord.json a bundle references. Fails closed
    (raises FileNotFoundError) if any path is missing -- callers wanting
    summary-only behavior on missing artifacts must catch this themselves."""
    return [_load_json(repo_root / p) for p in transition_record_paths]


def load_phase_space_coordinate_files(repo_root: Path, coordinate_paths: list[str]) -> list[dict[str, Any]]:
    """Read every PhaseSpaceCoordinates.json a bundle references. Each file
    holds a *list* of coordinates for one transition_id."""
    return [_load_json(repo_root / p) for p in coordinate_paths]


def summarize_transitions(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic summary of the TransitionRecordV1 artifacts referenced
    by a bundle. `records` are already-loaded dicts (see
    `load_transition_records`), never re-derived from raw data."""
    feature_set_ids = sorted({
        r.get("metadata", {}).get("feature_set_id")
        for r in records if r.get("metadata", {}).get("feature_set_id")
    })
    feature_families = sorted({
        name.split(".", 1)[0]
        for r in records
        for name in (r.get("feature_names") or [])
        if "." in name
    })
    record_levels = sorted({r.get("record_level") for r in records if r.get("record_level")})
    source_target_pairs = sorted({
        (r.get("source_state"), r.get("target_state"))
        for r in records if r.get("source_state") or r.get("target_state")
    })
    return {
        "count": len(records),
        "record_ids": sorted(r.get("transition_id") for r in records if r.get("transition_id")),
        "record_levels": record_levels,
        "feature_set_ids": feature_set_ids,
        "feature_families": feature_families,
        "source_target_pairs": [list(pair) for pair in source_target_pairs],
    }


def summarize_phase_space(coordinate_files: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic summary of the PhaseSpaceCoordinateV1 artifacts
    referenced by a bundle. Status/confidence counts always include every
    known value (zero-filled), per the mission's explicit required list --
    never silently omitting a status/confidence that happens to be zero."""
    status_counts = {s: 0 for s in STATUS_VALUES}
    confidence_counts = {c: 0 for c in CONFIDENCE_VALUES}
    axes_estimated: set[str] = set()
    axes_insufficient: set[str] = set()
    total = 0

    for coord_file in coordinate_files:
        for coord in coord_file.get("coordinates", []):
            total += 1
            status = coord.get("status", "insufficient_data")
            if status in status_counts:
                status_counts[status] += 1
            confidence = coord.get("confidence", "none")
            if confidence in confidence_counts:
                confidence_counts[confidence] += 1
            axis = coord.get("axis")
            if not axis:
                continue
            if status == "estimated":
                axes_estimated.add(axis)
            elif status == "insufficient_data":
                axes_insufficient.add(axis)

    return {
        "count": total,
        "status_counts": status_counts,
        "confidence_counts": confidence_counts,
        "axes_estimated": sorted(axes_estimated),
        "axes_insufficient_data": sorted(axes_insufficient - axes_estimated),
    }


def summarize_registry(bundle: Any) -> dict[str, Any]:
    decisions = list(getattr(bundle, "registry_decisions", None) or [])
    return {
        "registry_path": getattr(bundle, "registry_path", None),
        "requested_use": getattr(bundle, "requested_use", None),
        "decisions": decisions,
        "n_decisions": len(decisions),
        "all_allowed": all(d.get("allowed", False) for d in decisions) if decisions else None,
    }


def summarize_contamination(bundle: Any) -> dict[str, Any]:
    updates = list(getattr(bundle, "contamination_updates", None) or [])
    return {
        "updates": updates,
        "n_updates": len(updates),
        "any_applied": any(u.get("applied", False) for u in updates),
    }


def summarize_claim_scope(bundle: Any) -> dict[str, Any]:
    return {
        "claim_scope_ceiling": getattr(bundle, "claim_scope_ceiling", None),
        "generated_claim_scope": getattr(bundle, "generated_claim_scope", None),
    }


def summarize_evidence_level(bundle: Any) -> dict[str, Any]:
    return {
        "evidence_level_ceiling": getattr(bundle, "evidence_level_ceiling", None),
        "generated_evidence_levels": list(getattr(bundle, "generated_evidence_levels", None) or []),
    }
