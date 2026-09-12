from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import threading

from tools.simulation_adapters.adapter import execute_adapter
from tools.simulation_adapters.finite import dumps_finite
from tools.simulation_adapters.models import AdapterRequest, AdapterState, ResourceBudget


def _request(root: Path, code: str, **kwargs) -> AdapterRequest:
    command = (sys.executable, "-c", code)
    return AdapterRequest.make(workload_id="fixture", command=command, allowed_commands={"fixture": command}, code_commit="abc123", configuration={"mode": "fixture"}, seed=7, input_identity="input-1", provenance={"source": "local_fixture", "data_mode": "synthetic", "dataset_id": "fixture"}, output_root=root, evidence_class="engineering_fixture", resource_budget=ResourceBudget(timeout_s=kwargs.pop("timeout_s", 3), max_stdout_bytes=kwargs.pop("max_stdout_bytes", 512), max_stderr_bytes=512, **kwargs))


def _pass_code(unit_id="ignored"):
    return "from pathlib import Path; import json; Path('result.json').write_text(json.dumps({'value': 7})); Path('completion_manifest.json').write_text(json.dumps({'complete': True}))"


def test_validated_pass_emits_run_record_and_artifact_manifest(tmp_path):
    result = execute_adapter(_request(tmp_path / "run", _pass_code()))
    assert result.state is AdapterState.PASS
    assert (tmp_path / "run" / "RunRecord.json").is_file()
    assert (tmp_path / "run" / "artifact_manifest.json").is_file()
    record = json.loads((tmp_path / "run" / "RunRecord.json").read_text())
    assert record["schema_version"] == "0.1" and record["scientific_pass"] is False and record["formal_bayes_factor"] is None
    assert record["resource_budget"]["timeout_s"] == 3 and record["network_disabled"] is True
    assert all(result.report["checksums"].values())


def test_malformed_output_fails_closed(tmp_path):
    code = "from pathlib import Path; Path('result.json').write_text('{bad'); Path('completion_manifest.json').write_text('{\"complete\":true}')"
    result = execute_adapter(_request(tmp_path / "run", code))
    assert result.state is AdapterState.FAILED and not (tmp_path / "run" / "RunRecord.json").exists()


def test_timeout_has_no_checksums(tmp_path):
    result = execute_adapter(_request(tmp_path / "run", "import time; time.sleep(10)", timeout_s=0.2))
    assert result.state is AdapterState.TIMEOUT
    assert all(value is None for value in result.report["checksums"].values())


def test_missing_provenance_is_blocked(tmp_path):
    request = _request(tmp_path / "run", _pass_code())
    request = AdapterRequest.make(workload_id=request.workload_id, command=request.command, allowed_commands=request.allowed_commands, code_commit="", configuration=request.configuration, seed=request.seed, input_identity=request.input_identity, provenance={"source": "", "data_mode": "synthetic"}, output_root=request.output_root, evidence_class=request.evidence_class)
    assert execute_adapter(request).state is AdapterState.BLOCKED


def test_nonfinite_output_fails(tmp_path):
    code = "from pathlib import Path; Path('result.json').write_text('{\"value\": NaN}'); Path('completion_manifest.json').write_text('{\"complete\":true}')"
    assert execute_adapter(_request(tmp_path / "run", code)).state is AdapterState.FAILED


def test_interrupted_execution_is_partial(tmp_path):
    event = threading.Event(); event.set()
    result = execute_adapter(_request(tmp_path / "run", _pass_code()), interrupt_event=event)
    assert result.state is AdapterState.PARTIAL


def test_output_escape_is_blocked(tmp_path):
    request = _request(tmp_path / "run", _pass_code())
    request = AdapterRequest.make(workload_id=request.workload_id, command=request.command, allowed_commands=request.allowed_commands, code_commit=request.code_commit, configuration=request.configuration, seed=request.seed, input_identity=request.input_identity, provenance=request.provenance, output_root=request.output_root, evidence_class=request.evidence_class, expected_outputs=("../escape.json",))
    assert execute_adapter(request).state is AdapterState.BLOCKED


def test_not_implemented_state_is_explicit(tmp_path):
    request = _request(tmp_path / "run", _pass_code())
    request = AdapterRequest.make(workload_id="unknown", command=request.command, allowed_commands={}, code_commit=request.code_commit, configuration=request.configuration, seed=request.seed, input_identity=request.input_identity, provenance=request.provenance, output_root=request.output_root, evidence_class=request.evidence_class)
    assert execute_adapter(request).state is AdapterState.NOT_IMPLEMENTED


def test_deterministic_replay_skips_valid_outputs(tmp_path):
    request = _request(tmp_path / "run", _pass_code())
    first = execute_adapter(request); second = execute_adapter(request)
    assert first.state is second.state is AdapterState.PASS
    assert second.report["resumed"] is True
    assert first.report["command_identity"] == second.report["command_identity"]
    assert first.report["checksums"] == second.report["checksums"]


def test_network_disabled_python_guard(tmp_path):
    code = "import socket; from pathlib import Path; ok=False\ntry: socket.create_connection(('example.invalid',80),timeout=.1)\nexcept OSError: ok=True\nassert ok\nPath('result.json').write_text('{}'); Path('completion_manifest.json').write_text('{\"complete\":true}')"
    assert execute_adapter(_request(tmp_path / "run", code)).state is AdapterState.PASS


def test_stdout_truncation_and_finite_report(tmp_path):
    code = "print('x'*5000); " + _pass_code()
    result = execute_adapter(_request(tmp_path / "run", code, max_stdout_bytes=64))
    assert result.state is AdapterState.PASS and result.report["stdout_truncated"] is True
    json.dumps(result.report, allow_nan=False)
    assert "NaN" not in dumps_finite(result.report)


def test_child_timeout_uses_process_isolation(tmp_path):
    code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); time.sleep(20)"
    result = execute_adapter(_request(tmp_path / "run", code, timeout_s=.3))
    assert result.state is AdapterState.TIMEOUT
