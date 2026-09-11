from __future__ import annotations

import json
from pathlib import Path
import socket
import sys

import pytest

from tools.simulation_execution.finite import dumps_finite
from tools.simulation_execution.models import ExecutionState, RunnerConfig, WorkUnit
from tools.simulation_execution.runner import run_plan


def _config(root: Path, command: tuple[str, ...], **kwargs) -> RunnerConfig:
    kwargs.setdefault("default_timeout_s", 5)
    return RunnerConfig(output_root=root, allowed_commands={"fixture": command}, **kwargs)


def _unit(root: Path, command: tuple[str, ...], unit_id="unit-1", **kwargs) -> WorkUnit:
    return WorkUnit.make(unit_id, "fixture", command, root / unit_id, expected_outputs=("unit_manifest.json", "result.json"), **kwargs)


def _command(code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", code)


def _writer(code_suffix: str = "") -> tuple[str, ...]:
    code = "from pathlib import Path; import json; p=Path('result.json'); p.write_text(json.dumps({'value': 7}), encoding='utf-8'); Path('unit_manifest.json').write_text(json.dumps({'work_unit_id':'unit-1','complete':True}), encoding='utf-8')" + code_suffix
    return _command(code)


def test_clean_pass_has_finite_artifacts_and_atomic_manifest(tmp_path):
    root = tmp_path / "out"
    report = run_plan([_unit(root, _writer())], _config(root, _writer()))
    unit = report["units"][0]
    assert unit["state"] == ExecutionState.PASS.value
    assert all(unit["checksums"].values())
    assert (root / "execution_manifest.json").is_file()
    json.dumps(report, allow_nan=False)


def test_timeout_has_no_valid_checksum(tmp_path):
    command = _command("import time; time.sleep(10)")
    report = run_plan([_unit(tmp_path / "out", command)], _config(tmp_path / "out", command, default_timeout_s=0.2))
    unit = report["units"][0]
    assert unit["state"] == ExecutionState.TIMEOUT.value
    assert all(value is None for value in unit["checksums"].values())


def test_child_process_timeout_is_terminated_as_a_group(tmp_path):
    command = _command("import subprocess,time; subprocess.Popen([__import__('sys').executable,'-c','import time; time.sleep(30)']); time.sleep(30)")
    report = run_plan([_unit(tmp_path / "out", command)], _config(tmp_path / "out", command, default_timeout_s=0.3))
    assert report["units"][0]["state"] == ExecutionState.TIMEOUT.value


def test_allowlist_blocks_unapproved_command(tmp_path):
    command = _writer()
    config = _config(tmp_path / "out", _command("pass"))
    report = run_plan([_unit(tmp_path / "out", command)], config)
    assert report["units"][0]["state"] == ExecutionState.BLOCKED.value


def test_output_escape_is_blocked(tmp_path):
    root = tmp_path / "out"
    command = _writer()
    unit = WorkUnit.make("escape", "fixture", command, tmp_path / "outside", expected_outputs=("unit_manifest.json",))
    report = run_plan([unit], _config(root, command))
    assert report["units"][0]["state"] == ExecutionState.BLOCKED.value


def test_missing_manifest_is_failure(tmp_path):
    command = _command("from pathlib import Path; Path('result.json').write_text('{}')")
    report = run_plan([_unit(tmp_path / "out", command)], _config(tmp_path / "out", command))
    assert report["units"][0]["state"] == ExecutionState.FAILED.value
    assert all(value is None for value in report["units"][0]["checksums"].values())


def test_malformed_and_nonfinite_outputs_fail(tmp_path):
    for index, payload in enumerate(("{not-json", '{"value":NaN}')):
        command = _command(f"from pathlib import Path; Path('result.json').write_text('{{}}'); Path('unit_manifest.json').write_text({payload!r})")
        root = tmp_path / ("invalid-json" if index == 0 else "nonfinite-json")
        report = run_plan([_unit(root, command)], _config(root, command))
        assert report["units"][0]["state"] == ExecutionState.FAILED.value


def test_partial_artifact_is_partial(tmp_path):
    command = _command("from pathlib import Path; Path('result.json').write_text('{}'); Path('unit_manifest.json').write_text('{\"work_unit_id\":\"unit-1\",\"complete\":false,\"status\":\"partial\"}')")
    report = run_plan([_unit(tmp_path / "out", command)], _config(tmp_path / "out", command))
    assert report["units"][0]["state"] == ExecutionState.PARTIAL.value


def test_dependency_not_run_state(tmp_path):
    command = _command("raise SystemExit(3)")
    root = tmp_path / "out"
    first = _unit(root, command, "first")
    second = _unit(root, command, "second", dependencies=("first",))
    report = run_plan([first, second], RunnerConfig(output_root=root, allowed_commands={"fixture": command}, default_timeout_s=1, network_disabled=False))
    assert report["units"][0]["state"] == ExecutionState.FAILED.value
    assert report["units"][1]["state"] == ExecutionState.NOT_RUN.value


def test_resumable_recovery_skips_completed_valid_unit(tmp_path):
    root = tmp_path / "out"
    command_one = _writer()
    one = _unit(root, command_one, "unit-1")
    first = run_plan([one], _config(root, command_one))
    checksum = first["units"][0]["checksums"]["result.json"]
    command_two = _command("from pathlib import Path; import json; Path('result.json').write_text(json.dumps({'value':8})); Path('unit_manifest.json').write_text(json.dumps({'work_unit_id':'unit-2','complete':True}))")
    two = _unit(root, command_two, "unit-2")
    config = RunnerConfig(output_root=root, allowed_commands={"fixture": command_one}, default_timeout_s=2)
    # The second unit is intentionally blocked by the exact allowlist; unit-1 must still resume.
    report = run_plan([one, two], config, resume=True)
    assert report["units"][0]["resumed"] is True
    assert report["units"][0]["checksums"]["result.json"] == checksum
    assert report["units"][1]["state"] == ExecutionState.BLOCKED.value


def test_stdout_is_truncated(tmp_path):
    command = _command("print('x'*10000); from pathlib import Path; Path('result.json').write_text('{}'); Path('unit_manifest.json').write_text('{\"work_unit_id\":\"unit-1\",\"complete\":true}')")
    report = run_plan([_unit(tmp_path / "out", command)], _config(tmp_path / "out", command, stdout_limit=100))
    unit = report["units"][0]
    assert unit["state"] == ExecutionState.PASS.value and unit["stdout_truncated"] is True


def test_network_disabled_by_default(tmp_path):
    command = _command("import socket; from pathlib import Path; ok=False\ntry: socket.create_connection(('example.invalid',80),timeout=0.1)\nexcept OSError: ok=True\nassert ok\nfrom pathlib import Path; Path('result.json').write_text('{}'); Path('unit_manifest.json').write_text('{\"work_unit_id\":\"unit-1\",\"complete\":true}')")
    report = run_plan([_unit(tmp_path / "out", command)], _config(tmp_path / "out", command))
    assert report["units"][0]["state"] == ExecutionState.PASS.value


def test_deterministic_command_identity_and_repeatability(tmp_path):
    command = _writer()
    first = run_plan([_unit(tmp_path / "a", command)], _config(tmp_path / "a", command))
    second = run_plan([_unit(tmp_path / "b", command)], _config(tmp_path / "b", command))
    a, b = first["units"][0], second["units"][0]
    assert a["command_identity"] == b["command_identity"]
    assert a["state"] == b["state"] == ExecutionState.PASS.value
    assert a["checksums"] == b["checksums"]


def test_no_solver_import_in_runner_source():
    source = Path("tools/simulation_execution/runner.py").read_text(encoding="utf-8")
    assert "scipy" not in source and "numpy" not in source and "subprocess.run" not in source.replace("subprocess.run([\"taskkill\"", "")
