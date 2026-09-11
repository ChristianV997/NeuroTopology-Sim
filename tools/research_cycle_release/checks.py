"""Operational checks and decision selection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tools.research_cycle_release.language import scan_report_metadata
from tools.research_cycle_release.schema import CheckResult, DecisionState


def _check(check_id: str, passed: Optional[bool], detail: str = "", **evidence: Any) -> CheckResult:
    return CheckResult(check_id=check_id, passed=passed, detail=detail, evidence=dict(evidence))


def _tri(value: Any) -> Optional[bool]:
    if value is True:
        return True
    if value is False:
        return False
    return None


def run_checks(bundle: Dict[str, Any]) -> List[CheckResult]:
    checks: List[CheckResult] = []
    checks.append(
        _check(
            "source_manifest_present",
            _tri(bundle.get("source_manifest_present")),
            "source manifest must be present",
            path=bundle.get("source_manifest_path"),
        )
    )
    checks.append(
        _check(
            "checksums_present",
            _tri(bundle.get("checksums_present")),
            "checksums must be present",
            entries=len(bundle.get("checksum_entries") or []),
        )
    )
    checks.append(
        _check(
            "configuration_locked",
            _tri(bundle.get("configuration_locked")),
            "configuration must be locked",
        )
    )

    commit = bundle.get("code_commit")
    commit_pass = None if commit is None else bool(str(commit).strip())
    checks.append(_check("code_commit_recorded", commit_pass, "code commit must be recorded", code_commit=commit))

    seed = bundle.get("seed")
    seed_pass = None if seed is None else seed != ""
    checks.append(_check("seed_recorded", seed_pass, "seed must be recorded", seed=seed))

    checks.append(
        _check(
            "input_provenance_complete",
            _tri(bundle.get("input_provenance_complete")),
            "input provenance must be complete",
            missing=bundle.get("input_provenance_missing") or [],
        )
    )

    finite = bundle.get("outputs_finite")
    non_finite = list(bundle.get("non_finite_metric_paths") or [])
    if finite is None and non_finite:
        finite = False
    checks.append(
        _check("outputs_finite", _tri(finite), "outputs must be finite", non_finite_metric_paths=non_finite)
    )
    checks.append(
        _check(
            "all_work_units_terminal",
            _tri(bundle.get("all_work_units_terminal")),
            "all required work units must be terminal",
            work_units=len(bundle.get("work_units") or []),
        )
    )
    checks.append(
        _check(
            "partial_runs_explicitly_marked",
            _tri(bundle.get("partial_runs_explicitly_marked")),
            "partial runs must be explicitly marked",
        )
    )
    checks.append(
        _check(
            "artifact_lineage_complete",
            _tri(bundle.get("artifact_lineage_complete")),
            "artifact lineage must be complete",
            missing=bundle.get("artifact_lineage_missing") or [],
        )
    )
    checks.append(
        _check(
            "validation_report_present",
            _tri(bundle.get("validation_report_present")),
            "validation report must be present",
            status=bundle.get("validation_status"),
        )
    )

    null_app = bundle.get("null_metadata_applicable")
    null_pres = bundle.get("null_metadata_present")
    if null_app is False:
        null_pass: Optional[bool] = True
    elif null_app is True:
        null_pass = _tri(null_pres)
    else:
        null_pass = None
    checks.append(_check("null_metadata", null_pass, "null metadata where applicable", applicable=null_app, present=null_pres))

    multi_app = bundle.get("multiplicity_metadata_applicable")
    multi_pres = bundle.get("multiplicity_metadata_present")
    if multi_app is False:
        multi_pass: Optional[bool] = True
    elif multi_app is True:
        multi_pass = _tri(multi_pres)
    else:
        multi_pass = None
    checks.append(
        _check("multiplicity_metadata", multi_pass, "multiplicity metadata where applicable", applicable=multi_app, present=multi_pres)
    )

    forecast_app = bundle.get("forecasting_applicable")
    if forecast_app is False:
        split_pass: Optional[bool] = True
    elif forecast_app is True:
        splits = [
            bundle.get("forecasting_subject_split"),
            bundle.get("forecasting_session_split"),
            bundle.get("forecasting_time_split"),
        ]
        if any(s is False for s in splits):
            split_pass = False
        elif any(s is None for s in splits):
            split_pass = None
        else:
            split_pass = True
    else:
        split_pass = None
    checks.append(
        _check(
            "forecasting_splits",
            split_pass,
            "subject/session/time splits required for forecasting",
            subject=bundle.get("forecasting_subject_split"),
            session=bundle.get("forecasting_session_split"),
            time=bundle.get("forecasting_time_split"),
        )
    )

    checks.append(
        _check(
            "resource_budgets_respected",
            _tri(bundle.get("resource_budgets_respected")),
            "resource budgets must be respected",
            details=bundle.get("resource_budget_details") or {},
        )
    )

    full_dl = bundle.get("full_dataset_download")
    if full_dl is True:
        dl_pass: Optional[bool] = False
    elif full_dl is False:
        dl_pass = True
    else:
        dl_pass = None
    checks.append(_check("no_full_dataset_download", dl_pass, "full-dataset download forbidden", full_dataset_download=full_dl))

    checks.append(
        _check(
            "network_policy_recorded",
            _tri(bundle.get("network_policy_recorded")),
            "network policy must be recorded",
        )
    )

    net_violated = bundle.get("network_policy_violated")
    if net_violated is True:
        net_ok: Optional[bool] = False
    elif net_violated is False:
        net_ok = True
    else:
        net_ok = None
    checks.append(_check("network_policy_not_violated", net_ok, "network policy must not be violated", violated=net_violated))

    checks.append(
        _check(
            "evidence_classes_consistent",
            _tri(bundle.get("evidence_classes_consistent")),
            "synthetic/proxy/empirical classes must be consistent",
            classes=bundle.get("evidence_classes") or [],
        )
    )

    text = str(bundle.get("report_metadata_text") or "")
    forbidden, has_causal, has_proxy_promo = scan_report_metadata(text)
    lang_ok: Optional[bool] = True if not text else (not forbidden and not has_causal and not has_proxy_promo)
    checks.append(
        _check(
            "no_unsupported_causal_language",
            lang_ok,
            "no unsupported causal language in report metadata",
            forbidden_phrases=forbidden,
            causal_language=has_causal,
            proxy_to_causal=has_proxy_promo,
        )
    )

    infra = bundle.get("infrastructure_blocked")
    if infra is True:
        infra_ok: Optional[bool] = False
    elif infra is False:
        infra_ok = True
    else:
        infra_ok = None
    checks.append(_check("infrastructure_not_blocked", infra_ok, "infrastructure must not be blocked", blocked=infra))

    checks.append(
        _check(
            "comparable",
            _tri(bundle.get("comparable")),
            "cycle evidence must be comparable when claimed",
            notes=bundle.get("comparability_notes") or [],
        )
    )
    return checks


def decide_from_checks(
    bundle: Dict[str, Any], checks: List[CheckResult]
) -> Tuple[DecisionState, List[str], List[str]]:
    by_id = {c.check_id: c for c in checks}

    def failed(cid: str) -> bool:
        c = by_id.get(cid)
        return c is not None and c.passed is False

    def unknown(cid: str) -> bool:
        c = by_id.get(cid)
        return c is not None and c.passed is None

    if failed("network_policy_not_violated") or failed("no_full_dataset_download"):
        return DecisionState.NETWORK_POLICY_FAILURE, ["network_policy_failure"], [
            "Network policy violated or full-dataset download detected."
        ]
    if failed("infrastructure_not_blocked"):
        return DecisionState.INFRASTRUCTURE_BLOCKED, ["infrastructure_blocked"], [
            "Infrastructure dependencies are blocked."
        ]

    provenance_ids = [
        "source_manifest_present",
        "checksums_present",
        "configuration_locked",
        "code_commit_recorded",
        "seed_recorded",
        "input_provenance_complete",
    ]
    if any(failed(i) for i in provenance_ids):
        hit = [i for i in provenance_ids if failed(i)]
        return DecisionState.PROVENANCE_FAILURE, ["provenance_failure"], [
            "Provenance incomplete: " + ", ".join(hit)
        ]

    if failed("artifact_lineage_complete"):
        return DecisionState.ARTIFACT_FAILURE, ["artifact_failure"], ["Artifact lineage incomplete."]

    val_status = str(bundle.get("validation_status") or "").lower()
    if failed("validation_report_present") or val_status in {"failed", "error", "invalid"}:
        return DecisionState.VALIDATION_FAILURE, ["validation_failure"], [
            "Validation report missing or failed."
        ]

    if failed("resource_budgets_respected"):
        return DecisionState.RESOURCE_FAILURE, ["resource_failure"], ["Resource budgets exceeded."]

    if failed("comparable") or failed("evidence_classes_consistent"):
        return DecisionState.NOT_COMPARABLE, ["not_comparable"], [
            "Evidence not comparable or class-inconsistent."
        ]

    if failed("outputs_finite") or failed("no_unsupported_causal_language"):
        return DecisionState.VALIDATION_FAILURE, ["validation_failure"], [
            "Non-finite outputs or unsupported causal language in metadata."
        ]

    incomplete_ids = [
        "all_work_units_terminal",
        "partial_runs_explicitly_marked",
        "null_metadata",
        "multiplicity_metadata",
        "forecasting_splits",
        "network_policy_recorded",
    ]
    if any(failed(i) for i in incomplete_ids) or any(
        unknown(i) for i in provenance_ids + ["artifact_lineage_complete", "validation_report_present"]
    ):
        hit = [i for i in incomplete_ids + provenance_ids if failed(i) or unknown(i)]
        return DecisionState.EVIDENCE_INCOMPLETE, ["evidence_incomplete"], [
            "Operational evidence incomplete: " + ", ".join(hit[:8])
        ]

    if bundle.get("proxy_only") is True:
        return DecisionState.PROXY_ONLY, ["proxy_only"], [
            "Cycle is proxy-only; proxy results are not causal evidence."
        ]
    if bundle.get("synthetic_only") is True:
        return DecisionState.SYNTHETIC_ONLY, ["synthetic_only"], [
            "Cycle is synthetic-only; engineering evidence only."
        ]
    if bundle.get("empirical_present") is True:
        return DecisionState.SCIENTIFIC_REVIEW_REQUIRED, ["scientific_review_required"], [
            "Empirical content present — operationally reviewable but scientific claim gate review is still required."
        ]

    return DecisionState.EVIDENCE_READY_FOR_REVIEW, ["evidence_ready_for_review"], [
        "Operational checks passed for human review. This is not scientific PASS and emits no Bayes factor."
    ]
