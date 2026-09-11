"""Project adapter output onto canonical empty_bundle fields."""
from __future__ import annotations

from typing import Any, Dict, Iterable

from tools.research_cycle_release.adapters import empty_bundle
from tools.research_cycle_release.schema import json_safe

_ALIASES: Dict[str, Iterable[str]] = {
    "source_manifest_present": ("source_manifest_present",),
    "source_manifest_path": ("source_manifest_path",),
    "checksums_present": ("checksums_present",),
    "checksum_entries": ("checksum_entries",),
    "configuration_locked": ("configuration_locked", "config_locked"),
    "code_commit": ("code_commit", "software_commit"),
    "seed": ("seed", "random_seed"),
    "input_provenance_complete": ("input_provenance_complete",),
    "input_provenance_missing": ("input_provenance_missing",),
    "outputs_finite": ("outputs_finite",),
    "non_finite_metric_paths": ("non_finite_metric_paths",),
    "metrics": ("metrics",),
    "work_units": ("work_units",),
    "all_work_units_terminal": ("all_work_units_terminal",),
    "partial_runs_explicitly_marked": ("partial_runs_explicitly_marked",),
    "artifact_lineage_complete": ("artifact_lineage_complete",),
    "artifact_lineage_missing": ("artifact_lineage_missing",),
    "validation_report_present": ("validation_report_present",),
    "validation_status": ("validation_status",),
    "null_metadata_applicable": ("null_metadata_applicable",),
    "null_metadata_present": ("null_metadata_present",),
    "multiplicity_metadata_applicable": ("multiplicity_metadata_applicable",),
    "multiplicity_metadata_present": ("multiplicity_metadata_present",),
    "forecasting_applicable": ("forecasting_applicable",),
    "forecasting_subject_split": ("forecasting_subject_split",),
    "forecasting_session_split": ("forecasting_session_split",),
    "forecasting_time_split": ("forecasting_time_split",),
    "resource_budgets_respected": ("resource_budgets_respected",),
    "resource_budget_details": ("resource_budget_details",),
    "full_dataset_download": ("full_dataset_download",),
    "network_policy_recorded": ("network_policy_recorded",),
    "network_policy_violated": ("network_policy_violated",),
    "evidence_classes": ("evidence_classes",),
    "evidence_classes_consistent": ("evidence_classes_consistent",),
    "synthetic_only": ("synthetic_only",),
    "proxy_only": ("proxy_only",),
    "empirical_present": ("empirical_present",),
    "report_metadata_text": ("report_metadata_text",),
    "infrastructure_blocked": ("infrastructure_blocked",),
    "comparable": ("comparable",),
    "comparability_notes": ("comparability_notes",),
    "hardware_metrics_advisory": ("hardware_metrics_advisory",),
    "cycle_id": ("cycle_id",),
}


def normalize_bundle(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = empty_bundle(cycle_id=raw.get("cycle_id") if isinstance(raw, dict) else None)
    if not isinstance(raw, dict):
        return json_safe(base)
    for key in base:
        if key in raw:
            base[key] = raw[key]
    for canonical, alts in _ALIASES.items():
        current = base.get(canonical)
        emptyish = current is None or current == [] or current == {} or current == ""
        if not emptyish:
            continue
        for alt in alts:
            if alt in raw and raw[alt] is not None:
                base[canonical] = raw[alt]
                break
    return json_safe(base)
