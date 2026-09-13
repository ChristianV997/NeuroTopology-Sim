from dataclasses import replace
import hashlib
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


def literature_context(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Synthetic test-only literature fixture; no scientific evidence.", encoding="utf-8")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "source": {"source_id": "fixture-source", "identifier": "https://example.invalid/fixture",
                   "identifier_type": "url", "title": "Synthetic test-only source",
                   "publication_type": "technical_report", "content_checksum": checksum,
                   "retrieval_timestamp": "2026-09-13T00:00:00Z"},
        "snapshot": {"snapshot_id": "fixture-snapshot", "source_id": "fixture-source",
                     "kind": "full_local_snapshot", "local_path": str(path), "content_checksum": checksum,
                     "captured_at": "2026-09-13T00:00:00Z"},
        "claim": {"claim_id": "fixture-claim", "source_id": "fixture-source",
                  "claim_text": "Test-only proposed arithmetic relationship", "claim_kind": "review_required"},
    }


def test_local_literature_links_to_experiment_and_execution(tmp_path):
    request, registry, plan = case(tmp_path)
    plan["literature_context"] = literature_context(tmp_path)
    result = run(tmp_path, request, registry, plan)
    assert result["state"] == "ENGINEERING_EXECUTION_COMPLETE"
    records = ResearchCycleLedger(result["ledger_path"]).records(result["cycle_id"])
    assert {r.record_type for r in records} == {"source_snapshot", "claim", "hypothesis", "experiment_spec"}
    claim = next(r for r in records if r.record_type == "claim")
    assert claim.status == "REVIEW_REQUIRED"
    assert claim.evidence_class.value == "hypothesis"
    graph = result["graph"]
    assert len([n for n in graph["nodes"] if n["node_type"] == "experiment"]) == 1
    assert all(e["edge_type"] != "supports" for e in graph["edges"])
    repeated = run(tmp_path, request, registry, plan)
    assert repeated["cycle_id"] == result["cycle_id"]
    assert repeated["state"] == "ENGINEERING_EXECUTION_COMPLETE"


@pytest.mark.parametrize("change", ["retracted", "source_mismatch", "tampered"])
def test_invalid_literature_blocks_before_execution(tmp_path, change):
    request, registry, plan = case(tmp_path)
    context = literature_context(tmp_path)
    plan["literature_context"] = context
    if change == "retracted":
        context["source"]["status"] = "retracted"
    elif change == "source_mismatch":
        context["claim"]["source_id"] = "another-source"
    else:
        Path(context["snapshot"]["local_path"]).write_text("changed bytes", encoding="utf-8")
    result = run(tmp_path, request, registry, plan)
    assert result["state"] == "BLOCKED"
    assert not request.output_root.exists()
    assert not ResearchCycleLedger(result["ledger_path"]).records(result["cycle_id"])


def test_existing_fhn_solver_runs_through_registered_cycle(tmp_path):
    from tools.simulation_execution.fhn_workload import prepare_spec, SOURCE, DATASET_ID
    from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, simulate_fhn
    from dataclasses import asdict
    import numpy as np
    request, _, plan = case(tmp_path)
    parameters = asdict(FHNConfig(duration_s=0.001, dt_s=0.00001))
    workload, checksum = prepare_spec(tmp_path / "fhn-spec.json", run_id="fhn-test",
                                       code_commit=request.code_commit, seed=request.seed, configuration=parameters)
    registry = WorkloadRegistry([workload])
    request = replace(request, run_id="fhn-test", workload_id=workload.workload_id,
                      configuration=parameters, input_identity=checksum,
                      provenance={"dataset_id": DATASET_ID, "source": SOURCE, "data_mode": "synthetic"})
    plan["plan"]["dataset_id"] = DATASET_ID
    plan["plan"]["dataset_checksum"] = checksum
    plan["plan"]["research_question"] = "Does the bounded FHN adapter preserve the existing solver trajectory?"
    plan["execution_binding"] = execution_binding(request, registry)
    result = run(tmp_path, request, registry, plan)
    assert result["state"] == "ENGINEERING_EXECUTION_COMPLETE", result
    trajectory = json.loads((request.output_root / request.run_id / "trajectory.json").read_text())
    expected = simulate_fhn(FHNConfig(**parameters))
    for name, values in zip(("time_s", "model_voltage_V", "recovery"), expected):
        np.testing.assert_array_equal(trajectory[name], values)
    record = json.loads((request.output_root / request.run_id / "RunRecord.json").read_text())
    assert record["schema_version"] == "0.1"
    assert record["synthetic"] is True
    assert any("normalizes" in note for note in record["limitations"])
    assert result["release_review"]["decision"] == "EVIDENCE_INCOMPLETE"
    repeated = run(tmp_path, request, registry, plan)
    assert repeated["execution"]["runner_manifest"]["units"][0]["resumed"] is True


def test_fhn_worker_rejects_tampered_spec_before_output(tmp_path):
    from tools.simulation_execution.fhn_workload import execute_spec
    spec = tmp_path / "spec.json"
    spec.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        execute_spec(spec, "0" * 64, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("parameter,value", [("duration_s", 100), ("dt_s", 0), ("input_current", float("nan"))])
def test_fhn_preparation_rejects_unbounded_or_invalid_parameters(tmp_path, parameter, value):
    from tools.simulation_execution.fhn_workload import prepare_spec
    config = {"duration_s": 0.001, "dt_s": 0.00001, "input_current": 1.2,
              "resting_potential_V": -0.07, "spike_scale_V": 0.1}
    config[parameter] = value
    with pytest.raises(ValueError):
        prepare_spec(tmp_path / "spec.json", run_id="bounded-test", code_commit="test-revision", seed=1, configuration=config)
    assert not (tmp_path / "spec.json").exists()
