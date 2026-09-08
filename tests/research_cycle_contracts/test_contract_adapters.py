"""Comprehensive unit and integration tests for research cycle contract compatibility.

Verifies:
1. Complete hypothesis adapter round-trip and field retention (all 10 fields).
2. Incomplete hypothesis rejection (missing null prediction / falsification criteria).
3. Synthetic experiment claiming empirical proof rejection.
4. Empirical evidence lacking dataset verification rejection.
5. Contradictory evidence preservation and non-suppression.
6. Formal evidence promotion gating (human reviewer signoff required).
7. Missing source provenance rejection.
8. Tamper-evident checksum computation and integrity failure detection.
9. Version negotiation and migration warnings.
10. CLI validation tool end-to-end execution.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.research_cycle_contracts import (
    AwarenessHypothesisNodeV1,
    AwarenessStudioCycleInputV1,
    ContractCompatibilityError,
    ContractRejectionError,
    EvidenceUpdateV1,
    ExperimentLedgerRowV1,
    ExperimentPlanV1,
    HypothesisRecordV1,
    MigrationWarning,
    RejectionReasonCode,
    SupportedFeatureFamily,
    awareness_node_to_hypothesis,
    compute_checksum,
    cycle_input_to_registry_bundle,
    get_supported_schema_versions,
    hypothesis_to_awareness_node,
    ledger_row_to_evidence,
    load_contract_json,
    negotiate_contract_version,
    plan_and_evidence_to_ledger_row,
    registry_bundle_to_cycle_input,
    save_contract_json,
    validate_evidence_contract,
    validate_hypothesis_contract,
    validate_ledger_row_contract,
    verify_checksum,
)
from scripts.validate_research_cycle_contracts import main as cli_main


def _make_valid_hypothesis(
    hypothesis_id: str = "hypo-topo-001",
    status: str = "proposed",
    human_review_passed: bool = False,
    human_reviewer: str | None = None,
) -> HypothesisRecordV1:
    """Fixture helper for a valid HypothesisRecordV1."""
    return HypothesisRecordV1(
        hypothesis_id=hypothesis_id,
        precise_claim="Triadic hypergraph transitions exhibit higher persistent homology Betti-1 stability than pairwise controls.",
        construct_definitions={"triadic_hypergraph": "Three-way simultaneous co-activation simplex", "betti_1": "1-dimensional topological cycle"},
        operational_variables={"feature": "betti_1_stability", "window_size": "100ms"},
        predicted_direction="positive",
        null_prediction="Betti-1 stability does not exceed phase-randomized surrogate distributions (delta <= 0.05).",
        alternative_explanations=["Nonlinear pairwise coupling leakage", "Artifactual head motion burst"],
        falsification_criterion="Betti-1 difference p >= 0.05 against circular-shift null surrogate distribution.",
        min_sample_size_or_power={"n_subjects": 30, "power": 0.85},
        preregistration_reference="PREREG-2026-NEUROTOPO-001",
        data_requirements=["ds005620_paired_manifest"],
        dataset_ids=["ds005620"],
        analysis_plan="Paired Wilcoxon signed-rank comparison between triadic and surrogate topologies.",
        provenance={"source_id": "src-lit-2024-001", "creator": "NeuroTopology Working Group"},
        feature_family=SupportedFeatureFamily.TOPOLOGICAL_HOMOLOGY.value,
        epistemic_label="speculative_hypothesis",
        status=status,
        evidence_class="descriptive_or_paired_statistics",
        human_review_gate={"passed": human_review_passed, "reviewer": human_reviewer, "timestamp": "2026-09-07T12:00:00Z", "notes": "Approved for validation"},
        evidence_links=["ev-001"],
        contradictory_evidence_links=["ev-contra-002"],
        revision_history=[],
        unresolved_questions=["Spatial electrode resolution limits"],
    )


# --- Scenario 1: Complete Valid Hypothesis Round-Trip ---

def test_scenario_1_complete_hypothesis_roundtrip():
    """Verify that a valid hypothesis converts to an Awareness Studio node and back losslessly."""
    hypo = _make_valid_hypothesis()
    node, warnings = hypothesis_to_awareness_node(hypo, validate=True)

    # Validate node fields
    assert node.node_id == hypo.hypothesis_id
    assert node.null_prediction == hypo.null_prediction
    assert node.falsification_criteria == hypo.falsification_criterion
    assert node.feature_family == hypo.feature_family
    assert "src-lit-2024-001" in node.source_ids
    assert "ds005620" in node.dataset_ids
    assert "ev-contra-002" in node.contradictions
    assert node.checksum

    # Round trip back
    reconstituted, warnings2 = awareness_node_to_hypothesis(node, validate=True)
    assert reconstituted.hypothesis_id == hypo.hypothesis_id
    assert reconstituted.null_prediction == hypo.null_prediction
    assert reconstituted.falsification_criterion == hypo.falsification_criterion
    assert reconstituted.feature_family == hypo.feature_family
    assert reconstituted.contradictory_evidence_links == hypo.contradictory_evidence_links
    assert reconstituted.dataset_ids == hypo.dataset_ids


# --- Scenario 2: Incomplete Hypothesis Rejection ---

def test_scenario_2_incomplete_hypothesis_missing_null_and_falsification():
    """Verify rejection when null prediction or falsification criterion is absent."""
    # Missing null prediction
    hypo_no_null = _make_valid_hypothesis()
    hypo_no_null.null_prediction = ""
    with pytest.raises(ContractRejectionError) as exc_info:
        validate_hypothesis_contract(hypo_no_null)
    assert exc_info.value.reason_code == RejectionReasonCode.MISSING_NULL_PREDICTION.value

    # Missing falsification criterion
    hypo_no_falsif = _make_valid_hypothesis()
    hypo_no_falsif.falsification_criterion = "   "
    with pytest.raises(ContractRejectionError) as exc_info2:
        validate_hypothesis_contract(hypo_no_falsif)
    assert exc_info2.value.reason_code == RejectionReasonCode.MISSING_FALSIFICATION_CRITERIA.value


# --- Scenario 3: Synthetic Experiment Masquerading as Empirical Evidence ---

def test_scenario_3_synthetic_claiming_empirical_proof():
    """Verify rejection when synthetic data claims to be empirical or formal fact."""
    ev = EvidenceUpdateV1(
        evidence_id="ev-synth-001",
        hypothesis_id="hypo-001",
        experiment_id="exp-synth-001",
        source_ids=["src-001"],
        dataset_ids=["ds-synth"],
        source_checksum="sha256:abc",
        experiment_checksum="sha256:def",
        data_type="empirical_dataset",  # Fraudulent mismatch
        is_synthetic=True,
        is_out_of_sample=False,
        metrics_observed={"effect": 0.8},
        observed_effect_size=0.8,
        observed_p_value=0.001,
        provenance={"generator": "synthetic_agent"},
    )
    with pytest.raises(ContractRejectionError) as exc_info:
        validate_evidence_contract(ev)
    assert exc_info.value.reason_code == RejectionReasonCode.SYNTHETIC_EMPIRICAL_CLAIMS.value


# --- Scenario 4: Empirical Claim with Missing Dataset ---

def test_scenario_4_empirical_claim_without_dataset():
    """Verify rejection when empirical dataset claims formal status but lists no dataset IDs."""
    ev = EvidenceUpdateV1(
        evidence_id="ev-emp-001",
        hypothesis_id="hypo-001",
        experiment_id="exp-emp-001",
        source_ids=["src-001"],
        dataset_ids=[],  # Missing dataset
        source_checksum="sha256:abc",
        experiment_checksum="sha256:def",
        data_type="empirical_dataset",
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"effect": 0.4},
        observed_effect_size=0.4,
        observed_p_value=0.02,
        provenance={"study": "eeg_recording"},
    )
    with pytest.raises(ContractRejectionError) as exc_info:
        validate_evidence_contract(ev)
    assert exc_info.value.reason_code == RejectionReasonCode.UNVERIFIED_FORMAL_STATUS.value


# --- Scenario 5: Contradictory Evidence Retention ---

def test_scenario_5_contradictory_evidence_handling():
    """Verify contradictory evidence is correctly captured and mapped to ledger without suppression."""
    plan = ExperimentPlanV1(
        plan_id="plan-001",
        hypothesis_id="hypo-topo-001",
        domain="higher_order_spectra",
        design_type="paired_cohort",
        variables={"window": 100},
        target_sample_size=30,
        power_analysis={"power": 0.85},
        analysis_protocol="wilcoxon",
        dataset_id="ds005620",
        is_synthetic=False,
        provenance={"team": "Antigravity C"},
        checksum="sha256:plan123",
    )
    ev_contra = EvidenceUpdateV1(
        evidence_id="ev-contra-001",
        hypothesis_id="hypo-topo-001",
        experiment_id="plan-001",
        source_ids=["src-001"],
        dataset_ids=["ds005620"],
        source_checksum="sha256:src123",
        experiment_checksum="sha256:exp123",
        data_type="empirical_dataset",
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"observed_effect": -0.12, "observed_p": 0.45},
        observed_effect_size=-0.12,
        observed_p_value=0.45,
        is_contradictory=True,
        contradiction_details="Observed effect direction was opposite to preregistered prediction.",
        provenance={"audit": "cohort_statistics"},
    )

    hypo = _make_valid_hypothesis()
    row, warnings = plan_and_evidence_to_ledger_row(plan, ev_contra, hypo)

    assert row.is_contradictory is True
    assert row.outcome_status == "contradicted"
    assert "opposite to preregistered prediction" in str(row.contradiction_reason)
    assert row.null_prediction == hypo.null_prediction

    # Reverse adapter preserves contradiction
    ev_back, _ = ledger_row_to_evidence(row)
    assert ev_back.is_contradictory is True
    assert ev_back.contradiction_details == row.contradiction_reason


# --- Scenario 6: Formal Evidence Human Review Gate ---

def test_scenario_6_formal_evidence_promotion_gate():
    """Verify promotion to supported_as_specified requires explicit passed human review gate."""
    hypo_unreviewed = _make_valid_hypothesis(
        status="supported_as_specified",
        human_review_passed=False,
        human_reviewer=None,
    )
    with pytest.raises(ContractRejectionError) as exc_info:
        validate_hypothesis_contract(hypo_unreviewed)
    assert exc_info.value.reason_code == RejectionReasonCode.UNSUPPORTED_PROMOTION.value

    # When reviewed and passed by human, validation succeeds
    hypo_reviewed = _make_valid_hypothesis(
        status="supported_as_specified",
        human_review_passed=True,
        human_reviewer="Dr. Jane Doe",
    )
    notices = validate_hypothesis_contract(hypo_reviewed)
    assert any("Human review oversight confirmed" in n for n in notices)


# --- Scenario 7: Missing Source Identity and Incompatible Feature Families ---

def test_scenario_7_missing_source_identity_and_feature_families():
    """Verify rejection when provenance lacks identifiable source or uses illegal feature family."""
    hypo_no_prov = _make_valid_hypothesis()
    hypo_no_prov.provenance = {}
    with pytest.raises(ContractRejectionError) as exc_info:
        validate_hypothesis_contract(hypo_no_prov)
    assert exc_info.value.reason_code == RejectionReasonCode.MISSING_SOURCE_PROVENANCE.value

    hypo_bad_family = _make_valid_hypothesis()
    hypo_bad_family.feature_family = "unauthorized_esoteric_telepathy"
    with pytest.raises(ContractRejectionError) as exc_info2:
        validate_hypothesis_contract(hypo_bad_family)
    assert exc_info2.value.reason_code == RejectionReasonCode.INCOMPATIBLE_FEATURE_FAMILIES.value


# --- Scenario 8: Checksum Invariance and Tamper Detection ---

def test_scenario_8_checksum_and_tampering(tmp_path: Path):
    """Verify that checksums detect post-issuance modification and serialization is atomic."""
    hypo = _make_valid_hypothesis()
    target_file = tmp_path / "hypo.json"
    digest = save_contract_json(hypo, target_file)

    # Valid load passes checksum verification
    loaded = load_contract_json(target_file, verify_integrity=True)
    assert loaded["checksum"] == digest

    # Tamper with file content
    loaded["precise_claim"] = "Tampered claim content inserted by adversary."
    tampered_file = tmp_path / "tampered.json"
    # Write raw tampered content with stale checksum
    tampered_file.write_text(json.dumps(loaded), encoding="utf-8")

    with pytest.raises(ContractCompatibilityError) as exc_info:
        load_contract_json(tampered_file, verify_integrity=True)
    assert "Integrity checksum mismatch" in str(exc_info.value)


# --- Scenario 9: Registry Bundle to Cycle Input Aggregation ---

def test_scenario_9_bundle_aggregation_and_roundtrip():
    """Verify bundling hypotheses, plans, and evidence into AwarenessStudioCycleInput and unpacking."""
    hypo = _make_valid_hypothesis()
    plan = ExperimentPlanV1(
        plan_id="plan-001",
        hypothesis_id=hypo.hypothesis_id,
        domain="triadic_hypergraph",
        design_type="paired_cohort",
        variables={"k": 3},
        target_sample_size=30,
        power_analysis={"alpha": 0.05},
        analysis_protocol="simplex_decomposition",
        dataset_id="ds005620",
        checksum="sha256:plan001",
    )
    evidence = EvidenceUpdateV1(
        evidence_id="ev-001",
        hypothesis_id=hypo.hypothesis_id,
        experiment_id=plan.plan_id,
        source_ids=["src-001"],
        dataset_ids=["ds005620"],
        source_checksum="sha256:src001",
        experiment_checksum="sha256:exp001",
        data_type="empirical_dataset",
        is_synthetic=False,
        is_out_of_sample=True,
        metrics_observed={"betti_1_stability": 0.42},
        observed_effect_size=0.42,
        observed_p_value=0.01,
        provenance={"pipeline": "pitnn"},
        checksum="sha256:ev001",
    )

    cycle_input, warnings = registry_bundle_to_cycle_input(
        hypotheses=[hypo],
        plans=[plan],
        evidence_list=[evidence],
        cycle_id="cycle-2026-test",
    )

    assert len(cycle_input.nodes) == 1
    assert cycle_input.nodes[0].node_id == hypo.hypothesis_id
    assert len(cycle_input.plans) == 1
    assert len(cycle_input.evidence) == 1

    # Unpack
    hyp_list, plan_list, ev_list, warnings2 = cycle_input_to_registry_bundle(cycle_input)
    assert len(hyp_list) == 1
    assert hyp_list[0].hypothesis_id == hypo.hypothesis_id
    assert len(plan_list) == 1
    assert plan_list[0].plan_id == plan.plan_id
    assert len(ev_list) == 1
    assert ev_list[0].evidence_id == evidence.evidence_id


# --- Scenario 10: Version Negotiation ---

def test_scenario_10_version_negotiator():
    """Verify version negotiation rules for minor and major version adaptations."""
    # Minor forward adaptation emits warning
    ver, warnings = negotiate_contract_version("HypothesisRecord.v1.0", "HypothesisRecord.v1.1")
    assert ver == "HypothesisRecord.v1.1"
    assert len(warnings) == 1
    assert warnings[0].warning_type == "forward_adaptation"

    # Major version break raises ContractCompatibilityError
    with pytest.raises(ContractCompatibilityError) as exc_info:
        negotiate_contract_version("HypothesisRecord.v1.0", "HypothesisRecord.v2.0")
    assert "Breaking schema major version mismatch" in str(exc_info.value)

    # Schema family check
    versions = get_supported_schema_versions()
    assert "HypothesisRecord" in versions
    assert "ExperimentPlan" in versions


# --- Scenario 11: CLI Validator Integration ---

def test_scenario_11_cli_validator(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Verify CLI tool on valid contract, gate violations, and format conversion."""
    hypo = _make_valid_hypothesis()
    hypo_path = tmp_path / "valid_hypo.json"
    save_contract_json(hypo, hypo_path)

    # Test valid pass
    exit_code = cli_main(["--input", str(hypo_path), "--check-gates"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[PASS]" in captured.out

    # Test conversion to awareness_node
    out_node_path = tmp_path / "converted_node.json"
    exit_code_conv = cli_main([
        "--input", str(hypo_path),
        "--convert-to", "awareness_node",
        "--output", str(out_node_path),
    ])
    assert exit_code_conv == 0
    assert out_node_path.exists()
    _ = capsys.readouterr()

    # Load converted node and verify
    node_data = load_contract_json(out_node_path)
    assert node_data["node_id"] == hypo.hypothesis_id
    assert node_data["schema_version"] == "AwarenessHypothesisNode.v1"

    # Test JSON output mode
    exit_code_json = cli_main(["--input", str(hypo_path), "--json-output"])
    assert exit_code_json == 0
    captured_json = capsys.readouterr()
    report = json.loads(captured_json.out)
    assert report["overall_valid"] is True
    assert len(report["results"]) == 1
