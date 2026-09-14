"""Hermetic tests for the Awareness Studio simulation bridge."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from awareness_studio.simulation_bridge import (  # noqa: E402
    BridgeRequest,
    BridgeState,
    RegisteredWorkload,
    ResourceBudget,
    SimulationBridge,
    WorkloadRegistry,
)


def _record(run_id: str, commit: str, seed: int, input_identity: str, *, synthetic=True) -> dict:
    return {
        "run_id": run_id,
        "run_kind": "fixture",
        "created_at": "2026-09-12T00:00:00Z",
        "source": "local deterministic fixture",
        "dataset_id": input_identity,
        "data_mode": "synthetic" if synthetic else "simulation",
        "synthetic": synthetic,
        "git_commit": commit,
        "seed": seed,
        "input_identity": input_identity,
        "claim_scope": "engineering_fixture_only",
        "evidence_class": "synthetic_demo_only" if synthetic else "computational_model",
    }


def _command(code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", code)


def _workload(code: str, *, expected=("unit_manifest.json", "RunRecord.json", "summary.json"), workload_id="fixture"):
    return RegisteredWorkload(workload_id, _command(code), expected)


def _request(root: Path, workload_id="fixture", *, authorize=True, network=False, timeout=5, **kwargs):
    values = dict(
        workload_id=workload_id,
        run_id="run-001",
        code_commit="abc1234",
        configuration={"mode": "fixture", "version": 1},
        seed=7,
        input_identity="input-fixture-001",
        provenance={"dataset_id": "input-fixture-001", "source": "local deterministic fixture", "data_mode": "synthetic"},
        output_root=root,
        resource_budget=ResourceBudget(timeout_s=timeout, memory_budget_bytes=None, disk_budget_bytes=8 * 1024 * 1024),
        authorize_execution=authorize,
        network_enabled=network,
    )
    values.update(kwargs)
    return BridgeRequest(**values)


def _writer(*, malformed=False, nonfinite=False, missing_provenance=False, delay=False, synthetic=True, data_mode=None):
    record = _record("run-001", "abc1234", 7, "input-fixture-001", synthetic=synthetic)
    if data_mode is not None:
        record["data_mode"] = data_mode
    if missing_provenance:
        record.pop("source")
    record_text = json.dumps(record)
    summary_text = "{not-json" if malformed else ('{"metric": NaN}' if nonfinite else '{"status":"complete"}')
    sleep = "import time; time.sleep(10);" if delay else ""
    return (
        f"from pathlib import Path; import json; {sleep}"
        f"Path('RunRecord.json').write_text({record_text!r}, encoding='utf-8');"
        f"Path('summary.json').write_text({summary_text!r}, encoding='utf-8');"
        "Path('unit_manifest.json').write_text(json.dumps({'work_unit_id':'run-001','complete':True}), encoding='utf-8')"
    )


def test_default_is_planning_and_does_not_create_output(tmp_path):
    registry = WorkloadRegistry([_workload(_writer())])
    result = SimulationBridge(registry).run(_request(tmp_path, authorize=False))
    assert result.state is BridgeState.PLANNING
    assert not (tmp_path / "run-001").exists()
    assert result.to_dict()["metrics"] is None


def test_successful_deterministic_synthetic_run_is_engineering_only(tmp_path):
    registry = WorkloadRegistry([_workload(_writer())])
    result = SimulationBridge(registry).run(_request(tmp_path))
    assert result.state is BridgeState.ENGINEERING_EXECUTION_COMPLETE
    assert result.execution_state == "PASS"
    assert {item["relative_path"] for item in result.accepted_artifacts} == {"unit_manifest.json", "RunRecord.json", "summary.json"}
    assert result.evidence_class == "synthetic_demo_only"
    payload = json.dumps(result.to_dict(), sort_keys=True, allow_nan=False)
    assert result.to_dict()["scientific_pass"] is False
    assert "NaN" not in payload and "Infinity" not in payload


def test_deterministic_repeat_has_same_artifact_checksums(tmp_path):
    registry = WorkloadRegistry([_workload(_writer())])
    first = SimulationBridge(registry).run(_request(tmp_path / "a"))
    second = SimulationBridge(registry).run(_request(tmp_path / "b"))
    assert [(x["relative_path"], x["sha256"]) for x in first.accepted_artifacts] == [(x["relative_path"], x["sha256"]) for x in second.accepted_artifacts]


def test_non_synthetic_complete_artifacts_are_ready_for_review_not_scientific_pass(tmp_path):
    registry = WorkloadRegistry([_workload(_writer(synthetic=False))])
    provenance = {"dataset_id": "input-fixture-001", "source": "local deterministic fixture", "data_mode": "simulation"}
    result = SimulationBridge(registry).run(_request(tmp_path, provenance=provenance))
    assert result.state is BridgeState.EVIDENCE_READY_FOR_REVIEW
    assert result.to_dict()["scientific_pass"] is False
    assert result.to_dict()["formal_bayes_factor"] is None


def test_proxy_complete_artifacts_are_explicitly_proxy_not_empirical(tmp_path):
    registry = WorkloadRegistry([_workload(_writer(synthetic=False, data_mode="proxy"))])
    provenance = {"dataset_id": "input-fixture-001", "source": "local deterministic fixture", "data_mode": "proxy"}
    result = SimulationBridge(registry).run(_request(tmp_path, provenance=provenance))
    assert result.state is BridgeState.EVIDENCE_READY_FOR_REVIEW
    assert result.evidence_class == "proxy"
    payload = result.to_dict()
    assert payload["scientific_pass"] is False
    assert payload["formal_bayes_factor"] is None


@pytest.mark.parametrize("kwargs", [{"malformed": True}, {"nonfinite": True}, {"missing_provenance": True}])
def test_malformed_or_unprovenanced_output_is_not_imported(tmp_path, kwargs):
    registry = WorkloadRegistry([_workload(_writer(**kwargs))])
    result = SimulationBridge(registry).run(_request(tmp_path))
    assert result.state is BridgeState.EXECUTION_FAILED
    assert result.accepted_artifacts == []


def test_timeout_preserves_canonical_failure_state(tmp_path):
    registry = WorkloadRegistry([_workload(_writer(delay=True))])
    result = SimulationBridge(registry).run(_request(tmp_path, timeout=0.1))
    assert result.state is BridgeState.EXECUTION_FAILED
    assert result.execution_state == "TIMEOUT"
    assert result.accepted_artifacts == []


def test_network_enabled_request_is_denied_before_execution(tmp_path):
    registry = WorkloadRegistry([_workload(_writer())])
    result = SimulationBridge(registry).run(_request(tmp_path, network=True))
    assert result.state is BridgeState.EXECUTION_NOT_AVAILABLE
    assert not (tmp_path / "run-001").exists()


def test_output_escape_is_rejected_at_registration():
    with pytest.raises(ValueError, match="escapes"):
        WorkloadRegistry([_workload(_writer(), expected=("../escape.json", "RunRecord.json", "summary.json"))])


def test_unregistered_workload_and_missing_request_provenance_are_unavailable(tmp_path):
    bridge = SimulationBridge(WorkloadRegistry())
    result = bridge.run(_request(tmp_path, workload_id="not-registered"))
    assert result.state is BridgeState.EXECUTION_NOT_AVAILABLE
    registry = WorkloadRegistry([_workload(_writer())])
    request = _request(tmp_path, provenance={"dataset_id": "", "source": "", "data_mode": ""})
    assert SimulationBridge(registry).run(request).state is BridgeState.EXECUTION_NOT_AVAILABLE


def test_missing_canonical_runner_is_reported(monkeypatch, tmp_path):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name.startswith("tools.simulation_execution"):
            raise ModuleNotFoundError("fixture hides canonical runner")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    registry = WorkloadRegistry([_workload(_writer())])
    result = SimulationBridge(registry).run(_request(tmp_path))
    assert result.state is BridgeState.EXECUTION_NOT_AVAILABLE


def test_bridge_source_has_no_network_or_subprocess_implementation():
    source = (Path(__file__).resolve().parents[2] / "src" / "awareness_studio" / "simulation_bridge" / "bridge.py").read_text(encoding="utf-8")
    assert "urllib" not in source and "requests" not in source and "subprocess" not in source
