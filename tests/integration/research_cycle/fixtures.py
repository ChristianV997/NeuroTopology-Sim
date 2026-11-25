"""Deterministic fixture builders for the research-cycle file chain.

All fixtures are synthetic contract stand-ins. None are scientific evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .contracts import PIPELINE_CONTRACT, STAGE_ORDER, declared_version
from .inspector import stamp_checksum, write_document

CYCLE_ID = "rc-cycle-synthetic-001"
SOURCE_CHECKSUM = "a" * 64
HYPOTHESIS_ID = "hyp_fc_synthetic_001"
PLAN_ID = "plan_synthetic_001"
RUN_ID = "run_synthetic_001"
ARTIFACT_ID = "artifact_synthetic_001"
VALIDATION_ID = "validation_synthetic_001"
GRAPH_ID = "egraph_synthetic_001"
RELEASE_ID = "release_synthetic_001"
PLAN_AUDIT_ID = "plan_audit_synthetic_001"
LIT_ID = "lit_src_synthetic_001"

CLAIM_SCOPE = (
    "Synthetic fixture chain for contract interoperability only. "
    "Not empirical evidence, not formal Bayes, not a scientific PASS."
)


def _envelope(
    *,
    stage: str,
    record_id: str,
    parent_ids: list[str],
    parent_checksums: list[str],
    data_mode: str,
    evidence_class: str,
    status: str,
    payload: dict[str, Any],
    diagnostics: dict[str, list[str]] | None = None,
    scientific_verdict: Any = "NOT_APPLICABLE",
    schema_version: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": schema_version or declared_version(stage),
        "pipeline_contract": PIPELINE_CONTRACT,
        "stage": stage,
        "record_id": record_id,
        "parent_ids": list(parent_ids),
        "parent_checksums": list(parent_checksums),
        "data_mode": data_mode,
        "evidence_class": evidence_class,
        "claim_scope": CLAIM_SCOPE,
        "status": status,
        "scientific_verdict": scientific_verdict,
        "diagnostics": diagnostics or {"missing": [], "errors": [], "duplicates": []},
        "payload": payload,
        "cycle_id": CYCLE_ID,
    }
    if extra:
        document.update(extra)
    return stamp_checksum(document)


def literature_payload(*, origin: str = "synthetic_demo") -> dict[str, Any]:
    return {
        "schema": "NeuroTopologySim.EmpiricalSourceManifest.v1",
        "dataset_identifier": "synthetic-fixture-cohort-001",
        "source_url": "https://example.invalid/local-only",
        "local_root": "fixtures/synthetic-source",
        "subject_identifiers": [f"sub-{index:02d}" for index in range(1, 9)],
        "condition_labels": ["condition_a", "condition_b"],
        "pairing_key": "subject_id",
        "expected_sampling_rate_hz": {"min": 200.0, "max": 1000.0},
        "channel_count_range": {"min": 8, "max": 64},
        "montage_requirement": "operator_supplied_10-20",
        "minimum_paired_subject_count": 8,
        "exclusion_rules": ["exclude incomplete pairs"],
        "primary_outcome_metrics": ["paired_condition_difference"],
        "secondary_outcomes": ["channel_count_completeness"],
        "null_models": ["label_permutation"],
        "multiplicity_correction": "holm",
        "stopping_rule": "fixed_n_equals_minimum_paired_subject_count",
        "missing_data_rule": "exclude_incomplete_pairs",
        "synthetic_data_policy": {
            "policy": "synthetic_never_empirical",
            "treat_as_empirical": False,
        },
        "provenance_requirements": {
            "checksum": "required",
            "origin_label": "required",
            "no_filename_condition_inference": True,
        },
        "origin": origin,
        "source_checksum": SOURCE_CHECKSUM,
        "scientific_status": "preregistration_only",
        "evidence_claim_allowed": False,
    }


def hypothesis_payload(*, epistemic_label: str = "speculative_hypothesis") -> dict[str, Any]:
    hypothesis = {
        "schema_version": "HypothesisRecord.v1",
        "hypothesis_id": HYPOTHESIS_ID,
        "precise_claim": (
            "In this synthetic fixture, a declared topological contrast is "
            "operationalized for contract tests only."
        ),
        "construct_definitions": {"fixture_construct": "synthetic operational stand-in"},
        "operational_variables": {"x": "synthetic_condition", "y": "synthetic_metric"},
        "predicted_direction": "positive",
        "null_prediction": "no change under the synthetic null",
        "alternative_explanations": ["fixture noise", "label leakage"],
        "falsification_criterion": "observed direction opposite the prediction on held-out synthetic splits",
        "min_sample_size_or_power": {"n": 8, "alpha": 0.05, "power": 0.8},
        "preregistration_reference": "SYNTHETIC-PREREG-001",
        "data_requirements": ["synthetic-fixture-cohort-001"],
        "analysis_plan": "fixture-only inspection; no solver execution",
        "provenance": {
            "owner": "integration-test",
            "source_id": LIT_ID,
            "source_checksum": SOURCE_CHECKSUM,
        },
        "epistemic_label": epistemic_label,
        "status": "preregistered",
        "human_review_gate": {
            "passed": False,
            "reviewer": None,
            "timestamp": None,
            "review_notes": "",
        },
        "evidence_links": [],
        "contradictory_evidence_links": [],
        "revision_history": [],
        "unresolved_questions": ["synthetic fixtures cannot promote empirical claims"],
        "checksum": "",
    }
    plan = {
        "schema_version": "ExperimentPlan.v1",
        "plan_id": PLAN_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "domain": "null_and_surrogate",
        "design_type": "synthetic_surrogate_null",
        "variables": {"independent": "condition", "dependent": "synthetic_metric"},
        "target_sample_size": 8,
        "power_analysis": {"method": "declared_only", "n": 8},
        "analysis_protocol": "inspect contracts; do not run a solver",
        "surrogate_method": "phase_randomization",
        "data_source": "synthetic-fixture-cohort-001",
        "is_synthetic": True,
        "provenance": {"source_id": LIT_ID, "source_checksum": SOURCE_CHECKSUM},
        "checksum": "",
    }
    return {
        "schema_version": "ResearchCycleRegistry.v1",
        "registry_id": CYCLE_ID,
        "hypotheses": {HYPOTHESIS_ID: hypothesis},
        "plans": {PLAN_ID: plan},
        "predictions": {},
        "evidence": {},
        "revisions": [],
    }


def run_record_payload() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "run_id": RUN_ID,
        "run_kind": "hypothesis",
        "created_at": "2026-09-10T00:00:00+00:00",
        "elapsed_s": 0.01,
        "spec_id": "HYP-SYNTHETIC-001",
        "claim_type": "K",
        "layer": "Topology",
        "data_mode": "synthetic",
        "dataset_id": "synthetic-fixture-cohort-001",
        "verdict": None,
        "metrics": {"fixture_metric": 0.25},
        "artifacts": {
            "summary": "summary.json",
            "metrics": "metrics.json",
        },
        "source": "local synthetic fixture",
        "synthetic": True,
        "claim_scope": CLAIM_SCOPE,
        "input": {"seed": 7, "n_steps": 1},
        "dependencies": {"python": "3.x"},
    }


def artifact_payload(*, paths: list[str] | None = None, check_artifacts: bool = False) -> dict[str, Any]:
    entries = paths or ["summary.json", "metrics.json"]
    artifacts = [
        {
            "relative_path": path,
            "sha256": SOURCE_CHECKSUM,
            "size_bytes": 32,
        }
        for path in entries
    ]
    return {
        "schema": "NTS.IntegrationArtifactManifest.v1",
        "run_id": RUN_ID,
        "metadata": {"data_mode": "synthetic", "evidence_class": "synthetic_demo_only"},
        "artifacts": artifacts,
        "check_artifacts": check_artifacts,
    }


def validation_payload(*, verdict: str = "INCONCLUSIVE") -> dict[str, Any]:
    return {
        "schema_version": "NeuroTopologySim.ValidationReport.v1",
        "report_id": VALIDATION_ID,
        "run_id": RUN_ID,
        "artifact_manifest_id": ARTIFACT_ID,
        "validation_status": verdict,
        "checks": {
            "finite_json": True,
            "solver_executed": False,
            "network_accessed": False,
            "synthetic_not_promoted": True,
        },
        "claim_status": "synthetic",
        "data_mode": "synthetic",
        "source": "fixture",
        "scientific_limitations": [
            "Synthetic validation cannot become empirical evidence.",
            "Proxy K is not formal Bayes.",
        ],
    }


def evidence_graph_payload() -> dict[str, Any]:
    nodes = [
        {"id": LIT_ID, "stage": "literature_source_manifest", "data_mode": "synthetic"},
        {"id": PLAN_AUDIT_ID, "stage": "research_plan_audit", "data_mode": "synthetic"},
        {"id": HYPOTHESIS_ID, "stage": "hypothesis_experiment_manifest", "data_mode": "synthetic"},
        {"id": RUN_ID, "stage": "simulation_run_manifest", "data_mode": "synthetic"},
        {"id": ARTIFACT_ID, "stage": "artifact_manifest", "data_mode": "synthetic"},
        {"id": VALIDATION_ID, "stage": "validation_report", "data_mode": "synthetic"},
    ]
    edges = [
        {"source": PLAN_AUDIT_ID, "target": LIT_ID, "relationship": "audits"},
        {"source": HYPOTHESIS_ID, "target": PLAN_AUDIT_ID, "relationship": "preregisters"},
        {"source": RUN_ID, "target": HYPOTHESIS_ID, "relationship": "executes"},
        {"source": ARTIFACT_ID, "target": RUN_ID, "relationship": "indexes"},
        {"source": VALIDATION_ID, "target": ARTIFACT_ID, "relationship": "validates"},
    ]
    return {
        "schema_version": "NeuroTopologySim.ResearchCycleEvidenceGraph.v1",
        "graph_id": GRAPH_ID,
        "nodes": nodes,
        "edges": edges,
        "partial": False,
        "missing_nodes": [],
        "scientific_status": "not_evidence",
    }


def release_payload() -> dict[str, Any]:
    record = {
        "schema_version": "1.0",
        "benchmark_id": "research-cycle-fixture",
        "source_commit": "deadbeef",
        "branch": "main",
        "host": "fixture-host",
        "platform": "linux",
        "python_version": "3.12.3",
        "backend": "fixture",
        "input_shape": {"channels": 8, "samples": 128, "dtype": "float64"},
        "chunk_size": 32,
        "repetitions": 3,
        "checksum": 1.0,
        "correctness_status": "ok",
        "runtime_s": 0.01,
        "tracemalloc_peak_bytes": 1_000_000,
        "child_rss_bytes": None,
        "timeout_status": False,
        "process_exit_status": 0,
        "optional_dependency_state": None,
        "evidence_class": "performance_only",
        "synthetic": True,
        "raw_outcome": "not_scientific",
    }
    return {
        "schema_version": "1.0",
        "decision": "EVIDENCE_INCONCLUSIVE",
        "evidence_class": "performance_only",
        "synthetic": True,
        "comparable": True,
        "reason_codes": ["synthetic_performance_only"],
        "reasons": ["Synthetic fixtures are performance evidence only — never scientific evidence."],
        "baseline": record,
        "candidate": dict(record),
        "scientific_verdict": "NOT_APPLICABLE",
    }


def happy_chain() -> list[dict[str, Any]]:
    lit = _envelope(
        stage="literature_source_manifest",
        record_id=LIT_ID,
        parent_ids=[],
        parent_checksums=[],
        data_mode="synthetic",
        evidence_class="synthetic_demo_only",
        status="COMPLETE",
        payload=literature_payload(),
    )
    audit = _envelope(
        stage="research_plan_audit",
        record_id=PLAN_AUDIT_ID,
        parent_ids=[LIT_ID],
        parent_checksums=[lit["checksum"]],
        data_mode="synthetic",
        evidence_class="research_plan_audit",
        status="COMPLETE",
        payload={
            "plan_id": PLAN_ID,
            "overall_status": "READY_FOR_EXECUTION",
            "overall_score": 0.8,
            "evidence_class": "research_plan_audit",
            "hard_blockers": [],
            "missing_fields": [],
            "criteria": [
                {
                    "dimension": "falsifiable_question",
                    "status": "pass",
                    "detail": "question declared",
                    "score": 1.0,
                }
            ],
        },
    )
    hyp = _envelope(
        stage="hypothesis_experiment_manifest",
        record_id=HYPOTHESIS_ID,
        parent_ids=[PLAN_AUDIT_ID],
        parent_checksums=[audit["checksum"]],
        data_mode="synthetic",
        evidence_class="speculative_hypothesis",
        status="COMPLETE",
        payload=hypothesis_payload(),
    )
    run = _envelope(
        stage="simulation_run_manifest",
        record_id=RUN_ID,
        parent_ids=[HYPOTHESIS_ID],
        parent_checksums=[hyp["checksum"]],
        data_mode="synthetic",
        evidence_class="synthetic_demo_only",
        status="COMPLETE",
        payload=run_record_payload(),
    )
    artifacts = _envelope(
        stage="artifact_manifest",
        record_id=ARTIFACT_ID,
        parent_ids=[RUN_ID],
        parent_checksums=[run["checksum"]],
        data_mode="synthetic",
        evidence_class="synthetic_demo_only",
        status="COMPLETE",
        payload=artifact_payload(),
    )
    validation = _envelope(
        stage="validation_report",
        record_id=VALIDATION_ID,
        parent_ids=[ARTIFACT_ID],
        parent_checksums=[artifacts["checksum"]],
        data_mode="synthetic",
        evidence_class="synthetic_demo_only",
        status="COMPLETE",
        scientific_verdict="INCONCLUSIVE",
        payload=validation_payload(),
    )
    graph = _envelope(
        stage="evidence_graph",
        record_id=GRAPH_ID,
        parent_ids=[VALIDATION_ID],
        parent_checksums=[validation["checksum"]],
        data_mode="synthetic",
        evidence_class="synthetic_demo_only",
        status="COMPLETE",
        payload=evidence_graph_payload(),
    )
    release = _envelope(
        stage="release_evidence_report",
        record_id=RELEASE_ID,
        parent_ids=[GRAPH_ID],
        parent_checksums=[graph["checksum"]],
        data_mode="synthetic",
        evidence_class="performance_only",
        status="COMPLETE",
        scientific_verdict="NOT_APPLICABLE",
        payload=release_payload(),
    )
    return [lit, audit, hyp, run, artifacts, validation, graph, release]


def write_chain(directory: str | Path, documents: list[dict[str, Any]]) -> list[Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, document in enumerate(documents, start=1):
        stage = document["stage"]
        filename = f"{index:02d}_{stage}.json"
        written.append(write_document(root / filename, document))
    return written


def write_happy_chain(directory: str | Path) -> list[Path]:
    return write_chain(directory, happy_chain())


def failed_simulation_chain() -> list[dict[str, Any]]:
    docs = happy_chain()
    run = dict(docs[3])
    run["status"] = "FAILED"
    run["diagnostics"] = {
        "missing": [],
        "errors": ["solver marker present in fixture only; run did not execute"],
        "duplicates": [],
        "upstream_failures": [],
    }
    run["payload"] = dict(run["payload"])
    run["payload"]["verdict"] = None
    run["payload"]["run_status"] = "failed"
    run = stamp_checksum(run)
    docs[3] = run

    def _relink(index: int, parent: dict[str, Any], *, status: str) -> dict[str, Any]:
        child = dict(docs[index])
        child["status"] = status
        child["parent_checksums"] = [parent["checksum"]]
        child["diagnostics"] = {
            "missing": [],
            "errors": [],
            "duplicates": [],
            "upstream_failures": [f"{parent['record_id']}:{parent['status']}"],
        }
        child["scientific_verdict"] = "BLOCKED"
        return stamp_checksum(child)

    docs[4] = _relink(4, run, status="FAILED")
    docs[5] = _relink(5, docs[4], status="BLOCKED")
    docs[6] = _relink(6, docs[5], status="BLOCKED")
    docs[7] = _relink(7, docs[6], status="BLOCKED")
    return docs


def partial_chain() -> list[dict[str, Any]]:
    docs = happy_chain()
    artifacts = dict(docs[4])
    artifacts["status"] = "PARTIAL"
    artifacts["diagnostics"] = {
        "missing": ["metrics.json"],
        "errors": [],
        "duplicates": [],
        "upstream_failures": [],
    }
    artifacts["payload"] = artifact_payload(paths=["summary.json"], check_artifacts=False)
    artifacts["payload"]["missing_artifacts"] = ["metrics.json"]
    artifacts = stamp_checksum(artifacts)
    docs[4] = artifacts

    def _relink(index: int, parent: dict[str, Any]) -> dict[str, Any]:
        child = dict(docs[index])
        child["status"] = "PARTIAL"
        child["parent_checksums"] = [parent["checksum"]]
        child["diagnostics"] = {
            "missing": ["metrics.json"],
            "errors": [],
            "duplicates": [],
            "upstream_failures": [f"{parent['record_id']}:PARTIAL"],
        }
        child["scientific_verdict"] = "INCONCLUSIVE"
        return stamp_checksum(child)

    docs[5] = _relink(5, artifacts)
    docs[6] = _relink(6, docs[5])
    docs[7] = _relink(7, docs[6])
    return docs


STAGE_FILENAMES = {
    stage: f"{index:02d}_{stage}.json" for index, stage in enumerate(STAGE_ORDER, start=1)
}
