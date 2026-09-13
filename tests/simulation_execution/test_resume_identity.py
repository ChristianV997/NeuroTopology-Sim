"""Resume must never substitute an old computation for a changed request."""
from dataclasses import replace
import json
import sys

import pytest

from tools.simulation_execution.models import RunnerConfig, WorkUnit
from tools.simulation_execution.runner import run_plan


def setup_run(tmp_path):
    root = tmp_path / "outputs"
    source = tmp_path / "input.json"
    source.write_text('{"value":1}', encoding="utf-8")
    command = (sys.executable, "-c", "from pathlib import Path; "
               "Path('unit_manifest.json').write_text('{\"work_unit_id\":\"u\",\"complete\":true}'); "
               "p=Path('count.txt'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')")
    unit = WorkUnit.make("u", "writer", command, root / "u", seed=7,
                         input_references=(str(source),), config={"steps": 10})
    config = RunnerConfig(root, {"writer": command}, code_revision="revision-a", default_timeout_s=10)
    report = run_plan([unit], config)
    assert report["units"][0]["state"] == "PASS"
    return unit, config, source


@pytest.mark.parametrize("change", ["seed", "config", "command", "revision", "input", "environment", "legacy"])
def test_changed_computation_does_not_resume(tmp_path, change):
    unit, config, source = setup_run(tmp_path)
    if change == "seed":
        unit = replace(unit, seed=8)
    elif change == "config":
        unit = replace(unit, config={"steps": 20})
    elif change == "command":
        unit = replace(unit, argv=(*unit.argv[:2], unit.argv[2] + "; print('changed')"))
        config = replace(config, allowed_commands={"writer": unit.argv})
    elif change == "revision":
        config = replace(config, code_revision="revision-b")
    elif change == "input":
        source.write_text('{"value":2}', encoding="utf-8")
    elif change == "environment":
        config = replace(config, environment={"NTS_TEST_VARIANT": "changed"})
    else:
        path = config.output_root / "execution_manifest.json"
        old = json.loads(path.read_text())
        old["units"][0].pop("resume_identity", None)
        path.write_text(json.dumps(old), encoding="utf-8")
    report = run_plan([unit], config)
    assert report["units"][0]["state"] == "PASS"
    assert not report["units"][0].get("resumed", False)
    assert (unit.output_dir / "count.txt").read_text() == "2"


def test_revoked_command_is_blocked_even_with_valid_old_outputs(tmp_path):
    unit, config, _ = setup_run(tmp_path)
    report = run_plan([unit], replace(config, allowed_commands={}))
    assert report["units"][0]["state"] == "BLOCKED"
    assert (unit.output_dir / "count.txt").read_text() == "1"


def test_new_failed_dependency_prevents_cached_success(tmp_path):
    unit, config, _ = setup_run(tmp_path)
    command = (sys.executable, "-c", "raise SystemExit(1)")
    parent = WorkUnit.make("parent", "fail", command, config.output_root / "parent")
    config = replace(config, allowed_commands={**config.allowed_commands, "fail": command})
    report = run_plan([parent, replace(unit, dependencies=("parent",))], config)
    assert [record["state"] for record in report["units"]] == ["FAILED", "NOT_RUN"]
    assert (unit.output_dir / "count.txt").read_text() == "1"


def test_unchanged_computation_resumes_without_launch(tmp_path):
    unit, config, _ = setup_run(tmp_path)
    report = run_plan([unit], config)
    assert report["units"][0]["resumed"] is True
    assert (unit.output_dir / "count.txt").read_text() == "1"
