from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from awareness_studio.orchestrator import Orchestrator
from awareness_studio.orchestrator.registered_execution import execution_binding
from awareness_studio.research_cycle import ResearchCycleLedger
from awareness_studio.simulation_bridge import BridgeRequest, RegisteredWorkload, ResourceBudget, WorkloadRegistry


def case(tmp_path):
    repo = Path(__file__).resolve().parents[4]
    plan = json.loads((repo / "tests/research_cycle_preflight/fixtures/complete_plan.json").read_text())
    plan["plan"]["evidence_class_declared"] = "synthetic"
    record = {"run_id": "numerical-fixture", "created_at": "2026-09-13T00:00:00Z",
              "source": "local synthetic fixture", "dataset_id": plan["plan"]["dataset_id"],
              "data_mode": "synthetic", "synthetic": True, "git_commit": "v1.2.3",
              "seed": 42, "input_identity": "synthetic-sequence", "evidence_class": "synthetic_demo_only"}
    code = ("import json; from pathlib import Path; "
            f"Path('RunRecord.json').write_text({json.dumps(record)!r}); "
            "Path('summary.json').write_text(json.dumps({'sum_squares':sum(i*i for i in range(20))})); "
            "Path('unit_manifest.json').write_text('{\"work_unit_id\":\"numerical-fixture\",\"complete\":true}')")
    registry = WorkloadRegistry([RegisteredWorkload("fixture", (sys.executable, "-c", code))])
    request = BridgeRequest("fixture", "numerical-fixture", "v1.2.3", {"n": 20}, 42,
                            "synthetic-sequence", {key: record[key] for key in ("source", "dataset_id", "data_mode")},
                            tmp_path / "outputs", ResourceBudget(10, 512 * 1024**2, 8 * 1024**2),
                            authorize_execution=True)
    plan["execution_binding"] = execution_binding(request, registry)
    return request, registry, plan


def run(tmp_path, request, registry, plan):
    return Orchestrator().run_registered(request, registry, plan,
                                         ledger_path=tmp_path / "ledger.sqlite3",
                                         now="2026-09-13T00:00:00Z")


def test_registered_execution_persists_actual_artifacts_and_review(tmp_path):
    request, registry, plan = case(tmp_path)
    result = run(tmp_path, request, registry, plan)
    assert result["state"] == "ENGINEERING_EXECUTION_COMPLETE"
    assert json.loads((request.output_root / request.run_id / "summary.json").read_text())["sum_squares"] == 2470
    ledger = ResearchCycleLedger(result["ledger_path"])
    assert ledger.recover(result["cycle_id"])
    events = ledger.events(result["cycle_id"])
    validation = next(e for e in events if e.event_type == "validation_outcome")
    assert len(validation.payload["accepted_artifacts"]) == 3
    assert events[-1].payload["release_authorized"] is False
    graph = result["graph"]
    assert len([n for n in graph["nodes"] if n["node_type"] == "artifact"]) == 3
    assert all(n["evidence_class"] in {"synthetic", "unknown"} for n in graph["nodes"])
    assert not any(edge["edge_type"] == "supports" for edge in graph["edges"])
    assert result["release_review"]["decision"] == "EVIDENCE_INCOMPLETE"
    assert result["release_review"]["bundle"]["input_provenance_complete"] is None
    assert result["release_review"]["bundle"]["network_policy_violated"] is None
    assert any(e.event_type == "evidence_graph_update" for e in events)
    assert result["scientific_pass"] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("change", ["seed", "config", "missing_plan", "empirical", "unbounded"])
def test_admission_blocks_before_process_launch(tmp_path, change):
    request, registry, plan = case(tmp_path)
    if change == "seed":
        request = replace(request, seed=9)
    elif change == "config":
        request = replace(request, configuration={"n": 999})
    elif change == "missing_plan":
        plan.pop("plan")
    elif change == "empirical":
        plan["plan"]["evidence_class_declared"] = "empirical"
    else:
        request = replace(request, resource_budget=ResourceBudget(10, None, None))
        plan["execution_binding"] = execution_binding(request, registry)
    result = run(tmp_path, request, registry, plan)
    assert result["state"] == "BLOCKED"
    assert not request.output_root.exists()
    assert not any(node["node_type"] in {"run", "artifact"} for node in result["graph"]["nodes"])


def test_planning_does_not_execute_and_authorized_repeat_resumes(tmp_path):
    request, registry, plan = case(tmp_path)
    planning = run(tmp_path, replace(request, authorize_execution=False), registry, plan)
    assert planning["state"] == "PLANNING"
    assert not request.output_root.exists()
    first = run(tmp_path, request, registry, plan)
    second = run(tmp_path, request, registry, plan)
    assert first["cycle_id"] == second["cycle_id"] == planning["cycle_id"]
    assert second["execution"]["runner_manifest"]["units"][0]["resumed"] is True
