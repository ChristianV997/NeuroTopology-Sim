"""The artifact ledger (requirement 5): one row per experiment, tying its
hypothesis, its source literature, its execution provenance, and its
current scientific/reviewer status together for audit.
"""
from __future__ import annotations

from typing import Any

from tools.awareness_studio_research_loop.guardrails import evidence_class_for_execution


def build_artifact_ledger(
    *,
    plans: list[dict[str, Any]],
    executions_by_experiment: dict[str, dict[str, Any]],
    null_tests_by_experiment: dict[str, dict[str, Any]],
    hypotheses_by_id: dict[str, dict[str, Any]],
    claims_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
    reviewer_decisions_by_subject: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for plan in plans:
        experiment_id = plan["experiment_id"]
        execution = executions_by_experiment.get(experiment_id)
        null_test = null_tests_by_experiment.get(experiment_id)
        hypothesis = hypotheses_by_id.get(plan["hypothesis_id"]) if plan["hypothesis_id"] else None

        source_checksum = None
        if hypothesis is not None:
            for claim_id in hypothesis["claim_ids"]:
                claim = claims_by_id.get(claim_id)
                if claim is None:
                    continue
                source = sources_by_id.get(claim["source_id"])
                if source is not None and source["source_checksum"]:
                    source_checksum = source["source_checksum"]
                    break

        data_mode = execution["data_mode"] if execution is not None else ("synthetic" if plan["synthetic"] else "unknown")
        is_formal = bool(
            execution is not None
            and data_mode == "empirical"
            and null_test is not None
            and null_test["verdict"] in ("PASS", "FAIL")
            and plan["preregistered"]
            and plan["held_out_split_locked"] is True
        )

        reviewer_decision = reviewer_decisions_by_subject.get(("experiment", experiment_id)) or (
            reviewer_decisions_by_subject.get(("hypothesis", plan["hypothesis_id"])) if plan["hypothesis_id"] else None
        )

        rows.append(
            {
                "experiment_id": experiment_id,
                "hypothesis_id": plan["hypothesis_id"],
                "source_checksum": source_checksum,
                "input_checksums": execution["input_checksums"] if execution else [],
                "output_checksums": execution["output_checksums"] if execution else [],
                "software_commit": execution["software_commit"] if execution else None,
                "runtime_seconds": execution["runtime_seconds"] if execution else None,
                "dependency_state": execution["dependency_state"] if execution else "unknown",
                "scientific_status": evidence_class_for_execution(data_mode=data_mode, is_formal=is_formal),
                "reviewer_status": reviewer_decision["decision"] if reviewer_decision else "pending",
            }
        )
    rows.sort(key=lambda r: r["experiment_id"])
    return rows
