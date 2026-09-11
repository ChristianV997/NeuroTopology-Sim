"""Declared research-cycle file contracts for black-box integration tests.

Schema identifiers below are taken from origin/main producers when they exist.
When a Batch 1 producer is still only on an open PR, the identifier is the
declared contract that fixtures stand in for. Tests never invent production
modules.
"""
from __future__ import annotations

from typing import Any, Mapping

PIPELINE_CONTRACT = "NeuroTopologySim.ResearchCyclePipeline.v1"
PIPELINE_COMPATIBLE = frozenset({PIPELINE_CONTRACT})

# Ordered file/contract chain under test.
STAGE_ORDER: tuple[str, ...] = (
    "literature_source_manifest",
    "research_plan_audit",
    "hypothesis_experiment_manifest",
    "simulation_run_manifest",
    "artifact_manifest",
    "validation_report",
    "evidence_graph",
    "release_evidence_report",
)

# Producer status: ON_MAIN = importable from origin/main; PENDING = fixture-only.
ON_MAIN = "ON_MAIN"
PENDING = "PENDING"

STAGE_CONTRACTS: dict[str, dict[str, Any]] = {
    "literature_source_manifest": {
        "schema_version": "NeuroTopologySim.EmpiricalSourceManifest.v1",
        "compatible": frozenset({"NeuroTopologySim.EmpiricalSourceManifest.v1"}),
        "status": ON_MAIN,
        "producer": "configs.empirical_sources.manifest",
        "open_pr": None,
        "notes": (
            "On main as a preregistration/source identity contract. "
            "A completed template is not empirical evidence."
        ),
    },
    "research_plan_audit": {
        "schema_version": "NeuroTopologySim.ResearchPlanAudit.v1",
        "compatible": frozenset({"NeuroTopologySim.ResearchPlanAudit.v1"}),
        "status": PENDING,
        "producer": "tools.research_plan_quality (PR #302)",
        "open_pr": 302,
        "notes": (
            "PR #302 PlanAuditResult currently has evidence_class="
            "research_plan_audit but no schema_version field. The envelope "
            "schema_version is the declared integration contract."
        ),
    },
    "hypothesis_experiment_manifest": {
        "schema_version": "ResearchCycleRegistry.v1",
        "compatible": frozenset({"ResearchCycleRegistry.v1"}),
        "status": ON_MAIN,
        "producer": "tools.research_cycle",
        "open_pr": None,
        "payload_schemas": (
            "HypothesisRecord.v1",
            "ExperimentPlan.v1",
            "PredictionRecord.v1",
            "EvidenceUpdate.v1",
            "TheoryRevision.v1",
        ),
        "notes": "On main. Nested records each declare their own schema_version.",
    },
    "simulation_run_manifest": {
        "schema_version": "NeuroTopologySim.SimulationRunManifest.v1",
        "compatible": frozenset({"NeuroTopologySim.SimulationRunManifest.v1"}),
        "status": ON_MAIN,
        "producer": "runs.run_record.RunRecordV1 (payload schema_version 0.1 / 1)",
        "open_pr": 304,
        "notes": (
            "RunRecordV1 is on main. PR #304 adds SimulationArtifactLineage.v1 "
            "as a read-only lineage extractor; not on main yet."
        ),
    },
    "artifact_manifest": {
        "schema_version": "NTS.IntegrationArtifactManifest.v1",
        "compatible": frozenset(
            {
                "NTS.IntegrationArtifactManifest.v1",
                "NeuroTopologySim.SimulationArtifactLineage.v1",
            }
        ),
        "status": ON_MAIN,
        "producer": "tools.integration_bridge.artifact_manifest",
        "open_pr": 304,
        "notes": (
            "Integration artifact manifest is on main. Lineage extractor "
            "schema is declared by PR #304 and accepted as a compatible alias."
        ),
    },
    "validation_report": {
        "schema_version": "NeuroTopologySim.ValidationReport.v1",
        "compatible": frozenset(
            {
                "NeuroTopologySim.ValidationReport.v1",
                "awareness-studio-research-cycle.v1",
            }
        ),
        "status": PENDING,
        "producer": "apps/awareness_studio research-cycle ledger (PR #305)",
        "open_pr": 305,
        "notes": (
            "No standalone validation-report producer on main. PR #305 declares "
            "ValidationReport under awareness-studio-research-cycle.v1."
        ),
    },
    "evidence_graph": {
        "schema_version": "NeuroTopologySim.ResearchCycleEvidenceGraph.v1",
        "compatible": frozenset({"NeuroTopologySim.ResearchCycleEvidenceGraph.v1"}),
        "status": PENDING,
        "producer": None,
        "open_pr": None,
        "notes": (
            "No research-cycle evidence-graph producer on origin/main. "
            "tools/research_record/graph.py and tools/research_report/graph.py "
            "are PR-stacking graphs, not this pipeline stage."
        ),
    },
    "release_evidence_report": {
        "schema_version": "1.0",
        "compatible": frozenset({"1.0"}),
        "status": ON_MAIN,
        "producer": "tools.performance.release_evidence_gate",
        "open_pr": None,
        "notes": (
            "GATE_SCHEMA_VERSION=1.0 on main. Performance evidence only; "
            "timeouts never map to scientific PASS."
        ),
    },
}

STATUSES = frozenset(
    {
        "COMPLETE",
        "PARTIAL",
        "FAILED",
        "BLOCKED",
        "INCOMPLETE",
        "PENDING",
        "CONFLICTING",
    }
)

# Terminal engineering completeness that may not be claimed after a failed/partial upstream.
COMPLETE_STATUSES = frozenset({"COMPLETE"})

DATA_MODES = frozenset({"synthetic", "proxy", "empirical", "unknown"})

# Labels that must never be silently rewritten by a consumer.
PRESERVED_LABEL_FIELDS = (
    "data_mode",
    "evidence_class",
    "claim_scope",
    "origin",
    "epistemic_label",
)

EVIDENCE_CLASSES = frozenset(
    {
        "synthetic_demo_only",
        "research_plan_audit",
        "speculative_hypothesis",
        "computational_model",
        "surrogate_baseline",
        "preregistered_empirical",
        "performance_only",
        "proxy_inference",
        "literature_claim",
        "unknown",
    }
)

SCIENTIFIC_VERDICTS = frozenset(
    {
        None,
        "NOT_APPLICABLE",
        "BLOCKED",
        "INCONCLUSIVE",
        "PENDING_HUMAN_REVIEW",
    }
)

# Synthetic/proxy fixtures must never emit scientific PASS.
FORBIDDEN_SCIENTIFIC_PASS = frozenset({"PASS", "SUPPORTED", "CONFIRMED", "PROVEN"})

INVALID_PROMOTIONS = (
    # (from_data_mode, from_class, to_data_mode or to_class or verdict)
    ("synthetic", "empirical"),
    ("proxy", "empirical"),
    ("proxy", "formal_bayes"),
)

REQUIRED_ENVELOPE_FIELDS = (
    "schema_version",
    "pipeline_contract",
    "stage",
    "record_id",
    "checksum",
    "parent_ids",
    "parent_checksums",
    "data_mode",
    "evidence_class",
    "claim_scope",
    "status",
    "payload",
)

MISSING_PREREQUISITES: tuple[dict[str, Any], ...] = (
    {
        "component": "tools.research_plan_quality",
        "stage": "research_plan_audit",
        "pr": 302,
        "branch": "claude/research-plan-quality-rubric-20260910",
        "reason": "Research-plan rubric evaluator is not on origin/main.",
    },
    {
        "component": "tools.simulation_artifacts",
        "stage": "simulation_run_manifest / artifact_manifest",
        "pr": 304,
        "branch": "codex/simulation-artifact-lineage-20260910",
        "reason": "Simulation artifact lineage extractor is not on origin/main.",
    },
    {
        "component": "awareness_studio.research_cycle",
        "stage": "validation_report / hypothesis-experiment ledger",
        "pr": 305,
        "branch": "codex/research-cycle-ledger-20260910",
        "reason": "Immutable Awareness Studio research-cycle ledger is not on origin/main.",
    },
    {
        "component": "research-cycle evidence graph producer",
        "stage": "evidence_graph",
        "pr": None,
        "branch": None,
        "reason": "No file-chain evidence-graph producer exists on origin/main.",
    },
)


def compatible_versions(stage: str) -> frozenset[str]:
    return STAGE_CONTRACTS[stage]["compatible"]


def declared_version(stage: str) -> str:
    return str(STAGE_CONTRACTS[stage]["schema_version"])


def version_is_compatible(stage: str, schema_version: str | None) -> bool:
    if not schema_version:
        return False
    return schema_version in compatible_versions(stage)


def parent_stage(stage: str) -> str | None:
    idx = STAGE_ORDER.index(stage)
    if idx == 0:
        return None
    return STAGE_ORDER[idx - 1]


def is_scientific_pass(verdict: Any) -> bool:
    if verdict is None:
        return False
    text = str(verdict).strip().upper()
    return text in FORBIDDEN_SCIENTIFIC_PASS


def envelope_field_errors(document: Mapping[str, Any]) -> list[str]:
    errors = []
    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in document:
            errors.append(f"missing envelope field {field!r}")
    return errors
