"""Adapters integrating Research Cycle Bridge with existing canonical schemas and gates.

Adapts:
1. Simulation artifact lineage reports (`SimulationArtifactLineage.v1`) to bridge components.
2. Experiment plans (`ExperimentPlan.v1`) to bridge components.
3. Bridge records to release-evidence bundle (`research_cycle_release_bundle.v1`).
4. Bridge records to auditable research claims (`shared.research_claims`).
"""
from __future__ import annotations

from typing import Any, Mapping

from tools.research_cycle_bridge.models import (
    BridgeDataMode,
    BridgeEvidenceClass,
    BridgeRecordStatus,
    canonical_hash,
    finite_value,
)
from tools.research_cycle_release.schema import BUNDLE_SCHEMA


def adapt_simulation_lineage(lineage: Mapping[str, Any]) -> dict[str, Any]:
    """Convert an extract_run() simulation lineage report into bridge sub-structures."""
    status = str(lineage.get("status", "INCOMPLETE")).upper()
    provenance = dict(lineage.get("provenance", {}))
    artifacts_info = dict(lineage.get("artifact_manifest", {}))
    diagnostics = dict(lineage.get("diagnostics", {}))
    relationships = list(lineage.get("relationships", []))

    # Determine data modality only from explicit provenance. Missing or
    # unrecognized modality is unavailable, never empirical by default.
    diagnostics.setdefault("missing", [])
    diagnostics.setdefault("errors", [])
    diagnostics.setdefault("conflicting", [])
    raw_mode = provenance.get("data_mode")
    mode = str(raw_mode).strip().lower() if raw_mode is not None else ""
    if mode in {"synthetic", "synthetic_demo", "synthetic_simulation"} or provenance.get("synthetic") is True:
        data_mode = "synthetic"
    elif mode in {"proxy", "proxy_bayes_factor", "proxy_only"} or provenance.get("proxy") is True:
        data_mode = "proxy"
    elif mode in {"empirical", "empirical_dataset"}:
        data_mode = "empirical"
    else:
        data_mode = "unavailable"
        diagnostics["missing" if not mode else "errors"].append(
            "provenance.data_mode is missing or unrecognized; scientific modality is unavailable"
        )

    synthetic = data_mode == "synthetic"
    proxy = data_mode == "proxy"
    empirical = data_mode == "empirical" and not synthetic and not proxy
    if mode in {"empirical", "empirical_dataset"} and (provenance.get("synthetic") is True or provenance.get("proxy") is True):
        diagnostics["conflicting"].append("provenance data_mode=empirical conflicts with synthetic/proxy flag")
        empirical = False
        data_mode = "unavailable"

    # Normalize evidence class to recognized vocabulary
    raw_ev_class = provenance.get("evidence_class")
    if synthetic:
        evidence_class = "computational_model" if raw_ev_class == "simulation_artifact" else "synthetic_simulation"
    elif proxy:
        evidence_class = "proxy_only"
    elif empirical:
        evidence_class = "empirical_dataset"
    else:
        evidence_class = "unspecified"

    missing_prov = [field for field in ("run_id", "created_at", "source") if not provenance.get(field)]
    if missing_prov:
        diagnostics["missing"].extend(
            f"provenance.{field}" for field in missing_prov if f"provenance.{field}" not in diagnostics["missing"]
        )
        if status == "COMPLETE":
            status = "INCOMPLETE"
    if data_mode == "unavailable" and status == "COMPLETE":
        status = "INCOMPLETE"

    artifacts_list = artifacts_info.get("artifacts", [])
    validation_report_entry = None

    for entry in artifacts_list:
        role = entry.get("role")
        if role == "validation_report":
            validation_report_entry = entry

    return {
        "status": status,
        "data_mode": data_mode,
        "synthetic": synthetic,
        "proxy": proxy,
        "empirical": empirical,
        "evidence_class": evidence_class,
        "provenance": provenance,
        "artifact_manifest": artifacts_info,
        "diagnostics": diagnostics,
        "relationships": relationships,
        "validation_report_entry": validation_report_entry,
        "lineage_checksum": lineage.get("report_sha256") or canonical_hash(lineage),
    }


def adapt_bridge_to_release_bundle(
    record_dict: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt a bridge record mapping into a canonical release-evidence bundle."""
    prov = record_dict.get("provenance", {})
    artifacts_meta = record_dict.get("artifact_manifest", {})
    diagnostics = record_dict.get("diagnostics", {})
    status = record_dict.get("status", "INCOMPLETE")

    artifacts = artifacts_meta.get("artifacts", [])
    checksum_entries = [a["sha256"] for a in artifacts if a.get("sha256")]

    val_rep = record_dict.get("validation_report")
    has_validation = bool(
        (isinstance(val_rep, Mapping) and not val_rep.get("missing"))
        or any(a.get("role") == "validation_report" for a in artifacts)
    )

    missing_prov: list[str] = []
    for f in ("run_id", "created_at", "source"):
        if not prov.get(f):
            missing_prov.append(f)

    # Extract metrics while strictly preserving nulls
    metrics: dict[str, Any] = {}
    sim_run = record_dict.get("simulation_run") or {}
    if "metrics" in sim_run and isinstance(sim_run["metrics"], Mapping):
        for k, v in sim_run["metrics"].items():
            metrics[k] = finite_value(v)

    work_unit = {
        "unit_id": prov.get("run_id") or "unavailable",
        "status": "completed" if status == "COMPLETE" else ("failed" if status == "FAILED" else "in_progress"),
        "metrics": metrics,
    }

    # Extract seed only when explicitly declared; missing metadata stays null.
    seed = prov.get("seed")
    if seed is None and isinstance(prov.get("input"), Mapping):
        seed = prov["input"].get("seed")
    if seed is None:
        plan_vars = record_dict.get("experiment_plan", {})
        if isinstance(plan_vars, Mapping):
            vars_dict = plan_vars.get("variables", {})
            if isinstance(vars_dict, Mapping):
                seed = vars_dict.get("seed")
    code_commit = prov.get("git_commit") or prov.get("code_commit")

    bundle: dict[str, Any] = {
        "bundle_schema": BUNDLE_SCHEMA,
        "cycle_id": record_dict.get("cycle_id"),
        "source_manifest_present": bool(artifacts_meta.get("artifacts")),
        "source_manifest_path": artifacts_meta.get("run_directory"),
        "checksums_present": bool(checksum_entries),
        "checksum_entries": checksum_entries,
        "configuration_locked": bool(prov.get("configuration_fingerprint")),
        "code_commit": code_commit,
        "seed": seed,
        "input_provenance_complete": len(missing_prov) == 0,
        "input_provenance_missing": missing_prov,
        "outputs_finite": record_dict.get("outputs_finite"),
        "non_finite_metric_paths": [],
        "metrics": metrics,
        "work_units": [work_unit],
        "all_work_units_terminal": status in {"COMPLETE", "FAILED"},
        "partial_runs_explicitly_marked": status in {"COMPLETE", "PARTIAL", "FAILED", "INCOMPLETE", "BLOCKED", "CONFLICTING", "UNAVAILABLE"},
        "artifact_lineage_complete": status == "COMPLETE",
        "artifact_lineage_missing": diagnostics.get("missing", []),
        "validation_report_present": has_validation,
        "validation_status": (
            str(val_rep.get("status"))
            if has_validation and isinstance(val_rep, Mapping) and val_rep.get("status") is not None
            else None
        ),
        "null_metadata_applicable": False,
        "null_metadata_present": False,
        "multiplicity_metadata_applicable": False,
        "multiplicity_metadata_present": False,
        "forecasting_applicable": False,
        "forecasting_subject_split": None,
        "forecasting_session_split": None,
        "forecasting_time_split": None,
        "resource_budgets_respected": record_dict.get("resource_budgets_respected"),
        "resource_budget_details": {},
        "full_dataset_download": False,
        "network_policy_recorded": record_dict.get("network_policy_recorded"),
        "network_policy_violated": record_dict.get("network_policy_violated"),
        "evidence_classes": [record_dict.get("evidence_class", "unspecified")],
        "evidence_classes_consistent": record_dict.get("evidence_classes_consistent"),
        "synthetic_only": record_dict.get("synthetic", False),
        "proxy_only": record_dict.get("proxy", False),
        "empirical_present": bool(record_dict.get("empirical", False)) and not missing_prov,
        "report_metadata_text": f"Bridge record {record_dict.get('record_id')}",
        "infrastructure_blocked": status in {"BLOCKED", "UNAVAILABLE"} or bool(missing_prov),
        "comparable": bool(status == "COMPLETE" and not missing_prov and record_dict.get("data_mode") != "unavailable"),
        "comparability_notes": [],
        "hardware_metrics_advisory": True,
    }

    return bundle


def adapt_bridge_to_claims(record_dict: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Generate auditable research claim records reflecting bridge guardrails."""
    prov = record_dict.get("provenance", {})
    run_id = prov.get("run_id") or "unavailable"
    synthetic = record_dict.get("synthetic", False)
    proxy = record_dict.get("proxy", False)

    if synthetic:
        claim_cat = "synthetic_demonstration"
        ev_class = "synthetic_demonstration"
        emp_status = "synthetic"
        proxy_status = "not_applicable"
        text = f"Synthetic benchmark execution for run {run_id} validates container pipeline contracts."
    elif proxy:
        claim_cat = "proxy_inference"
        ev_class = "proxy_inference"
        emp_status = "not_applicable"
        proxy_status = "proxy"
        text = f"Proxy surrogate evaluation for run {run_id} checks baseline numerical bounds."
    elif (
        record_dict.get("data_mode") == "empirical"
        and record_dict.get("empirical") is True
        and all(prov.get(field) for field in ("run_id", "created_at", "source"))
    ):
        claim_cat = "empirical_observation"
        ev_class = "empirical_observation"
        emp_status = "empirical"
        proxy_status = "formal"
        text = f"Simulation analysis on dataset for run {run_id} extracts empirical topological features."
    else:
        claim_cat = "unsupported_claim"
        ev_class = "unsupported_claim"
        emp_status = "unknown"
        proxy_status = "unknown"
        text = f"No scientific claim generated for run {run_id}: provenance or data modality is incomplete."

    claim = {
        "claim_id": f"claim-bridge-{run_id}",
        "text": text,
        "claim_category": claim_cat,
        "evidence_class": ev_class,
        "empirical_synthetic_status": emp_status,
        "proxy_formal_status": proxy_status,
        "reviewer_state": "pending",
        "falsifiability_condition": f"Run {run_id} outputs non-finite values or violates contract schema.",
        "provenance_reference": f"run_id:{run_id};created_at:{prov.get('created_at')};source:{prov.get('source')}",
        "data_origin": str(prov.get("source", "local_synthesizer")),
        "required_controls": ["finite_check", "schema_validation"],
        "allowed_language": [],
        "prohibited_language": [],
    }
    return [claim]
