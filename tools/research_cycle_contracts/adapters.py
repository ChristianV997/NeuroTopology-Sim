"""Bidirectional adapters between Hypothesis Registry models, Awareness Studio, and Experiment Ledger.

Translates between schemas while preserving all 10 essential fields:
1. Hypothesis ID
2. Source IDs
3. Dataset IDs
4. Falsification criteria
5. Null predictions
6. Evidence class
7. Reviewer state / human review gates
8. Status transitions
9. Contradiction records
10. Integrity checksums
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from .models import (
    AwarenessHypothesisNodeV1,
    AwarenessStudioCycleInputV1,
    EvidenceUpdateV1,
    ExperimentLedgerRowV1,
    ExperimentPlanV1,
    HypothesisRecordV1,
    MigrationWarning,
    PredictionRecordV1,
    SupportedFeatureFamily,
    _safe_dict,
)
from .rejection import (
    ContractRejectionError,
    validate_evidence_contract,
    validate_hypothesis_contract,
    validate_ledger_row_contract,
)
from .version_negotiator import negotiate_contract_version


def _compute_sha256(data: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 digest of dict excluding existing checksum."""
    payload = {k: v for k, v in data.items() if k != "checksum"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hypothesis_to_awareness_node(
    hypothesis: HypothesisRecordV1 | dict[str, Any],
    *,
    target_version: str = "AwarenessHypothesisNode.v1",
    validate: bool = True,
) -> tuple[AwarenessHypothesisNodeV1, list[MigrationWarning]]:
    """Convert a HypothesisRecordV1 to an AwarenessHypothesisNodeV1.

    Guarantees retention of ID, provenance sources, datasets, falsification,
    null predictions, evidence class, review gates, and contradiction links.
    """
    if isinstance(hypothesis, dict):
        # Instantiate model from dict
        hypo = HypothesisRecordV1(
            hypothesis_id=hypothesis["hypothesis_id"],
            precise_claim=hypothesis.get("precise_claim", hypothesis.get("statement", "")),
            construct_definitions=hypothesis.get("construct_definitions", {}),
            operational_variables=hypothesis.get("operational_variables", {}),
            predicted_direction=hypothesis.get("predicted_direction", ""),
            null_prediction=hypothesis.get("null_prediction", ""),
            alternative_explanations=hypothesis.get("alternative_explanations", []),
            falsification_criterion=hypothesis.get("falsification_criterion", ""),
            min_sample_size_or_power=hypothesis.get("min_sample_size_or_power", {}),
            preregistration_reference=hypothesis.get("preregistration_reference"),
            data_requirements=hypothesis.get("data_requirements", []),
            analysis_plan=hypothesis.get("analysis_plan", ""),
            provenance=hypothesis.get("provenance", {}),
            feature_family=hypothesis.get("feature_family", SupportedFeatureFamily.TOPOLOGICAL_HOMOLOGY.value),
            dataset_ids=hypothesis.get("dataset_ids", []),
            epistemic_label=hypothesis.get("epistemic_label", "speculative_hypothesis"),
            status=hypothesis.get("status", "proposed"),
            evidence_class=hypothesis.get("evidence_class", "descriptive_or_paired_statistics"),
            schema_version=hypothesis.get("schema_version", "HypothesisRecord.v1"),
            human_review_gate=hypothesis.get("human_review_gate", {"passed": False, "reviewer": None, "timestamp": None, "notes": ""}),
            evidence_links=hypothesis.get("evidence_links", []),
            contradictory_evidence_links=hypothesis.get("contradictory_evidence_links", []),
            revision_history=hypothesis.get("revision_history", []),
            unresolved_questions=hypothesis.get("unresolved_questions", []),
            checksum=hypothesis.get("checksum", ""),
        )
    else:
        hypo = hypothesis

    if validate:
        validate_hypothesis_contract(hypo)

    negotiated_version, warnings = negotiate_contract_version(
        hypo.schema_version, target_version, schema_name="HypothesisRecord"
    )

    # Extract source IDs from provenance
    source_ids = list(hypo.provenance.get("source_ids", []))
    if not source_ids:
        single_src = hypo.provenance.get("source_id") or hypo.provenance.get("creator")
        if single_src:
            source_ids = [str(single_src)]

    # Map human review gate
    gate = hypo.human_review_gate or {}
    human_reviewer = gate.get("reviewer")
    human_review_passed = bool(gate.get("passed", False))

    node = AwarenessHypothesisNodeV1(
        node_id=hypo.hypothesis_id,
        label=hypo.precise_claim,
        construct=json.dumps(hypo.construct_definitions, sort_keys=True),
        operationalization=hypo.operational_variables,
        feature_family=hypo.feature_family,
        null_prediction=hypo.null_prediction,
        falsification_criteria=hypo.falsification_criterion,
        status=hypo.status,
        evidence_class=hypo.evidence_class,
        human_reviewer=human_reviewer,
        human_review_passed=human_review_passed,
        source_ids=source_ids,
        dataset_ids=list(hypo.dataset_ids),
        evidence_ids=list(hypo.evidence_links),
        contradictions=list(hypo.contradictory_evidence_links),
        schema_version="AwarenessHypothesisNode.v1",
    )
    node.checksum = _compute_sha256(node.to_dict())
    return node, warnings


def awareness_node_to_hypothesis(
    node: AwarenessHypothesisNodeV1 | dict[str, Any],
    *,
    target_version: str = "HypothesisRecord.v1",
    validate: bool = True,
) -> tuple[HypothesisRecordV1, list[MigrationWarning]]:
    """Convert an AwarenessHypothesisNodeV1 back to a HypothesisRecordV1 with full fidelity."""
    if isinstance(node, dict):
        node_obj = AwarenessHypothesisNodeV1(
            node_id=node["node_id"],
            label=node.get("label", ""),
            construct=node.get("construct", ""),
            operationalization=node.get("operationalization", {}),
            feature_family=node.get("feature_family", SupportedFeatureFamily.TOPOLOGICAL_HOMOLOGY.value),
            null_prediction=node.get("null_prediction", ""),
            falsification_criteria=node.get("falsification_criteria", ""),
            status=node.get("status", "proposed"),
            evidence_class=node.get("evidence_class", "descriptive_or_paired_statistics"),
            human_reviewer=node.get("human_reviewer"),
            human_review_passed=node.get("human_review_passed", False),
            source_ids=node.get("source_ids", []),
            dataset_ids=node.get("dataset_ids", []),
            evidence_ids=node.get("evidence_ids", []),
            contradictions=node.get("contradictions", []),
            schema_version=node.get("schema_version", "AwarenessHypothesisNode.v1"),
            checksum=node.get("checksum", ""),
        )
    else:
        node_obj = node

    negotiated_version, warnings = negotiate_contract_version(
        node_obj.schema_version, target_version, schema_name=None
    )

    # Reconstitute construct definitions
    try:
        construct_defs = json.loads(node_obj.construct) if node_obj.construct else {}
        if not isinstance(construct_defs, dict):
            construct_defs = {"raw_construct": str(node_obj.construct)}
    except (json.JSONDecodeError, TypeError):
        construct_defs = {"raw_construct": str(node_obj.construct)}

    # Provenance reconstruction
    prov: dict[str, Any] = {
        "source_ids": list(node_obj.source_ids),
        "source_id": node_obj.source_ids[0] if node_obj.source_ids else "unknown_source",
        "adapted_from": "AwarenessHypothesisNode.v1",
    }

    gate = {
        "passed": node_obj.human_review_passed,
        "reviewer": node_obj.human_reviewer,
        "timestamp": None,
        "notes": "Reconstituted from Awareness Studio node.",
    }

    hypo = HypothesisRecordV1(
        hypothesis_id=node_obj.node_id,
        precise_claim=node_obj.label,
        construct_definitions=construct_defs,
        operational_variables={str(k): str(v) for k, v in node_obj.operationalization.items()},
        predicted_direction="positive",
        null_prediction=node_obj.null_prediction,
        alternative_explanations=[],
        falsification_criterion=node_obj.falsification_criteria,
        min_sample_size_or_power={},
        preregistration_reference=None,
        data_requirements=[],
        dataset_ids=list(node_obj.dataset_ids),
        analysis_plan="",
        provenance=prov,
        feature_family=node_obj.feature_family,
        status=node_obj.status,
        evidence_class=node_obj.evidence_class,
        human_review_gate=gate,
        evidence_links=list(node_obj.evidence_ids),
        contradictory_evidence_links=list(node_obj.contradictions),
        schema_version="HypothesisRecord.v1",
    )
    hypo.checksum = _compute_sha256(hypo.to_dict())

    if validate:
        validate_hypothesis_contract(hypo)

    return hypo, warnings


def plan_and_evidence_to_ledger_row(
    plan: ExperimentPlanV1,
    evidence: EvidenceUpdateV1,
    hypothesis: HypothesisRecordV1 | None = None,
    *,
    validate: bool = True,
) -> tuple[ExperimentLedgerRowV1, list[MigrationWarning]]:
    """Convert an experiment plan and evidence update into an ExperimentLedgerRowV1."""
    if validate:
        validate_evidence_contract(evidence)

    warnings: list[MigrationWarning] = []

    row_id = f"row-{plan.plan_id}-{evidence.evidence_id}"
    feature_fam = (
        hypothesis.feature_family
        if hypothesis
        else SupportedFeatureFamily.TOPOLOGICAL_HOMOLOGY.value
    )
    falsif_crit = (
        hypothesis.falsification_criterion
        if hypothesis
        else plan.variables.get("falsification_threshold", "none")
    )
    null_pred = hypothesis.null_prediction if hypothesis else "null_expected"

    reviewer_signoff = None
    if hypothesis and hypothesis.human_review_gate and hypothesis.human_review_gate.get("passed"):
        reviewer_signoff = str(hypothesis.human_review_gate.get("reviewer"))

    row = ExperimentLedgerRowV1(
        row_id=row_id,
        experiment_id=plan.plan_id,
        hypothesis_id=plan.hypothesis_id,
        plan_id=plan.plan_id,
        dataset_id=evidence.dataset_ids[0] if evidence.dataset_ids else plan.dataset_id,
        source_id=evidence.source_ids[0] if evidence.source_ids else "unknown_source",
        feature_family=feature_fam,
        is_synthetic=evidence.is_synthetic,
        falsification_threshold=str(falsif_crit),
        null_prediction=null_pred,
        observed_effect=evidence.observed_effect_size,
        observed_p=evidence.observed_p_value,
        outcome_status="contradicted" if evidence.is_contradictory else "observed",
        is_contradictory=evidence.is_contradictory,
        contradiction_reason=evidence.contradiction_details,
        reviewer_signoff=reviewer_signoff,
        evidence_checksum=evidence.checksum or evidence.experiment_checksum,
        provenance_tag=f"plan:{plan.checksum[:8]}_ev:{evidence.checksum[:8] if evidence.checksum else 'raw'}",
        schema_version="ExperimentLedgerRow.v1",
    )
    row.checksum = _compute_sha256(row.to_dict())

    if validate:
        validate_ledger_row_contract(row)

    return row, warnings


def ledger_row_to_evidence(
    row: ExperimentLedgerRowV1 | dict[str, Any],
    *,
    validate: bool = True,
) -> tuple[EvidenceUpdateV1, list[MigrationWarning]]:
    """Convert an ExperimentLedgerRowV1 back to an EvidenceUpdateV1."""
    if isinstance(row, dict):
        row_obj = ExperimentLedgerRowV1(**row)
    else:
        row_obj = row

    if validate:
        validate_ledger_row_contract(row_obj)

    warnings: list[MigrationWarning] = []

    ev = EvidenceUpdateV1(
        evidence_id=f"ev-from-{row_obj.row_id}",
        hypothesis_id=row_obj.hypothesis_id,
        experiment_id=row_obj.experiment_id,
        source_ids=[row_obj.source_id] if row_obj.source_id else [],
        dataset_ids=[row_obj.dataset_id] if row_obj.dataset_id else [],
        source_checksum="derived_from_ledger",
        experiment_checksum=row_obj.evidence_checksum,
        data_type="synthetic_simulation" if row_obj.is_synthetic else "empirical_dataset",
        is_synthetic=row_obj.is_synthetic,
        is_out_of_sample=not row_obj.is_synthetic,
        metrics_observed={
            "observed_effect": row_obj.observed_effect,
            "observed_p": row_obj.observed_p,
        },
        observed_effect_size=row_obj.observed_effect,
        observed_p_value=row_obj.observed_p,
        is_contradictory=row_obj.is_contradictory,
        contradiction_details=row_obj.contradiction_reason,
        provenance={"provenance_tag": row_obj.provenance_tag, "derived_from": row_obj.row_id},
        schema_version="EvidenceUpdate.v1",
    )
    ev.checksum = _compute_sha256(ev.to_dict())

    if validate:
        validate_evidence_contract(ev)

    return ev, warnings


def registry_bundle_to_cycle_input(
    hypotheses: Sequence[HypothesisRecordV1],
    plans: Sequence[ExperimentPlanV1] = (),
    evidence_list: Sequence[EvidenceUpdateV1] = (),
    cycle_id: str = "cycle-001",
    *,
    validate: bool = True,
) -> tuple[AwarenessStudioCycleInputV1, list[MigrationWarning]]:
    """Aggregate registry records into an AwarenessStudioCycleInputV1 artifact."""
    all_warnings: list[MigrationWarning] = []
    nodes: list[AwarenessHypothesisNodeV1] = []

    for h in hypotheses:
        node, warnings = hypothesis_to_awareness_node(h, validate=validate)
        nodes.append(node)
        all_warnings.extend(warnings)

    plans_dict = [p.to_dict() for p in plans]
    evidence_dict = [e.to_dict() for e in evidence_list]

    cycle_input = AwarenessStudioCycleInputV1(
        cycle_id=cycle_id,
        contract_version="AwarenessStudioCycleInput.v1",
        nodes=nodes,
        plans=plans_dict,
        evidence=evidence_dict,
        metadata={"total_hypotheses": len(nodes), "total_plans": len(plans)},
        schema_version="AwarenessStudioCycleInput.v1",
    )
    cycle_input.checksum = _compute_sha256(cycle_input.to_dict())
    return cycle_input, all_warnings


def cycle_input_to_registry_bundle(
    cycle_input: AwarenessStudioCycleInputV1 | dict[str, Any],
    *,
    validate: bool = True,
) -> tuple[list[HypothesisRecordV1], list[ExperimentPlanV1], list[EvidenceUpdateV1], list[MigrationWarning]]:
    """Unpack an AwarenessStudioCycleInputV1 into registry hypothesis, plan, and evidence records."""
    if isinstance(cycle_input, dict):
        inp = AwarenessStudioCycleInputV1(
            cycle_id=cycle_input["cycle_id"],
            contract_version=cycle_input.get("contract_version", "AwarenessStudioCycleInput.v1"),
            nodes=[
                n if isinstance(n, AwarenessHypothesisNodeV1) else AwarenessHypothesisNodeV1(**n)
                for n in cycle_input.get("nodes", [])
            ],
            plans=cycle_input.get("plans", []),
            evidence=cycle_input.get("evidence", []),
            metadata=cycle_input.get("metadata", {}),
            checksum=cycle_input.get("checksum", ""),
        )
    else:
        inp = cycle_input

    all_warnings: list[MigrationWarning] = []
    hypotheses: list[HypothesisRecordV1] = []

    for node in inp.nodes:
        h, warnings = awareness_node_to_hypothesis(node, validate=validate)
        hypotheses.append(h)
        all_warnings.extend(warnings)

    plans: list[ExperimentPlanV1] = []
    for p_dict in inp.plans:
        p = ExperimentPlanV1(
            plan_id=p_dict["plan_id"],
            hypothesis_id=p_dict["hypothesis_id"],
            domain=p_dict.get("domain", "higher_order_spectra"),
            design_type=p_dict.get("design_type", "paired_cohort"),
            variables=p_dict.get("variables", {}),
            target_sample_size=p_dict.get("target_sample_size", 30),
            power_analysis=p_dict.get("power_analysis", {}),
            analysis_protocol=p_dict.get("analysis_protocol", "standard"),
            surrogate_method=p_dict.get("surrogate_method"),
            data_source=p_dict.get("data_source", ""),
            dataset_id=p_dict.get("dataset_id", ""),
            is_synthetic=p_dict.get("is_synthetic", False),
            provenance=p_dict.get("provenance", {}),
            checksum=p_dict.get("checksum", ""),
        )
        if not p.checksum:
            p.checksum = _compute_sha256(p.to_dict())
        plans.append(p)

    evidence_list: list[EvidenceUpdateV1] = []
    for e_dict in inp.evidence:
        ev = EvidenceUpdateV1(
            evidence_id=e_dict["evidence_id"],
            hypothesis_id=e_dict["hypothesis_id"],
            experiment_id=e_dict["experiment_id"],
            source_ids=e_dict.get("source_ids", []),
            dataset_ids=e_dict.get("dataset_ids", []),
            source_checksum=e_dict.get("source_checksum", ""),
            experiment_checksum=e_dict.get("experiment_checksum", ""),
            data_type=e_dict.get("data_type", "empirical_dataset"),
            is_synthetic=e_dict.get("is_synthetic", False),
            is_out_of_sample=e_dict.get("is_out_of_sample", True),
            metrics_observed=e_dict.get("metrics_observed", {}),
            observed_effect_size=e_dict.get("observed_effect_size"),
            observed_p_value=e_dict.get("observed_p_value"),
            is_contradictory=e_dict.get("is_contradictory", False),
            contradiction_details=e_dict.get("contradiction_details"),
            provenance=e_dict.get("provenance", {}),
            notes=e_dict.get("notes", ""),
            checksum=e_dict.get("checksum", ""),
        )
        if not ev.checksum:
            ev.checksum = _compute_sha256(ev.to_dict())
        if validate:
            validate_evidence_contract(ev)
        evidence_list.append(ev)

    return hypotheses, plans, evidence_list, all_warnings
