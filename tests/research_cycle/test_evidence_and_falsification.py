"""Tests for evidence ingestion, failure updates (Rule E), and contradiction retention (Rule F)."""
from __future__ import annotations

import pytest

from tools.research_cycle import (
    EpistemicLabel,
    EvidenceDataType,
    EvidenceUpdate,
    HypothesisRecord,
    HypothesisStatus,
    ResearchCycleRegistry,
)


def _build_test_registry() -> tuple[ResearchCycleRegistry, str]:
    reg = ResearchCycleRegistry(registry_id="reg_test")
    hyp = HypothesisRecord(
        hypothesis_id="hyp_fc_01",
        precise_claim="Triadic hypergraphs predict cross-frequency coupling shifts.",
        construct_definitions={"triadic": "3-node hyperedges"},
        operational_variables={"x": "anesthesia", "y": "betti1"},
        predicted_direction="positive",
        null_prediction="zero change",
        alternative_explanations=["motion artifact"],
        falsification_criterion="p > 0.05 on empirical cohort",
        min_sample_size_or_power={"n": 30},
        preregistration_reference="PREREG-001",
        data_requirements=["ds005620"],
        analysis_plan="paired test",
        provenance={"owner": "Antigravity C"},
        status=HypothesisStatus.READY_FOR_EXECUTION.value,
    )
    reg.register_hypothesis(hyp)
    return reg, hyp.hypothesis_id


def test_rule_e_failed_experiment_updates_hypothesis_rather_than_disappearing():
    """Rule E: A failed experiment updates the hypothesis to falsified or weakened, never deleted."""
    reg, hyp_id = _build_test_registry()

    # Ingest a falsifying evidence update
    failed_ev = EvidenceUpdate(
        evidence_id="ev_failed_01",
        hypothesis_id=hyp_id,
        experiment_id="exp_01",
        source_checksum="sha256:src123",
        experiment_checksum="sha256:exp123",
        data_type=EvidenceDataType.EMPIRICAL_DATASET.value,
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"observed_direction": "opposite", "p_val": 0.002},
        observed_effect_size=-0.65,
        observed_p_value=0.002,
        is_contradictory=True,
        contradiction_details="Statistically significant shift in the opposite direction from prediction.",
        provenance={"dataset": "ds005620"},
        notes="Preregistered test falsified original directional claim.",
    )

    rev = reg.ingest_evidence_update(failed_ev)
    hyp = reg.get_hypothesis(hyp_id)

    # Hypothesis is not deleted; its status is updated to FALSIFIED
    assert hyp.status == HypothesisStatus.FALSIFIED.value
    assert "ev_failed_01" in hyp.evidence_links
    assert "ev_failed_01" in hyp.contradictory_evidence_links
    assert len(hyp.revision_history) == 1
    assert hyp.revision_history[0]["new_status"] == HypothesisStatus.FALSIFIED.value
    assert hyp.revision_history[0]["is_contradictory"] is True

    # Check that it appears in falsified query
    falsified = reg.get_falsified_hypotheses()
    assert len(falsified) == 1
    assert falsified[0].hypothesis_id == hyp_id


def test_rule_f_contradictory_evidence_remains_visible():
    """Rule F: Conflicting evidence must remain permanently visible in contradictory_evidence_links."""
    reg, hyp_id = _build_test_registry()

    # First evidence is contradictory
    contra_ev = EvidenceUpdate(
        evidence_id="ev_contra_01",
        hypothesis_id=hyp_id,
        experiment_id="exp_01",
        source_checksum="sha256:src1",
        experiment_checksum="sha256:exp1",
        data_type=EvidenceDataType.EMPIRICAL_DATASET.value,
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"effect": -0.15},
        observed_effect_size=-0.15,
        observed_p_value=0.25,
        is_contradictory=True,
        contradiction_details="Null effect observed in subset A.",
        provenance={"dataset": "ds005620"},
    )
    reg.ingest_evidence_update(contra_ev)

    # Second evidence is non-contradictory
    second_ev = EvidenceUpdate(
        evidence_id="ev_clean_02",
        hypothesis_id=hyp_id,
        experiment_id="exp_02",
        source_checksum="sha256:src2",
        experiment_checksum="sha256:exp2",
        data_type=EvidenceDataType.EMPIRICAL_DATASET.value,
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"effect": 0.45},
        observed_effect_size=0.45,
        observed_p_value=0.03,
        is_contradictory=False,
        provenance={"dataset": "ds005620"},
    )
    reg.ingest_evidence_update(second_ev)

    hyp = reg.get_hypothesis(hyp_id)
    # Contradictory evidence remains logged and visible
    assert "ev_contra_01" in hyp.contradictory_evidence_links
    assert len(hyp.evidence_links) == 2
    assert len(hyp.revision_history) == 2


def test_missing_provenance_rejected():
    """Verify that registering an evidence update or hypothesis without provenance raises ValueError."""
    reg = ResearchCycleRegistry()

    # Empty provenance hypothesis
    with pytest.raises(ValueError, match="provenance"):
        reg.register_hypothesis(
            HypothesisRecord(
                hypothesis_id="h_bad",
                precise_claim="Claim",
                construct_definitions={},
                operational_variables={},
                predicted_direction="pos",
                null_prediction="null",
                alternative_explanations=[],
                falsification_criterion="crit",
                min_sample_size_or_power={},
                preregistration_reference=None,
                data_requirements=[],
                analysis_plan="",
                provenance={},  # Empty!
            )
        )


def test_missing_checksums_rejected():
    """Verify that evidence without source or experiment checksum is rejected."""
    reg, hyp_id = _build_test_registry()
    with pytest.raises(ValueError, match="checksum"):
        reg.ingest_evidence_update(
            EvidenceUpdate(
                evidence_id="ev_no_chk",
                hypothesis_id=hyp_id,
                experiment_id="exp_01",
                source_checksum="",  # Missing!
                experiment_checksum="sha256:exp",
                data_type=EvidenceDataType.EMPIRICAL_DATASET.value,
                is_synthetic=False,
                is_out_of_sample=True,
                metrics_observed={},
                observed_effect_size=None,
                observed_p_value=None,
                provenance={"source": "test"},
            )
        )
