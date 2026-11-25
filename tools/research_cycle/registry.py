"""Deterministic Research Cycle Registry Engine.

Coordinates versioned hypotheses, experiment plans, predictions, evidence updates,
and theory revisions across the scientific research cycle.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Mapping

from .gates import (
    PromotionBlockedError,
    apply_evidence_to_hypothesis,
    check_promotion_gates,
    validate_status_transition,
)
from .schema import (
    EpistemicLabel,
    EvidenceDataType,
    EvidenceUpdate,
    ExperimentPlan,
    HumanReviewGate,
    HypothesisRecord,
    HypothesisStatus,
    PredictionRecord,
    TheoryRevision,
    _safe_dict,
)
from .serialization import (
    compute_record_checksum,
    load_registry_json,
    save_registry_json,
    verify_record_checksum,
)


class ResearchCycleRegistry:
    """Versioned Hypothesis and Experiment Registry for automated scientific inquiry."""

    def __init__(self, registry_id: str = "default_research_cycle") -> None:
        self.registry_id = registry_id
        self.schema_version = "ResearchCycleRegistry.v1"
        self._hypotheses: dict[str, HypothesisRecord] = {}
        self._plans: dict[str, ExperimentPlan] = {}
        self._predictions: dict[str, PredictionRecord] = {}
        self._evidence: dict[str, EvidenceUpdate] = {}
        self._revisions: list[TheoryRevision] = []

    def register_hypothesis(self, hypothesis: HypothesisRecord) -> str:
        """Register a new hypothesis record after validating non-empty claim and required fields."""
        if not hypothesis.hypothesis_id:
            raise ValueError("hypothesis_id cannot be empty.")
        if not hypothesis.precise_claim:
            raise ValueError("precise_claim must be specified.")
        if not hypothesis.provenance:
            raise ValueError("provenance cannot be empty.")

        hyp_dict = hypothesis.to_dict()
        hypothesis.checksum = compute_record_checksum(hyp_dict)
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return hypothesis.hypothesis_id

    def register_experiment_plan(self, plan: ExperimentPlan) -> str:
        """Register a new experiment plan linked to an existing hypothesis."""
        if not plan.plan_id:
            raise ValueError("plan_id cannot be empty.")
        if plan.hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{plan.hypothesis_id}' not found in registry.")

        plan_dict = plan.to_dict()
        plan.checksum = compute_record_checksum(plan_dict)
        self._plans[plan.plan_id] = plan
        return plan.plan_id

    def register_prediction(self, prediction: PredictionRecord) -> str:
        """Register a pre-registered prediction linked to a hypothesis and experiment plan."""
        if not prediction.prediction_id:
            raise ValueError("prediction_id cannot be empty.")
        if prediction.hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{prediction.hypothesis_id}' not found in registry.")
        if prediction.plan_id not in self._plans:
            raise KeyError(f"Experiment plan '{prediction.plan_id}' not found in registry.")

        pred_dict = prediction.to_dict()
        prediction.checksum = compute_record_checksum(pred_dict)
        self._predictions[prediction.prediction_id] = prediction
        return prediction.prediction_id

    def sign_human_review_gate(
        self,
        hypothesis_id: str,
        reviewer: str,
        notes: str = "",
    ) -> None:
        """Sign and validate the human review oversight gate for a hypothesis."""
        if hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{hypothesis_id}' not found.")
        if not reviewer:
            raise ValueError("Reviewer identity cannot be empty.")

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        hyp = self._hypotheses[hypothesis_id]
        hyp.human_review_gate = HumanReviewGate(
            passed=True,
            reviewer=reviewer,
            timestamp=now_iso,
            review_notes=notes,
        )
        hyp.checksum = compute_record_checksum(hyp.to_dict())

    def transition_hypothesis_status(
        self,
        hypothesis_id: str,
        target_status: str,
        reviewer_id: str | None = None,
        reason_codes: list[str] | None = None,
        modifications: dict[str, Any] | None = None,
    ) -> TheoryRevision:
        """Transition a hypothesis to a new lifecycle status obeying all promotion gates."""
        if hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{hypothesis_id}' not found.")

        hyp = self._hypotheses[hypothesis_id]
        prev_status = hyp.status

        # 1. Validate permitted DAG transition
        validate_status_transition(prev_status, target_status)

        # 2. Check promotion gates
        all_ev = [self._evidence[eid] for eid in hyp.evidence_links if eid in self._evidence]
        check_promotion_gates(hyp, target_status, all_evidence=all_ev)

        # 3. Update status
        hyp.status = target_status
        hyp.checksum = compute_record_checksum(hyp.to_dict())

        # 4. Record TheoryRevision
        rev_id = f"rev_{hypothesis_id}_{len(self._revisions) + 1}"
        revision = TheoryRevision(
            revision_id=rev_id,
            hypothesis_id=hypothesis_id,
            previous_status=prev_status,
            new_status=target_status,
            reason_codes=reason_codes or ["manual_transition"],
            evidence_ids=list(hyp.evidence_links),
            modifications=modifications or {},
            unresolved_questions=list(hyp.unresolved_questions),
            human_review_signed=hyp.human_review_gate.passed,
            reviewer_id=reviewer_id or hyp.human_review_gate.reviewer,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            checksum="",
        )
        revision.checksum = compute_record_checksum(revision.to_dict())
        self._revisions.append(revision)
        return revision

    def ingest_evidence_update(self, evidence: EvidenceUpdate) -> TheoryRevision:
        """Ingest empirical or simulation evidence update, updating hypothesis without burying failures."""
        if not evidence.evidence_id:
            raise ValueError("evidence_id cannot be empty.")
        if evidence.hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{evidence.hypothesis_id}' not found in registry.")
        if not evidence.provenance:
            raise ValueError("Evidence provenance cannot be empty.")
        if not evidence.source_checksum or not evidence.experiment_checksum:
            raise ValueError("Evidence must include source_checksum and experiment_checksum.")

        hyp = self._hypotheses[evidence.hypothesis_id]
        prev_status = hyp.status

        # Compute evidence checksum and store
        evidence_dict = evidence.to_dict()
        evidence.checksum = compute_record_checksum(evidence_dict)
        self._evidence[evidence.evidence_id] = evidence

        # Apply update logic (retains contradictions and failed updates)
        new_status = apply_evidence_to_hypothesis(hyp, evidence)
        hyp.checksum = compute_record_checksum(hyp.to_dict())

        # Record revision
        rev_id = f"rev_{hyp.hypothesis_id}_{len(self._revisions) + 1}"
        reason = "contradictory_evidence_ingested" if evidence.is_contradictory else "evidence_ingested"
        revision = TheoryRevision(
            revision_id=rev_id,
            hypothesis_id=hyp.hypothesis_id,
            previous_status=prev_status,
            new_status=new_status,
            reason_codes=[reason],
            evidence_ids=[evidence.evidence_id],
            modifications={"metrics_observed": evidence.metrics_observed},
            unresolved_questions=list(hyp.unresolved_questions),
            human_review_signed=hyp.human_review_gate.passed,
            reviewer_id=hyp.human_review_gate.reviewer,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            checksum="",
        )
        revision.checksum = compute_record_checksum(revision.to_dict())
        self._revisions.append(revision)
        return revision

    def get_hypothesis(self, hypothesis_id: str) -> HypothesisRecord:
        """Retrieve hypothesis by ID."""
        if hypothesis_id not in self._hypotheses:
            raise KeyError(f"Hypothesis '{hypothesis_id}' not found.")
        return self._hypotheses[hypothesis_id]

    def get_experiment_plan(self, plan_id: str) -> ExperimentPlan:
        """Retrieve experiment plan by ID."""
        if plan_id not in self._plans:
            raise KeyError(f"Experiment plan '{plan_id}' not found.")
        return self._plans[plan_id]

    def get_hypotheses_by_status(self, status: HypothesisStatus | str) -> list[HypothesisRecord]:
        """Return all registered hypotheses with matching status."""
        stat_val = status.value if isinstance(status, HypothesisStatus) else str(status)
        return [h for h in self._hypotheses.values() if h.status == stat_val]

    def get_falsified_hypotheses(self) -> list[HypothesisRecord]:
        """Return all hypotheses marked as falsified."""
        return self.get_hypotheses_by_status(HypothesisStatus.FALSIFIED)

    def to_dict(self) -> dict[str, Any]:
        """Export entire registry state as a sanitized JSON dictionary."""
        return _safe_dict({
            "schema_version": self.schema_version,
            "registry_id": self.registry_id,
            "hypotheses": {k: v.to_dict() for k, v in sorted(self._hypotheses.items())},
            "plans": {k: v.to_dict() for k, v in sorted(self._plans.items())},
            "predictions": {k: v.to_dict() for k, v in sorted(self._predictions.items())},
            "evidence": {k: v.to_dict() for k, v in sorted(self._evidence.items())},
            "revisions": [r.to_dict() for r in self._revisions],
        })

    def save_to_file(self, output_path: str | Path) -> Path:
        """Save registry atomically to disk."""
        return save_registry_json(self.to_dict(), output_path)

    @classmethod
    def load_from_file(cls, input_path: str | Path) -> ResearchCycleRegistry:
        """Load and reconstruct registry from JSON file."""
        data = load_registry_json(input_path)
        reg = cls(registry_id=data.get("registry_id", "default_research_cycle"))

        for h_id, h_data in data.get("hypotheses", {}).items():
            gate_data = h_data.get("human_review_gate", {})
            gate = HumanReviewGate(
                passed=gate_data.get("passed", False),
                reviewer=gate_data.get("reviewer"),
                timestamp=gate_data.get("timestamp"),
                review_notes=gate_data.get("review_notes", ""),
            )
            hyp = HypothesisRecord(
                hypothesis_id=h_data.get("hypothesis_id", h_id),
                precise_claim=h_data.get("precise_claim", ""),
                construct_definitions=h_data.get("construct_definitions", {}),
                operational_variables=h_data.get("operational_variables", {}),
                predicted_direction=h_data.get("predicted_direction", ""),
                null_prediction=h_data.get("null_prediction", ""),
                alternative_explanations=h_data.get("alternative_explanations", []),
                falsification_criterion=h_data.get("falsification_criterion", ""),
                min_sample_size_or_power=h_data.get("min_sample_size_or_power", {}),
                preregistration_reference=h_data.get("preregistration_reference"),
                data_requirements=h_data.get("data_requirements", []),
                analysis_plan=h_data.get("analysis_plan", ""),
                provenance=h_data.get("provenance", {}),
                epistemic_label=h_data.get("epistemic_label", EpistemicLabel.SPECULATIVE_HYPOTHESIS.value),
                status=h_data.get("status", HypothesisStatus.PROPOSED.value),
                schema_version=h_data.get("schema_version", "HypothesisRecord.v1"),
                human_review_gate=gate,
                evidence_links=h_data.get("evidence_links", []),
                contradictory_evidence_links=h_data.get("contradictory_evidence_links", []),
                revision_history=h_data.get("revision_history", []),
                unresolved_questions=h_data.get("unresolved_questions", []),
                checksum=h_data.get("checksum", ""),
            )
            reg._hypotheses[hyp.hypothesis_id] = hyp

        for p_id, p_data in data.get("plans", {}).items():
            plan = ExperimentPlan(
                plan_id=p_data.get("plan_id", p_id),
                hypothesis_id=p_data.get("hypothesis_id", ""),
                domain=p_data.get("domain", ""),
                design_type=p_data.get("design_type", ""),
                variables=p_data.get("variables", {}),
                target_sample_size=p_data.get("target_sample_size", 0),
                power_analysis=p_data.get("power_analysis", {}),
                analysis_protocol=p_data.get("analysis_protocol", ""),
                surrogate_method=p_data.get("surrogate_method"),
                data_source=p_data.get("data_source", ""),
                is_synthetic=p_data.get("is_synthetic", False),
                provenance=p_data.get("provenance", {}),
                schema_version=p_data.get("schema_version", "ExperimentPlan.v1"),
                checksum=p_data.get("checksum", ""),
            )
            reg._plans[plan.plan_id] = plan

        for pred_id, pred_data in data.get("predictions", {}).items():
            pred = PredictionRecord(
                prediction_id=pred_data.get("prediction_id", pred_id),
                hypothesis_id=pred_data.get("hypothesis_id", ""),
                plan_id=pred_data.get("plan_id", ""),
                metric_name=pred_data.get("metric_name", ""),
                expected_direction=pred_data.get("expected_direction", ""),
                expected_effect_range=pred_data.get("expected_effect_range"),
                falsification_threshold=pred_data.get("falsification_threshold", {}),
                is_preregistered=pred_data.get("is_preregistered", True),
                schema_version=pred_data.get("schema_version", "PredictionRecord.v1"),
                checksum=pred_data.get("checksum", ""),
            )
            reg._predictions[pred.prediction_id] = pred

        for ev_id, ev_data in data.get("evidence", {}).items():
            ev = EvidenceUpdate(
                evidence_id=ev_data.get("evidence_id", ev_id),
                hypothesis_id=ev_data.get("hypothesis_id", ""),
                experiment_id=ev_data.get("experiment_id", ""),
                source_checksum=ev_data.get("source_checksum", ""),
                experiment_checksum=ev_data.get("experiment_checksum", ""),
                data_type=ev_data.get("data_type", EvidenceDataType.EMPIRICAL_DATASET.value),
                is_synthetic=ev_data.get("is_synthetic", False),
                is_out_of_sample=ev_data.get("is_out_of_sample", False),
                metrics_observed=ev_data.get("metrics_observed", {}),
                observed_effect_size=ev_data.get("observed_effect_size"),
                observed_p_value=ev_data.get("observed_p_value"),
                is_contradictory=ev_data.get("is_contradictory", False),
                contradiction_details=ev_data.get("contradiction_details"),
                provenance=ev_data.get("provenance", {}),
                notes=ev_data.get("notes", ""),
                schema_version=ev_data.get("schema_version", "EvidenceUpdate.v1"),
                checksum=ev_data.get("checksum", ""),
            )
            reg._evidence[ev.evidence_id] = ev

        for rev_data in data.get("revisions", []):
            rev = TheoryRevision(
                revision_id=rev_data.get("revision_id", ""),
                hypothesis_id=rev_data.get("hypothesis_id", ""),
                previous_status=rev_data.get("previous_status", ""),
                new_status=rev_data.get("new_status", ""),
                reason_codes=rev_data.get("reason_codes", []),
                evidence_ids=rev_data.get("evidence_ids", []),
                modifications=rev_data.get("modifications", {}),
                unresolved_questions=rev_data.get("unresolved_questions", []),
                human_review_signed=rev_data.get("human_review_signed", False),
                reviewer_id=rev_data.get("reviewer_id"),
                schema_version=rev_data.get("schema_version", "TheoryRevision.v1"),
                timestamp=rev_data.get("timestamp", ""),
                checksum=rev_data.get("checksum", ""),
            )
            reg._revisions.append(rev)

        return reg
