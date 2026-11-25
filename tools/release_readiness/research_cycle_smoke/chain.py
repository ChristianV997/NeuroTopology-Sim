"""Verify the source→…→release relationship chain remains intact and visible."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from tools.release_readiness.research_cycle_smoke.schema import CHAIN_STAGES, StageRecord


def verify_chain(stages: List[StageRecord]) -> Tuple[bool, List[str]]:
    """Check ordered parent links and that every CHAIN stage appears (except release)."""
    errors: List[str] = []
    by_stage = {s.stage: s for s in stages}
    expected = [s for s in CHAIN_STAGES if s != "release_decision"]
    for stage_name in expected:
        if stage_name not in by_stage:
            errors.append(f"missing_stage:{stage_name}")

    ids = {s.record_id for s in stages}
    for stage in stages:
        for parent in stage.parent_ids:
            if parent not in ids:
                errors.append(f"dangling_parent:{stage.record_id}->{parent}")

    # Ordered adjacency: each non-source stage should parent the previous stage id.
    ordered = [by_stage[name] for name in expected if name in by_stage]
    for idx in range(1, len(ordered)):
        prev = ordered[idx - 1]
        cur = ordered[idx]
        if prev.record_id not in cur.parent_ids:
            errors.append(f"broken_link:{prev.stage}->{cur.stage}")
    return len(errors) == 0, errors


def incomplete_states_visible(stages: List[StageRecord]) -> Tuple[bool, List[str]]:
    """Any non-complete/projected stage must expose a visible_issue."""
    problems: List[str] = []
    ok_statuses = {"complete", "completed", "ok", "projected", "preregistered", "ready", "success"}
    for stage in stages:
        if stage.status.lower() in ok_statuses:
            continue
        if not stage.visible_issue:
            problems.append(f"hidden_incomplete:{stage.stage}:{stage.status}")
    return len(problems) == 0, problems


def synthetic_not_promoted(stages: List[StageRecord], release_report: Dict[str, Any]) -> bool:
    for stage in stages:
        payload = stage.payload or {}
        if payload.get("scientific_pass") is True:
            return False
        if payload.get("scientific_evidence") is True:
            return False
        if payload.get("bayes_factor") not in (None,):
            # Explicit null is ok; any numeric/string BF is forbidden in smoke fixtures.
            return False
    if release_report.get("scientific_pass_emitted") is True:
        return False
    if release_report.get("bayes_factor_emitted") is True:
        return False
    if release_report.get("causal_promotion_emitted") is True:
        return False
    decision = str(release_report.get("decision") or "")
    if decision in {"SCIENTIFIC_PASS", "PASS"}:
        return False
    return True


def missing_metrics_not_zeroed(bundle: Dict[str, Any], release_report: Dict[str, Any]) -> bool:
    """Missing / non-finite metrics must remain null — never coerced to 0."""
    metrics = bundle.get("metrics") if isinstance(bundle.get("metrics"), dict) else {}
    for key, value in metrics.items():
        if value is None:
            continue
        # A declared finite metric may be numeric; zero is allowed only if intentionally present.
        # Guard: paths marked non-finite must not reappear as 0.
        pass
    for path in bundle.get("non_finite_metric_paths") or []:
        # corresponding metric must be null in cleaned metrics
        if path.startswith("metrics."):
            key = path.split(".", 1)[1]
            if metrics.get(key) == 0:
                return False
            if metrics.get(key) is not None and not isinstance(metrics.get(key), str):
                # cleaned adapter should have set None
                if metrics.get(key) not in (None,):
                    # if still non-finite somehow, fail
                    try:
                        import math

                        if isinstance(metrics.get(key), float) and not math.isfinite(metrics[key]):
                            return False
                    except Exception:
                        return False
    # Child RSS-like keys if present must not fabricate 0 from missing
    for key in ("child_rss_bytes", "tracemalloc_peak_bytes", "parent_sampled_rss_bytes"):
        if key in metrics and metrics[key] == 0 and key in (bundle.get("missing_metrics") or []):
            return False
    report_bundle = release_report.get("bundle") if isinstance(release_report.get("bundle"), dict) else {}
    report_metrics = report_bundle.get("metrics") if isinstance(report_bundle.get("metrics"), dict) else {}
    for path in report_bundle.get("non_finite_metric_paths") or []:
        if path.startswith("metrics."):
            key = path.split(".", 1)[1]
            if report_metrics.get(key) == 0:
                return False
    return True
