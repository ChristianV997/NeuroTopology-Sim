"""Tests for bridge adapters connecting release evaluator and claim gate."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from shared.research_claims.audit import load_and_audit
from tools.research_cycle.schema import ExperimentPlan
from tools.research_cycle_bridge.adapters import (
    adapt_bridge_to_claims,
    adapt_bridge_to_release_bundle,
)
from tools.research_cycle_bridge.builder import build_research_cycle_bridge
from tools.research_cycle_release.evaluator import evaluate_research_cycle_release
from tools.research_cycle_release.schema import DecisionState


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_release_evidence_evaluator_compatibility(tmp_path: Path) -> None:
    """Ensure bridge bundle adapts seamlessly to evaluate_research_cycle_release."""
    run = tmp_path / "run_adapter_test"
    _write_json(
        run / "RunRecord.json",
        {
            "run_id": "run_eval_001",
            "created_at": "2026-09-11T00:00:00Z",
            "source": "local_synthesizer",
            "data_mode": "synthetic",
            "synthetic": True,
            "git_commit": "d4dc5fc",
        },
    )
    _write_json(run / "summary.json", {"status": "complete"})
    _write_json(run / "metrics.json", {"loss": 0.05})
    _write_json(run / "validation_report.json", {"status": "complete", "checks_passed": True})

    bridge = build_research_cycle_bridge(run)
    bundle = adapt_bridge_to_release_bundle(bridge.to_dict())

    # Invoke the canonical evaluator
    report = evaluate_research_cycle_release(bundle, adapter_hint="generic")
    assert report.schema_version == "1.0"
    # The fixture omits a seed, so the bridge must remain operationally
    # incomplete rather than fabricating one merely to reach SYNTHETIC_ONLY.
    assert report.decision == DecisionState.EVIDENCE_INCOMPLETE
    assert report.synthetic_flag is True


def test_claims_gate_compatibility(tmp_path: Path) -> None:
    """Ensure generated research claims pass the repository's claim gate auditor."""
    run = tmp_path / "run_claims_test"
    _write_json(
        run / "RunRecord.json",
        {
            "run_id": "run_claim_001",
            "created_at": "2026-09-11T00:00:00Z",
            "source": "local_synthesizer",
            "data_mode": "synthetic",
            "synthetic": True,
        },
    )
    _write_json(run / "summary.json", {"status": "complete"})
    _write_json(run / "metrics.json", {"loss": 0.05})

    bridge = build_research_cycle_bridge(run)
    claims = adapt_bridge_to_claims(bridge.to_dict())

    assert len(claims) == 1
    claims_payload = {"claims": claims}
    audit_report = load_and_audit(json.dumps(claims_payload))
    assert audit_report["ok"] is True
    assert audit_report["counts"]["fail"] == 0


def test_experiment_plan_dataclass_integration(tmp_path: Path) -> None:
    """Ensure ExperimentPlan dataclass can be provided directly to the bridge builder."""
    run = tmp_path / "run_plan_test"
    _write_json(
        run / "RunRecord.json",
        {
            "run_id": "run_plan_001",
            "created_at": "2026-09-11T00:00:00Z",
            "source": "local_solver",
            "data_mode": "empirical",
            "synthetic": False,
        },
    )
    _write_json(run / "summary.json", {"status": "complete"})
    _write_json(run / "metrics.json", {"loss": 0.01})
    _write_json(run / "validation_report.json", {"status": "complete"})

    plan = ExperimentPlan(
        plan_id="plan-custom-001",
        hypothesis_id="hyp-custom-001",
        domain="higher_order_spectra",
        design_type="factorial",
        variables={"factor": "triadic"},
        target_sample_size=30,
        power_analysis={"alpha": 0.05, "power": 0.8},
        analysis_protocol="spectral_bispectrum",
        data_source="ds005620",
        is_synthetic=False,
    )

    bridge = build_research_cycle_bridge(run, experiment_plan=plan)
    assert bridge.experiment_plan["plan_id"] == "plan-custom-001"
    assert bridge.experiment_plan["domain"] == "higher_order_spectra"

    # Evidence graph should connect to custom plan
    egraph = bridge.evidence_graph
    plan_node = next(n for n in egraph["nodes"] if n["stage"] == "experiment_plan")
    assert plan_node["id"] == "plan-custom-001"
