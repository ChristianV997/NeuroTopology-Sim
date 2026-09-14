"""Offline end-to-end tests for the registered local solver bridge."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np
import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
REPO_ROOT = Path(__file__).resolve().parents[4]
for entry in (SRC, REPO_ROOT):
    if str(entry) in sys.path:
        sys.path.remove(str(entry))
    sys.path.insert(0, str(entry))

from awareness_studio.simulation_bridge import (  # noqa: E402
    BridgeRequest,
    BridgeState,
    RegisteredWorkload,
    ResourceBudget,
    SimulationBridge,
    WorkloadRegistry,
)
from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, simulate_fhn  # noqa: E402
from tools.simulation_execution.fhn_workload import DATASET_ID, SOURCE, prepare_spec  # noqa: E402


def _budget(timeout_s: float = 5.0) -> ResourceBudget:
    return ResourceBudget(
        timeout_s=timeout_s,
        memory_budget_bytes=256 * 1024 * 1024,
        disk_budget_bytes=32 * 1024 * 1024,
    )


def _fhn_case(tmp_path: Path, *, root_name: str = "outputs"):
    config = asdict(FHNConfig(duration_s=0.0005, dt_s=0.00001))
    workload, identity = prepare_spec(
        tmp_path / "fhn-spec.json",
        run_id="fhn-smoke",
        code_commit="revision-test",
        seed=7,
        configuration=config,
    )
    request = BridgeRequest(
        workload_id=workload.workload_id,
        run_id="fhn-smoke",
        code_commit="revision-test",
        configuration=config,
        seed=7,
        input_identity=identity,
        provenance={"dataset_id": DATASET_ID, "source": SOURCE, "data_mode": "synthetic"},
        output_root=tmp_path / root_name,
        resource_budget=_budget(),
        authorize_execution=True,
    )
    return workload, request


def test_registered_fhn_runs_through_executor_artifact_and_release_review(tmp_path: Path):
    workload, request = _fhn_case(tmp_path)
    result = SimulationBridge(WorkloadRegistry([workload])).run(request)

    assert result.state is BridgeState.ENGINEERING_EXECUTION_COMPLETE
    assert result.execution_state == "PASS"
    assert result.evidence_class == "synthetic_demo_only"
    assert result.lineage_report is not None
    assert result.lineage_report["status"] == "COMPLETE"
    assert result.lineage_report["provenance"]["evidence_class"] == "synthetic_demo_only"
    assert {item["relative_path"] for item in result.accepted_artifacts} == {
        "unit_manifest.json",
        "RunRecord.json",
        "summary.json",
        "trajectory.json",
    }

    trajectory = json.loads((request.output_root / request.run_id / "trajectory.json").read_text(encoding="utf-8"))
    expected = simulate_fhn(FHNConfig(**request.configuration))
    for name, values in zip(("time_s", "model_voltage_V", "recovery"), expected):
        np.testing.assert_array_equal(trajectory[name], values)

    record = json.loads((request.output_root / request.run_id / "RunRecord.json").read_text(encoding="utf-8"))
    assert record["schema_version"] == "0.1"
    assert record["synthetic"] is True
    assert record["evidence_class"] == "synthetic_demo_only"
    assert record["scientific_pass"] is False
    assert record["formal_bayes_factor"] is None

    review = result.release_review()
    assert review == result.release_review()
    assert review["decision"] == "SYNTHETIC_ONLY"
    assert review["bundle"]["evidence_classes"] == ["synthetic_demo_only"]
    assert review["scientific_pass_emitted"] is False
    assert review["bayes_factor_emitted"] is False
    json.dumps(result.to_dict(), sort_keys=True, allow_nan=False)
    json.dumps(review, sort_keys=True, allow_nan=False)


def test_registered_fhn_artifacts_are_deterministic(tmp_path: Path):
    workload, request_a = _fhn_case(tmp_path, root_name="outputs-a")
    bridge = SimulationBridge(WorkloadRegistry([workload]))
    first = bridge.run(request_a)

    request_b = BridgeRequest(**{**request_a.__dict__, "output_root": tmp_path / "outputs-b"})
    second = bridge.run(request_b)

    assert first.state is second.state is BridgeState.ENGINEERING_EXECUTION_COMPLETE
    assert [(item["relative_path"], item["sha256"]) for item in first.accepted_artifacts] == [
        (item["relative_path"], item["sha256"]) for item in second.accepted_artifacts
    ]


def test_bridge_defaults_to_planning(tmp_path: Path):
    workload, request = _fhn_case(tmp_path)
    request = BridgeRequest(**{**request.__dict__, "authorize_execution": False})
    result = SimulationBridge(WorkloadRegistry([workload])).run(request)
    assert result.state is BridgeState.PLANNING
    assert not request.output_root.exists()


def _fixture_workload(
    *,
    record_overrides: dict | None = None,
    summary_text: str = '{"status":"complete","evidence_class":"synthetic_demo_only"}',
    extra_text: str | None = None,
) -> RegisteredWorkload:
    record = {
        "schema_version": "0.1",
        "run_id": "fixture-run",
        "run_kind": "fixture",
        "created_at": "1970-01-01T00:00:00+00:00",
        "source": "local deterministic fixture",
        "dataset_id": "fixture-dataset",
        "data_mode": "synthetic",
        "git_commit": "fixture-revision",
        "seed": 11,
        "input_identity": "fixture-input",
        "input": {"identity": "fixture-input"},
        "configuration": {"mode": "fixture"},
        "metrics": {"value": 1.0},
        "artifacts": {"summary": "summary.json"},
        "synthetic": True,
        "evidence_class": "synthetic_demo_only",
        "scientific_pass": False,
        "formal_bayes_factor": None,
    }
    record.update(record_overrides or {})
    script = (
        "from pathlib import Path; import json; "
        f"Path('RunRecord.json').write_text({json.dumps(json.dumps(record))}, encoding='utf-8'); "
        f"Path('summary.json').write_text({json.dumps(summary_text)}, encoding='utf-8'); "
        "Path('unit_manifest.json').write_text(json.dumps({'work_unit_id':'fixture-run','complete':True}), encoding='utf-8')"
    )
    if extra_text is not None:
        script += f"; Path('unexpected.json').write_text({json.dumps(extra_text)}, encoding='utf-8')"
    return RegisteredWorkload("fixture", (sys.executable, "-c", script), ("unit_manifest.json", "RunRecord.json", "summary.json"))


def _fixture_request(root: Path) -> BridgeRequest:
    return BridgeRequest(
        workload_id="fixture",
        run_id="fixture-run",
        code_commit="fixture-revision",
        configuration={"mode": "fixture"},
        seed=11,
        input_identity="fixture-input",
        provenance={"dataset_id": "fixture-dataset", "source": "local deterministic fixture", "data_mode": "synthetic"},
        output_root=root,
        resource_budget=_budget(),
        authorize_execution=True,
    )


@pytest.mark.parametrize(
    "workload",
    [
        _fixture_workload(summary_text="{not-json"),
        _fixture_workload(summary_text='{"metric":NaN}'),
        _fixture_workload(record_overrides={"source": "other-source"}),
        _fixture_workload(extra_text='{"bad":NaN}'),
    ],
    ids=["malformed", "nonfinite", "provenance-mismatch", "unexpected-nonfinite"],
)
def test_invalid_or_inconsistent_artifacts_are_not_imported(tmp_path: Path, workload: RegisteredWorkload):
    result = SimulationBridge(WorkloadRegistry([workload])).run(_fixture_request(tmp_path / "outputs"))
    assert result.state is BridgeState.EXECUTION_FAILED
    assert result.accepted_artifacts == []
    assert result.scientific_pass is False
    assert result.formal_bayes_factor is None


def test_network_enabled_execution_is_rejected_before_child_launch(tmp_path: Path):
    workload, request = _fhn_case(tmp_path)
    request = BridgeRequest(**{**request.__dict__, "network_enabled": True})
    result = SimulationBridge(WorkloadRegistry([workload])).run(request)
    assert result.state is BridgeState.EXECUTION_NOT_AVAILABLE
    assert not request.output_root.exists()
