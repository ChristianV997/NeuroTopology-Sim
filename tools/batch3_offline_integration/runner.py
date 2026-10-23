"""Deterministic offline fixture runner for Batch 3 integration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from tools.batch3_offline_integration.allowlist import STAGE_ORDER, STAGE_SPECS
from tools.batch3_offline_integration.guards import no_network
from tools.batch3_offline_integration.fixture_producers import MAX_FIXTURE_BYTES, display_fixture_name
from tools.batch3_offline_integration.schema import (
    EVIDENCE_CLASS,
    RELATED_BUT_DISTINCT,
    RESULT_LABEL_ENGINEERING,
    SCHEMA_VERSION,
    StageOutcome,
)
from tools.batch3_offline_integration.serialization import dumps, json_safe, sha256_hex
from tools.batch3_offline_integration.stages import execute_stage


def run_offline_integration(
    *,
    fixture_name: str = "workflow_request.json",
    prior_run_dir: Optional[str] = None,
    force_fail_stage: Optional[str] = None,
    stage_ids: Optional[Sequence[str]] = None,
    created_at: str = "2026-10-16T00:00:00Z",
) -> Dict[str, Any]:
    """Run the fixed allowlisted stage sequence under a no-network guard.

    Returns an ENGINEERING_ONLY / SYNTHETIC_ONLY report. Never claims scientific
    validity. Workflow success is distinct from scientific validity.
    """
    if stage_ids is None:
        selected = list(STAGE_ORDER)
    else:
        if isinstance(stage_ids, (str, bytes)):
            raise ValueError("stage_ids must be a sequence of fixed allowlist stage identifiers")
        selected = []
        try:
            for stage_id in stage_ids:
                if len(selected) >= len(STAGE_ORDER):
                    raise ValueError("stage_ids exceeds the maximum number of fixed allowlist stages")
                selected.append(stage_id)
        except TypeError:
            raise ValueError("stage_ids must be a sequence of fixed allowlist stage identifiers") from None
    if not selected:
        raise ValueError("stage_ids must select at least one fixed allowlist stage")
    if any(not isinstance(stage_id, str) or stage_id not in STAGE_ORDER for stage_id in selected):
        raise ValueError("stage_ids must contain only fixed allowlist stage identifiers")
    if len(set(selected)) != len(selected):
        raise ValueError("stage_ids must not contain duplicate stage identifiers")
    if force_fail_stage is not None and (
        not isinstance(force_fail_stage, str) or force_fail_stage not in STAGE_ORDER
    ):
        raise ValueError("force_fail_stage must match a fixed allowlist stage identifier")

    specs = [s for s in STAGE_SPECS if s.stage_id in selected]
    specs.sort(key=lambda s: s.order)

    context: Dict[str, Any] = {"stages": {}}
    stage_records: List[Dict[str, Any]] = []

    with no_network():
        for spec in specs:
            record = execute_stage(
                spec,
                context=context,
                fixture_name=fixture_name,
                force_fail_stage=force_fail_stage,
                prior_run_dir=prior_run_dir,
            )
            context["stages"][spec.stage_id] = record
            stage_records.append(record)

    executed = [
        r["stage_id"]
        for r in stage_records
        if r["outcome"]
        in {
            StageOutcome.SUCCEEDED.value,
            StageOutcome.FAILED.value,
            StageOutcome.REJECTED_NONFINITE.value,
            StageOutcome.REJECTED_SCHEMA.value,
            StageOutcome.REJECTED_INVALID_INPUT.value,
        }
        and r.get("actual_upstream_producer_ran")
    ]
    fixture_producers = [
        r["stage_id"]
        for r in stage_records
        if r.get("execution_mode") in {"fixture_producer", "fixture_substitute"}
        or r["outcome"]
        in {
            StageOutcome.FIXTURE_SUBSTITUTED.value,
            StageOutcome.SKIPPED_OPTIONAL_ABSENT.value,
        }
    ]
    skipped_after_failure = [
        r["stage_id"] for r in stage_records if r["outcome"] == StageOutcome.SKIPPED_UPSTREAM_FAILED.value
    ]

    required_specs = [s for s in STAGE_SPECS if s.required]
    required_ok = all(
        s.stage_id in selected
        and (context["stages"].get(s.stage_id) or {}).get("outcome") == StageOutcome.SUCCEEDED.value
        for s in required_specs
    )

    # Observed stage order must match allowlist order for selected stages.
    observed_order = [r["stage_id"] for r in stage_records]
    expected_order = [s.stage_id for s in specs]
    order_ok = observed_order == expected_order
    rejected_input = any(
        r["outcome"]
        in {
            StageOutcome.REJECTED_NONFINITE.value,
            StageOutcome.REJECTED_SCHEMA.value,
            StageOutcome.REJECTED_INVALID_INPUT.value,
        }
        for r in stage_records
    )
    # Any selected stage that failed (including force-fail on optional stages)
    # clears workflow success. Optional absence (skipped_optional_absent) does not.
    any_failed = any(r["outcome"] == StageOutcome.FAILED.value for r in stage_records)

    release_decision = None
    release_rec = context["stages"].get("release_evaluate") or {}
    if release_rec.get("outputs"):
        release_decision = release_rec["outputs"].get("decision")

    content = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "result_label": RESULT_LABEL_ENGINEERING,
        "created_at": created_at,
        "network_accessed": False,
        "dependencies_installed": False,
        "data_downloaded": False,
        "caller_run_data_scanned": False,
        "fixture_max_bytes": MAX_FIXTURE_BYTES,
        "scientific_validity_claimed": False,
        "scientific_pass_emitted": False,
        "workflow_executed_successfully": bool(
            required_ok and order_ok and not rejected_input and not any_failed
        ),
        "fixture_name": display_fixture_name(fixture_name),
        "stage_order_expected": expected_order,
        "stage_order_observed": observed_order,
        "stage_order_ok": order_ok,
        "stages_executed_allowlisted": executed,
        "stages_fixture_substituted_or_producer": fixture_producers,
        "stages_skipped_upstream_failed": skipped_after_failure,
        "release_decision": release_decision,
        "related_but_distinct_harnesses": list(RELATED_BUT_DISTINCT),
        "stages": stage_records,
        "notes": (
            "Batch 3 offline integration harness: execution-order and failure-propagation "
            "testing only. ENGINEERING_ONLY / SYNTHETIC_ONLY under existing project conventions. "
            "Workflow success is not scientific validity."
        ),
    }
    report = json_safe(content)
    report["report_sha256"] = sha256_hex({k: v for k, v in report.items() if k != "report_sha256"})
    # Finite serialization guard
    _ = dumps(report)
    return report


def write_report(report: Dict[str, Any], output_path: str) -> str:
    from pathlib import Path

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(report) + "\n", encoding="utf-8")
    return str(path)
