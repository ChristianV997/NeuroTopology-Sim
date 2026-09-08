"""Tests for research cycle lifecycle transitions and promotion gates (Rules A, B, C, D, G)."""
from __future__ import annotations

import pytest

from tools.research_cycle import (
    EpistemicLabel,
    EvidenceDataType,
    EvidenceUpdate,
    HumanReviewGate,
    HypothesisRecord,
    HypothesisStatus,
    InvalidStatusTransitionError,
    PromotionBlockedError,
    ResearchCycleRegistry,
    check_promotion_gates,
    validate_status_transition,
)


def _make_sample_hypothesis(
    hypothesis_id: str = "hyp_001",
    status: str = HypothesisStatus.PROPOSED.value,
    epistemic_label: str = EpistemicLabel.SPECULATIVE_HYPOTHESIS.value,
    human_approved: bool = False,
) -> HypothesisRecord:
    gate = HumanReviewGate(
        passed=human_approved,
        reviewer="Dr. Jane Doe" if human_approved else None,
        timestamp="2026-09-07T12:00:00Z" if human_approved else None,
        review_notes="Approved after preregistration audit" if human_approved else "",
    )
    return HypothesisRecord(
        hypothesis_id=hypothesis_id,
        precise_claim="Triadic functional connectivity reveals higher Betti-1 persistence than bivariate nulls in conscious states.",
        construct_definitions={"triadic_fc": "3-node synergy hyperedge", "betti_1": "1-dimensional topological cavities"},
        operational_variables={"independent": "anesthetic_depth", "dependent": "betti_1_persistence"},
        predicted_direction="positive",
        null_prediction="No significant difference in Betti-1 persistence between conditions.",
        alternative_explanations=["Bivariate correlation artifact", "Motion-induced volume fluctuations"],
        falsification_criterion="No significant divergence (p > 0.05) across paired awake-vs-sedated contrast.",
        min_sample_size_or_power={"min_n": 30, "power": 0.8, "alpha": 0.05},
        preregistration_reference="OSF-PREREG-2026-NTS-01",
        data_requirements=["ds005620", "eeg_resting_state"],
        analysis_plan="Paired topological persistent homology with Wilcoxon signed-rank test.",
        provenance={"creator": "Antigravity C", "cycle": "2026.09"},
        epistemic_label=epistemic_label,
        status=status,
        human_review_gate=gate,
    )


def test_valid_lifecycle_transitions():
    """Verify permitted sequential state progression through the lifecycle DAG."""
    validate_status_transition(HypothesisStatus.PROPOSED.value, HypothesisStatus.PREREGISTERED.value)
    validate_status_transition(HypothesisStatus.PREREGISTERED.value, HypothesisStatus.READY_FOR_EXECUTION.value)
    validate_status_transition(HypothesisStatus.READY_FOR_EXECUTION.value, HypothesisStatus.EXECUTED.value)
    validate_status_transition(HypothesisStatus.EXECUTED.value, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value)
    validate_status_transition(HypothesisStatus.EXECUTED.value, HypothesisStatus.FALSIFIED.value)
    validate_status_transition(HypothesisStatus.EXECUTED.value, HypothesisStatus.WEAKENED.value)
    validate_status_transition(HypothesisStatus.EXECUTED.value, HypothesisStatus.INCONCLUSIVE.value)


def test_invalid_lifecycle_transitions():
    """Verify that jumping stages or promoting falsified claims raises InvalidStatusTransitionError."""
    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(HypothesisStatus.PROPOSED.value, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value)

    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(HypothesisStatus.FALSIFIED.value, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value)

    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(HypothesisStatus.RETIRED.value, HypothesisStatus.READY_FOR_EXECUTION.value)


def test_rule_a_literature_claim_cannot_become_empirical():
    """Rule A: A literature claim cannot promote hypothesis to executed/supported without data."""
    hyp = _make_sample_hypothesis(status=HypothesisStatus.EXECUTED.value, human_approved=True)
    lit_evidence = EvidenceUpdate(
        evidence_id="ev_lit_01",
        hypothesis_id=hyp.hypothesis_id,
        experiment_id="exp_none",
        source_checksum="sha256:abc",
        experiment_checksum="sha256:def",
        data_type=EvidenceDataType.LITERATURE_CLAIM.value,
        is_synthetic=False,
        is_out_of_sample=False,
        metrics_observed={"citation": "Smith et al. 2024"},
        observed_effect_size=None,
        observed_p_value=None,
        provenance={"source": "review_paper"},
    )

    with pytest.raises(PromotionBlockedError, match="Rule A"):
        check_promotion_gates(hyp, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value, evidence=lit_evidence)


def test_rule_b_synthetic_simulation_cannot_become_biological_evidence():
    """Rule B: A synthetic simulation cannot be used to promote a biological hypothesis."""
    # Biological empirical hypothesis
    hyp = _make_sample_hypothesis(
        status=HypothesisStatus.EXECUTED.value,
        epistemic_label=EpistemicLabel.PREREGISTERED_EMPIRICAL.value,
        human_approved=True,
    )
    synth_evidence = EvidenceUpdate(
        evidence_id="ev_synth_01",
        hypothesis_id=hyp.hypothesis_id,
        experiment_id="exp_sim_01",
        source_checksum="sha256:111",
        experiment_checksum="sha256:222",
        data_type=EvidenceDataType.SYNTHETIC_SIMULATION.value,
        is_synthetic=True,
        is_out_of_sample=True,
        metrics_observed={"betti_1": 12.0},
        observed_effect_size=0.8,
        observed_p_value=0.001,
        provenance={"generator": "sim_engine"},
    )

    with pytest.raises(PromotionBlockedError, match="Rule B"):
        check_promotion_gates(hyp, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value, evidence=synth_evidence)

    # However, for a purely computational model hypothesis, synthetic evidence is permitted
    comp_hyp = _make_sample_hypothesis(
        status=HypothesisStatus.EXECUTED.value,
        epistemic_label=EpistemicLabel.COMPUTATIONAL_MODEL.value,
        human_approved=True,
    )
    passes = check_promotion_gates(comp_hyp, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value, evidence=synth_evidence)
    assert any("Rule B passed" in p for p in passes)


def test_rule_c_proxy_bayes_factor_cannot_become_formal_evidence():
    """Rule C: A proxy Bayes factor cannot serve as formal evidence for hypothesis support."""
    hyp = _make_sample_hypothesis(status=HypothesisStatus.EXECUTED.value, human_approved=True)
    proxy_bf_evidence = EvidenceUpdate(
        evidence_id="ev_proxy_bf",
        hypothesis_id=hyp.hypothesis_id,
        experiment_id="exp_proxy",
        source_checksum="sha256:333",
        experiment_checksum="sha256:444",
        data_type=EvidenceDataType.PROXY_BAYES_FACTOR.value,
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"proxy_k": 120.0},
        observed_effect_size=None,
        observed_p_value=None,
        provenance={"method": "heuristic_proxy"},
    )

    with pytest.raises(PromotionBlockedError, match="Rule C"):
        check_promotion_gates(hyp, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value, evidence=proxy_bf_evidence)


def test_rule_d_model_improvement_must_be_out_of_sample():
    """Rule D: A model improvement must be evaluated out-of-sample."""
    comp_hyp = _make_sample_hypothesis(
        status=HypothesisStatus.EXECUTED.value,
        epistemic_label=EpistemicLabel.COMPUTATIONAL_MODEL.value,
        human_approved=True,
    )
    in_sample_evidence = EvidenceUpdate(
        evidence_id="ev_in_sample",
        hypothesis_id=comp_hyp.hypothesis_id,
        experiment_id="exp_train",
        source_checksum="sha256:555",
        experiment_checksum="sha256:666",
        data_type=EvidenceDataType.SYNTHETIC_SIMULATION.value,
        is_synthetic=True,
        is_out_of_sample=False,  # In-sample only
        metrics_observed={"r2_train": 0.99},
        observed_effect_size=0.9,
        observed_p_value=0.001,
        provenance={"dataset": "training_split"},
    )

    with pytest.raises(PromotionBlockedError, match="Rule D"):
        check_promotion_gates(comp_hyp, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value, evidence=in_sample_evidence)


def test_rule_g_human_review_gate_required_for_support():
    """Rule G: Speculative theories cannot autonomously self-certify as supported without human review."""
    unreviewed_hyp = _make_sample_hypothesis(
        status=HypothesisStatus.EXECUTED.value,
        human_approved=False,  # Not signed off by human reviewer
    )
    emp_evidence = EvidenceUpdate(
        evidence_id="ev_emp_01",
        hypothesis_id=unreviewed_hyp.hypothesis_id,
        experiment_id="exp_emp_01",
        source_checksum="sha256:777",
        experiment_checksum="sha256:888",
        data_type=EvidenceDataType.EMPIRICAL_DATASET.value,
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"dz": 0.72},
        observed_effect_size=0.72,
        observed_p_value=0.005,
        provenance={"dataset": "ds005620"},
    )

    with pytest.raises(PromotionBlockedError, match="Rule G"):
        check_promotion_gates(unreviewed_hyp, HypothesisStatus.SUPPORTED_AS_SPECIFIED.value, evidence=emp_evidence)
