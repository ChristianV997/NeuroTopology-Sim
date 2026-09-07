"""Tests for domain experiment planners, RFC-8259 serialization, tampering detection, and CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_research_cycle import main as cli_main
from tools.research_cycle import (
    DiscernmentNonjudgmentPlanner,
    ExperimentDomain,
    HigherOrderSpectraPlanner,
    HypergraphTransitionPlanner,
    HypothesisRecord,
    HypothesisStatus,
    NullSurrogatePlanner,
    PairwiseVsTriadicFCPlanner,
    ResearchCycleRegistry,
    RespirationAutonomicPlanner,
    compute_record_checksum,
    load_registry_json,
    save_registry_json,
    verify_record_checksum,
)


def _make_dummy_hypothesis(hyp_id: str = "hyp_plan_01") -> HypothesisRecord:
    return HypothesisRecord(
        hypothesis_id=hyp_id,
        precise_claim="Operationalized test claim.",
        construct_definitions={"c1": "def1"},
        operational_variables={"v1": "var1"},
        predicted_direction="positive",
        null_prediction="zero",
        alternative_explanations=[],
        falsification_criterion="p > 0.05",
        min_sample_size_or_power={"n": 30},
        preregistration_reference="PREREG-002",
        data_requirements=["ds005620"],
        analysis_plan="plan",
        provenance={"owner": "Antigravity C"},
    )


def test_six_domain_experiment_planners():
    """Verify all 6 required experiment planners generate valid ExperimentPlan records."""
    reg = ResearchCycleRegistry()
    hyp = _make_dummy_hypothesis("hyp_001")
    reg.register_hypothesis(hyp)

    # 1. Pairwise vs triadic FC
    p1 = PairwiseVsTriadicFCPlanner.build_plan("plan_fc", hyp.hypothesis_id)
    assert p1.domain == ExperimentDomain.PAIRWISE_VS_TRIADIC_FC.value
    assert "triadic_hypergraph" in p1.variables["orders_compared"]
    reg.register_experiment_plan(p1)

    # 2. Higher-order spectra
    p2 = HigherOrderSpectraPlanner.build_plan("plan_spectra", hyp.hypothesis_id)
    assert p2.domain == ExperimentDomain.HIGHER_ORDER_SPECTRA.value
    assert "bicoherence_phase_coupling" in p2.variables["dependent"]
    reg.register_experiment_plan(p2)

    # 3. Respiration & autonomic modulation
    p3 = RespirationAutonomicPlanner.build_plan("plan_resp", hyp.hypothesis_id)
    assert p3.domain == ExperimentDomain.RESPIRATION_AUTONOMIC_MODULATION.value
    assert "neural_topological_winding" in p3.variables["dependent"]
    reg.register_experiment_plan(p3)

    # 4. Discernment vs nonjudgment
    p4 = DiscernmentNonjudgmentPlanner.build_plan("plan_att", hyp.hypothesis_id)
    assert p4.domain == ExperimentDomain.DISCERNMENT_NONJUDGMENT_OPERATIONALIZATION.value
    assert "open_monitoring_nonjudgment" in p4.variables["attentional_states"]
    reg.register_experiment_plan(p4)

    # 5. Hypergraph transition forecasting
    p5 = HypergraphTransitionPlanner.build_plan("plan_trans", hyp.hypothesis_id)
    assert p5.domain == ExperimentDomain.HYPERGRAPH_TRANSITION_FORECASTING.value
    assert "critical_slowing_down_autocorrelation" in p5.variables["dependent"]
    reg.register_experiment_plan(p5)

    # 6. Null and surrogate experiments
    p6 = NullSurrogatePlanner.build_plan("plan_null", hyp.hypothesis_id, surrogate_type="iaaft")
    assert p6.domain == ExperimentDomain.NULL_AND_SURROGATE.value
    assert p6.surrogate_method == "iaaft"
    reg.register_experiment_plan(p6)

    assert len(reg._plans) == 6


def test_rfc8259_strict_json_finite_serialization(tmp_path):
    """Verify registry serialization enforces RFC-8259 JSON without NaN or Infinity."""
    reg = ResearchCycleRegistry(registry_id="reg_finite_test")
    hyp = _make_dummy_hypothesis("hyp_finite_01")
    reg.register_hypothesis(hyp)

    out_file = tmp_path / "registry_finite.json"
    reg.save_to_file(out_file)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")

    # Tokens check
    assert "NaN" not in content
    assert "Infinity" not in content

    # Re-hydrate from file
    loaded = ResearchCycleRegistry.load_from_file(out_file)
    assert loaded.registry_id == "reg_finite_test"
    assert "hyp_finite_01" in loaded._hypotheses


def test_checksum_tamper_detection():
    """Verify that tampering with any record field invalidates its SHA-256 digest."""
    hyp = _make_dummy_hypothesis("hyp_tamper_01")
    hyp_dict = hyp.to_dict()
    hyp.checksum = compute_record_checksum(hyp_dict)
    assert verify_record_checksum(hyp.to_dict()) is True

    # Tamper with claim
    tampered = hyp.to_dict()
    tampered["precise_claim"] = "Completely altered claim."
    assert verify_record_checksum(tampered) is False


def test_cli_smoke_and_validation(tmp_path, capsys):
    """Verify scripts/validate_research_cycle.py audits registry files correctly."""
    reg = ResearchCycleRegistry(registry_id="reg_cli_test")
    hyp = _make_dummy_hypothesis("hyp_cli_01")
    reg.register_hypothesis(hyp)

    plan = PairwiseVsTriadicFCPlanner.build_plan("plan_cli_01", hyp.hypothesis_id)
    reg.register_experiment_plan(plan)

    reg_file = tmp_path / "reg_cli.json"
    reg.save_to_file(reg_file)

    # Run CLI
    exit_code = cli_main(["--registry", str(reg_file)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "RESEARCH CYCLE REGISTRY VALIDATION AUDIT" in captured.out
    assert "Total Hypotheses:       1" in captured.out
    assert "Experiment Plans:       1" in captured.out

    # Test JSON output mode
    json_exit_code = cli_main(["--registry", str(reg_file), "--json-output"])
    assert json_exit_code == 0


def test_no_network_operation(monkeypatch):
    """Verify all registry and planning operations function without any network activity."""
    import socket

    def blocked_connect(*args, **kwargs):
        raise RuntimeError("Network activity blocked in offline research cycle test.")

    monkeypatch.setattr(socket, "create_connection", blocked_connect)
    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    reg = ResearchCycleRegistry(registry_id="offline_reg")
    hyp = _make_dummy_hypothesis("hyp_offline")
    reg.register_hypothesis(hyp)
    plan = HigherOrderSpectraPlanner.build_plan("plan_offline", hyp.hypothesis_id)
    reg.register_experiment_plan(plan)

    assert len(reg._hypotheses) == 1
    assert len(reg._plans) == 1
