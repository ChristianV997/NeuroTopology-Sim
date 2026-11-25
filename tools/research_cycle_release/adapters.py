"""Read-only adapters from Batch 1 JSON into the release-evidence bundle.

Primary contract is the generic bundle (BUNDLE_SCHEMA). Awareness compiler and
registry exports are mapped onto that contract without importing Batch 1 code.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from tools.research_cycle_release.schema import BUNDLE_SCHEMA, json_safe

TERMINAL = frozenset(
    {
        "completed",
        "complete",
        "failed",
        "error",
        "cancelled",
        "canceled",
        "timeout",
        "timed_out",
        "done",
        "succeeded",
        "success",
        "terminal",
    }
)
SYNTHETIC = frozenset({"synthetic", "synthetic_simulation", "computational_model", "surrogate_baseline"})
PROXY = frozenset({"proxy", "proxy_bayes_factor", "proxy_only"})
EMPIRICAL = frozenset(
    {"empirical", "empirical_dataset", "formal", "preregistered_empirical", "empirically_constrained"}
)


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _is_terminal(status: Optional[str]) -> bool:
    return bool(status) and status.lower() in TERMINAL


def source_payload_checksum(payload: Dict[str, Any]) -> str:
    blob = json.dumps(json_safe(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def empty_bundle(*, cycle_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "bundle_schema": BUNDLE_SCHEMA,
        "cycle_id": cycle_id,
        "source_manifest_present": None,
        "source_manifest_path": None,
        "checksums_present": None,
        "checksum_entries": [],
        "configuration_locked": None,
        "code_commit": None,
        "seed": None,
        "input_provenance_complete": None,
        "input_provenance_missing": [],
        "outputs_finite": None,
        "non_finite_metric_paths": [],
        "metrics": {},
        "work_units": [],
        "all_work_units_terminal": None,
        "partial_runs_explicitly_marked": None,
        "artifact_lineage_complete": None,
        "artifact_lineage_missing": [],
        "validation_report_present": None,
        "validation_status": None,
        "null_metadata_applicable": None,
        "null_metadata_present": None,
        "multiplicity_metadata_applicable": None,
        "multiplicity_metadata_present": None,
        "forecasting_applicable": None,
        "forecasting_subject_split": None,
        "forecasting_session_split": None,
        "forecasting_time_split": None,
        "resource_budgets_respected": None,
        "resource_budget_details": {},
        "full_dataset_download": None,
        "network_policy_recorded": None,
        "network_policy_violated": None,
        "evidence_classes": [],
        "evidence_classes_consistent": None,
        "synthetic_only": None,
        "proxy_only": None,
        "empirical_present": None,
        "report_metadata_text": "",
        "infrastructure_blocked": None,
        "comparable": None,
        "comparability_notes": [],
        "hardware_metrics_advisory": True,
    }


def _scan_non_finite(obj: Any, path: str = "$") -> List[str]:
    bad: List[str] = []
    if isinstance(obj, float) and not math.isfinite(obj):
        bad.append(path)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            bad.extend(_scan_non_finite(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            bad.extend(_scan_non_finite(value, f"{path}[{idx}]"))
    return bad


def _classify(
    classes: List[str],
) -> Tuple[Optional[bool], Optional[bool], Optional[bool], Optional[bool]]:
    if not classes:
        return None, None, None, None
    norm = [c.lower() for c in classes]
    known = SYNTHETIC | PROXY | EMPIRICAL
    if not all(c in known for c in norm):
        emp = any(c in EMPIRICAL for c in norm)
        return None, None, emp if emp else None, None
    syn = all(c in SYNTHETIC for c in norm)
    prox = all(c in PROXY for c in norm)
    emp = any(c in EMPIRICAL for c in norm)
    return syn, prox, emp, not (emp and (syn or prox))


def _finalize_units(bundle: Dict[str, Any]) -> None:
    units = bundle.get("work_units") or []
    if not units:
        bundle["all_work_units_terminal"] = False
        bundle["partial_runs_explicitly_marked"] = False
        return
    bundle["all_work_units_terminal"] = all(
        _is_terminal(str(u.get("status"))) and not u.get("partial") for u in units
    )
    unmarked = [
        u for u in units if str(u.get("status", "")).lower() == "partial" and not u.get("partial")
    ]
    bundle["partial_runs_explicitly_marked"] = len(unmarked) == 0


def adapt_generic_bundle(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    inner = payload["bundle"] if isinstance(payload.get("bundle"), dict) else payload
    if not (
        inner.get("bundle_schema") == BUNDLE_SCHEMA
        or "work_units" in inner
        or "source_manifest_present" in inner
        or "checksums_present" in inner
    ):
        raise ValueError("not a generic release bundle")

    bundle = empty_bundle(cycle_id=_as_str(inner.get("cycle_id")))
    for key in list(bundle.keys()):
        if key in inner:
            bundle[key] = inner[key]

    metrics = inner.get("metrics")
    if isinstance(metrics, dict):
        cleaned: Dict[str, Any] = {}
        non_finite = list(bundle.get("non_finite_metric_paths") or [])
        for mk, mv in metrics.items():
            if isinstance(mv, float) and not math.isfinite(mv):
                cleaned[mk] = None
                non_finite.append(f"metrics.{mk}")
            else:
                cleaned[mk] = mv
        bundle["metrics"] = cleaned
        bundle["non_finite_metric_paths"] = non_finite
        if non_finite:
            bundle["outputs_finite"] = False

    if bundle.get("work_units") and bundle.get("all_work_units_terminal") is None:
        _finalize_units(bundle)

    classes = list(bundle.get("evidence_classes") or [])
    if classes and bundle.get("synthetic_only") is None:
        syn, prox, emp, cons = _classify(classes)
        bundle["synthetic_only"] = syn
        bundle["proxy_only"] = prox
        bundle["empirical_present"] = emp
        if bundle.get("evidence_classes_consistent") is None:
            bundle["evidence_classes_consistent"] = cons

    return json_safe(bundle), "generic_bundle"


def adapt_awareness_compiler_report(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Best-effort JSON mapping from Awareness compiler exports."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    if "artifact_ledger" not in payload and not (
        "cycle_states" in payload and "gate_results" in payload
    ):
        raise ValueError("not an awareness compiler report")

    cfg = payload.get("cycle_config") if isinstance(payload.get("cycle_config"), dict) else {}
    prov = payload.get("record_provenance") if isinstance(payload.get("record_provenance"), dict) else {}
    checksums = prov.get("source_checksums") if isinstance(prov.get("source_checksums"), dict) else {}
    ledger = [r for r in (payload.get("artifact_ledger") or []) if isinstance(r, dict)]
    executions = []
    if isinstance(payload.get("execution_results"), dict):
        executions = [e for e in (payload["execution_results"].get("executions") or []) if isinstance(e, dict)]
    plans = []
    if isinstance(payload.get("experiment_plans"), dict):
        plans = [p for p in (payload["experiment_plans"].get("plans") or []) if isinstance(p, dict)]
    nulls = []
    if isinstance(payload.get("null_surrogate_results"), dict):
        nulls = [n for n in (payload["null_surrogate_results"].get("null_tests") or []) if isinstance(n, dict)]
    validations = []
    if isinstance(payload.get("validation_reports"), dict):
        validations = [v for v in (payload["validation_reports"].get("reports") or []) if isinstance(v, dict)]

    mapped = empty_bundle(cycle_id=_as_str(cfg.get("cycle_id") or payload.get("cycle_id")))
    mapped["source_manifest_present"] = bool(prov.get("manifest_path") or payload.get("manifest_path"))
    mapped["source_manifest_path"] = _as_str(prov.get("manifest_path") or payload.get("manifest_path"))

    entries = []
    missing = []
    for key, meta in sorted(checksums.items()):
        if isinstance(meta, dict) and _as_str(meta.get("sha256") or meta.get("checksum")):
            entries.append(
                {
                    "section": key,
                    "sha256": _as_str(meta.get("sha256") or meta.get("checksum")),
                    "path": meta.get("path"),
                }
            )
        else:
            missing.append(str(key))
    completeness = payload.get("completeness") if isinstance(payload.get("completeness"), dict) else {}
    for section, info in completeness.items():
        if isinstance(info, dict) and info.get("available") is False:
            missing.append(str(section))
    mapped["checksum_entries"] = entries
    mapped["checksums_present"] = bool(entries)
    mapped["input_provenance_missing"] = sorted(set(missing))
    mapped["input_provenance_complete"] = (not missing) and bool(entries)

    commits = [_as_str(r.get("software_commit")) for r in ledger]
    commits = [c for c in commits if c]
    mapped["code_commit"] = commits[0] if commits else _as_str(cfg.get("software_commit") or cfg.get("code_commit"))
    mapped["seed"] = cfg.get("seed", cfg.get("random_seed"))
    mapped["configuration_locked"] = _as_bool(cfg.get("configuration_locked", cfg.get("config_locked")))

    exec_by = {e.get("experiment_id"): e for e in executions}
    units = []
    for row in ledger:
        eid = _as_str(row.get("experiment_id")) or "unknown"
        ex = exec_by.get(eid) or {}
        status = _as_str(ex.get("status") or row.get("status")) or "unknown"
        units.append(
            {
                "id": eid,
                "status": status,
                "partial": bool(ex.get("partial")) or status.lower() == "partial",
                "output_checksums": row.get("output_checksums") or ex.get("output_checksums") or [],
                "input_checksums": row.get("input_checksums") or ex.get("input_checksums") or [],
            }
        )
    if not units:
        for ex in executions:
            status = _as_str(ex.get("status")) or "unknown"
            units.append(
                {
                    "id": _as_str(ex.get("experiment_id")) or "unknown",
                    "status": status,
                    "partial": bool(ex.get("partial")) or status.lower() == "partial",
                    "output_checksums": ex.get("output_checksums") or [],
                    "input_checksums": ex.get("input_checksums") or [],
                }
            )
    mapped["work_units"] = units
    _finalize_units(mapped)

    lineage_missing = []
    for u in units:
        if not u.get("output_checksums"):
            lineage_missing.append(f"output:{u['id']}")
        if not u.get("input_checksums"):
            lineage_missing.append(f"input:{u['id']}")
    for row in ledger:
        if not (row.get("source_checksum") or row.get("source_checksums")):
            lineage_missing.append(f"source:{row.get('experiment_id')}")
    mapped["artifact_lineage_missing"] = sorted(set(lineage_missing))
    mapped["artifact_lineage_complete"] = bool(units) and not lineage_missing
    mapped["validation_report_present"] = bool(validations)
    if validations:
        mapped["validation_status"] = _as_str(validations[0].get("status") or validations[0].get("verdict"))

    forecasting = any(
        "forecast" in str(p.get("domain", "")).lower()
        or p.get("held_out_split_locked") is True
        or p.get("requires_forecasting_splits") is True
        for p in plans
    )
    mapped["forecasting_applicable"] = forecasting
    if forecasting:
        splits = cfg.get("forecasting_splits") if isinstance(cfg.get("forecasting_splits"), dict) else {}
        locked = any(p.get("held_out_split_locked") is True for p in plans)
        mapped["forecasting_subject_split"] = _as_bool(splits.get("subject")) if splits else locked
        mapped["forecasting_session_split"] = _as_bool(splits.get("session")) if splits else locked
        mapped["forecasting_time_split"] = _as_bool(splits.get("time")) if splits else locked

    mapped["null_metadata_applicable"] = True
    mapped["null_metadata_present"] = bool(nulls)
    multi = cfg.get("multiplicity") if isinstance(cfg.get("multiplicity"), dict) else {}
    mapped["multiplicity_metadata_applicable"] = True
    mapped["multiplicity_metadata_present"] = bool(
        multi.get("method") or multi.get("multiplicity_method") or cfg.get("multiplicity_method")
    )

    resource = cfg.get("resource_budget") if isinstance(cfg.get("resource_budget"), dict) else {}
    if resource:
        respected = _as_bool(resource.get("respected"))
        if respected is None and resource.get("exceeded") is not None:
            respected = not bool(resource.get("exceeded"))
        mapped["resource_budgets_respected"] = respected
        mapped["resource_budget_details"] = resource

    net = cfg.get("network_policy") if isinstance(cfg.get("network_policy"), dict) else {}
    mapped["network_policy_recorded"] = bool(net) or cfg.get("network_policy_recorded") is True
    mapped["network_policy_violated"] = (
        _as_bool(net.get("violated")) if net else _as_bool(cfg.get("network_policy_violated"))
    )
    if cfg.get("full_dataset_download") is not None:
        mapped["full_dataset_download"] = _as_bool(cfg.get("full_dataset_download"))
    elif net:
        mapped["full_dataset_download"] = _as_bool(net.get("full_dataset_download"))

    classes = []
    for row in ledger:
        if row.get("scientific_status"):
            classes.append(str(row["scientific_status"]))
    for ex in executions:
        if ex.get("data_mode"):
            classes.append(str(ex["data_mode"]))
    mapped["evidence_classes"] = sorted(set(classes))
    syn, prox, emp, cons = _classify(mapped["evidence_classes"])
    mapped["synthetic_only"] = syn
    mapped["proxy_only"] = prox
    mapped["empirical_present"] = emp
    mapped["evidence_classes_consistent"] = cons

    non_finite = _scan_non_finite(payload.get("execution_results") or {})
    non_finite += _scan_non_finite(payload.get("validation_reports") or {})
    mapped["non_finite_metric_paths"] = non_finite
    mapped["outputs_finite"] = not non_finite

    gates = payload.get("gate_results") if isinstance(payload.get("gate_results"), dict) else {}
    failed = [n for n, g in gates.items() if isinstance(g, dict) and g.get("passed") is False]
    if any("depend" in str(n).lower() for n in failed):
        mapped["infrastructure_blocked"] = True
    if any(r.get("dependency_state") in {"missing", "blocked"} for r in ledger):
        mapped["infrastructure_blocked"] = True

    limits = payload.get("scientific_limitations") or []
    paper = payload.get("paper_draft_markdown") or ""
    mapped["report_metadata_text"] = "\n".join([str(x) for x in limits] + [str(paper)[:4000]])
    return json_safe(mapped), "awareness_compiler_report"


def adapt_registry_export(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    if not (
        "hypotheses" in payload
        or "hypothesis_records" in payload
        or "experiment_plans" in payload
        or "plans" in payload
        or payload.get("schema") == "research_cycle_registry"
    ):
        raise ValueError("not a research_cycle registry export")

    hypotheses = [
        h for h in (payload.get("hypotheses") or payload.get("hypothesis_records") or []) if isinstance(h, dict)
    ]
    plans = [p for p in (payload.get("experiment_plans") or payload.get("plans") or []) if isinstance(p, dict)]
    evidence = [
        e for e in (payload.get("evidence_updates") or payload.get("evidence") or []) if isinstance(e, dict)
    ]
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    prov = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else meta

    mapped = empty_bundle(cycle_id=_as_str(payload.get("cycle_id") or meta.get("cycle_id")))
    mapped["source_manifest_present"] = bool(prov.get("manifest_path") or payload.get("manifest_path"))
    mapped["source_manifest_path"] = _as_str(prov.get("manifest_path") or payload.get("manifest_path"))
    mapped["code_commit"] = _as_str(prov.get("code_commit") or prov.get("software_commit") or meta.get("code_commit"))
    mapped["seed"] = prov.get("seed", meta.get("seed"))
    mapped["configuration_locked"] = _as_bool(prov.get("configuration_locked", meta.get("configuration_locked")))

    entries = []
    for record in list(hypotheses) + list(plans) + list(evidence):
        if record.get("checksum"):
            entries.append(
                {
                    "id": record.get("hypothesis_id") or record.get("experiment_id") or record.get("evidence_id"),
                    "sha256": record.get("checksum"),
                }
            )
    mapped["checksum_entries"] = entries
    mapped["checksums_present"] = bool(entries)
    missing = []
    if not mapped["source_manifest_present"]:
        missing.append("source_manifest")
    if not entries:
        missing.append("record_checksums")
    mapped["input_provenance_missing"] = missing
    mapped["input_provenance_complete"] = not missing

    units = []
    for plan in plans:
        status = _as_str(plan.get("status") or plan.get("execution_status")) or "unknown"
        units.append(
            {
                "id": _as_str(plan.get("experiment_id") or plan.get("plan_id")) or "unknown",
                "status": status,
                "partial": bool(plan.get("partial")),
                "output_checksums": plan.get("output_checksums")
                or ([plan["checksum"]] if plan.get("checksum") else []),
                "input_checksums": plan.get("input_checksums") or [],
            }
        )
    mapped["work_units"] = units
    _finalize_units(mapped)
    lineage_missing = [f"output:{u['id']}" for u in units if not u.get("output_checksums")]
    mapped["artifact_lineage_missing"] = lineage_missing
    mapped["artifact_lineage_complete"] = bool(units) and not lineage_missing

    val = payload.get("validation_report") or payload.get("validation")
    mapped["validation_report_present"] = val is not None
    if isinstance(val, dict):
        mapped["validation_status"] = _as_str(val.get("status") or val.get("verdict"))

    domains = [str(p.get("domain", "")) for p in plans]
    forecasting = any("forecast" in d.lower() for d in domains) or bool(meta.get("forecasting"))
    mapped["forecasting_applicable"] = forecasting
    splits = meta.get("forecasting_splits") if isinstance(meta.get("forecasting_splits"), dict) else {}
    if forecasting:
        mapped["forecasting_subject_split"] = _as_bool(splits.get("subject"))
        mapped["forecasting_session_split"] = _as_bool(splits.get("session"))
        mapped["forecasting_time_split"] = _as_bool(splits.get("time"))

    null_meta = meta.get("null_metadata") if isinstance(meta.get("null_metadata"), dict) else {}
    mapped["null_metadata_applicable"] = True
    mapped["null_metadata_present"] = bool(null_meta) or any("null" in d.lower() for d in domains)
    multi = meta.get("multiplicity") if isinstance(meta.get("multiplicity"), dict) else {}
    mapped["multiplicity_metadata_applicable"] = True
    mapped["multiplicity_metadata_present"] = bool(multi.get("method") or meta.get("multiplicity_method"))

    resource = meta.get("resource_budget") if isinstance(meta.get("resource_budget"), dict) else {}
    if resource:
        respected = _as_bool(resource.get("respected"))
        if respected is None and resource.get("exceeded") is not None:
            respected = not bool(resource.get("exceeded"))
        mapped["resource_budgets_respected"] = respected
        mapped["resource_budget_details"] = resource

    net = meta.get("network_policy") if isinstance(meta.get("network_policy"), dict) else {}
    mapped["network_policy_recorded"] = bool(net) or meta.get("network_policy_recorded") is True
    mapped["network_policy_violated"] = (
        _as_bool(net.get("violated")) if net else _as_bool(meta.get("network_policy_violated"))
    )
    mapped["full_dataset_download"] = _as_bool(meta.get("full_dataset_download"))

    classes = []
    for ev in evidence:
        dt = ev.get("data_type") or ev.get("evidence_class")
        if dt:
            classes.append(str(dt))
    for hyp in hypotheses:
        if hyp.get("epistemic_label"):
            classes.append(str(hyp["epistemic_label"]))
    mapped["evidence_classes"] = sorted(set(classes))
    syn, prox, emp, cons = _classify(classes)
    mapped["synthetic_only"] = syn
    mapped["proxy_only"] = prox
    mapped["empirical_present"] = emp
    mapped["evidence_classes_consistent"] = cons

    non_finite = _scan_non_finite(payload)
    metric_bad = [
        p for p in non_finite if any(t in p.lower() for t in ("metric", "runtime", "score", "rss", "memory"))
    ]
    mapped["non_finite_metric_paths"] = metric_bad if metric_bad else non_finite
    mapped["outputs_finite"] = not mapped["non_finite_metric_paths"]
    mapped["report_metadata_text"] = "\n".join(
        str(h.get("precise_claim") or h.get("statement") or "") for h in hypotheses
    )
    if meta.get("infrastructure_blocked") is True:
        mapped["infrastructure_blocked"] = True
    if meta.get("comparable") is False:
        mapped["comparable"] = False
        mapped["comparability_notes"] = [str(meta.get("comparability_reason") or "declared_not_comparable")]
    return json_safe(mapped), "research_cycle_registry_export"


def adapt_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a JSON object")
    if isinstance(payload.get("bundle"), dict) and payload.get("bundle_schema") == BUNDLE_SCHEMA:
        return adapt_generic_bundle(payload)
    if payload.get("bundle_schema") == BUNDLE_SCHEMA or "source_manifest_present" in payload:
        try:
            return adapt_generic_bundle(payload)
        except ValueError:
            pass
    if "artifact_ledger" in payload or ("cycle_states" in payload and "gate_results" in payload):
        return adapt_awareness_compiler_report(payload)
    if (
        "hypotheses" in payload
        or "hypothesis_records" in payload
        or payload.get("schema") == "research_cycle_registry"
    ):
        return adapt_registry_export(payload)
    if "work_units" in payload or "cycle_id" in payload:
        return adapt_generic_bundle(payload)
    raise ValueError(
        "Unrecognized research-cycle payload. Provide a release bundle, "
        "Awareness compiler report, or research_cycle registry export."
    )
