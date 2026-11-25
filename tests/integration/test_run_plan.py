"""Run-plan construction: graceful degradation when an adapter's optional
dependency is unavailable, with a stated reason rather than a silent
drop."""
from __future__ import annotations

from tools.integration_bridge import run_plan


def test_all_steps_run_when_every_adapter_available():
    available = {"spatial_topology": True, "graph_beta1": True, "scalar_chirality": True, "bayesian_falsification": True}
    plan = run_plan.build_plan(available)
    assert len(plan.steps) == 4
    assert plan.skipped == ()


def test_step_skipped_with_reason_when_adapter_unavailable():
    available = {"spatial_topology": True, "graph_beta1": False, "scalar_chirality": True, "bayesian_falsification": True}
    plan = run_plan.build_plan(available)
    skipped_names = {step.name for step in plan.skipped}
    assert "graph_beta1" in skipped_names
    skipped_step = next(step for step in plan.skipped if step.name == "graph_beta1")
    assert skipped_step.reason_if_skipped is not None
    assert "graph_beta1" not in {step.name for step in plan.steps}


def test_all_adapters_absent_skips_everything_without_raising():
    available = {name: False for name in ("spatial_topology", "graph_beta1", "scalar_chirality", "bayesian_falsification")}
    plan = run_plan.build_plan(available)
    assert plan.steps == ()
    assert len(plan.skipped) == 4
    assert all(step.reason_if_skipped for step in plan.skipped)


def test_requested_steps_narrows_the_candidate_set():
    available = {"spatial_topology": True, "graph_beta1": True, "scalar_chirality": True, "bayesian_falsification": True}
    plan = run_plan.build_plan(available, requested_steps=("spatial_winding_and_charge",))
    assert {step.name for step in plan.steps} == {"spatial_winding_and_charge"}
    assert plan.skipped == ()


def test_plan_to_dict_is_json_serializable():
    import json

    available = {"spatial_topology": True, "graph_beta1": False, "scalar_chirality": True, "bayesian_falsification": True}
    plan = run_plan.build_plan(available)
    json.dumps(plan.to_dict())  # must not raise
