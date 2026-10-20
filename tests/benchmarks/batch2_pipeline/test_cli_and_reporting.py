"""CLI generate/validate and artifact pack shape."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarks.batch2_pipeline.reporting import generate
from tools.benchmarks.batch2_pipeline.schema import REQUIRED_OUTPUT_FILES
from tools.benchmarks.batch2_pipeline.validator import validate_root

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_batch2_pipeline_cli2",
    REPO_ROOT / "scripts" / "benchmark_batch2_pipeline.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_generate_writes_required_files(tmp_path):
    out = tmp_path / "out"
    report = generate(out, seed=0, size=8, repetitions=1)
    assert report["all_equivalent"] is True
    for rel in REQUIRED_OUTPUT_FILES:
        assert (out / rel).exists(), rel
    validation = validate_root(out)
    assert validation["ok"] is True, validation["violations"]


def test_validate_cli(tmp_path, capsys):
    out = tmp_path / "out"
    generate(out, seed=0, size=8, repetitions=1)
    rc = cli.main(["validate", "--root", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True


def test_generate_cli(tmp_path, capsys):
    out = tmp_path / "gen"
    rc = cli.main(["generate", "--out", str(out), "--size", "8", "--repetitions", "1"])
    assert rc == 0
    assert "schema=batch2_pipeline/v1" in capsys.readouterr().out
    assert (out / "batch2_pipeline_report.json").exists()


def test_unknown_target_exits_nonzero(capsys):
    """Regression: typos must not look like a successful empty benchmark."""
    rc = cli.main(["--target", "does_not_exist", "--json", "--size", "8", "--repetitions", "1"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "unknown target" in err


def test_isolated_unknown_target_exits_nonzero(capsys):
    rc = cli.main(
        [
            "--isolated",
            "--target",
            "does_not_exist",
            "--json",
            "--per-target-timeout-s",
            "5",
        ]
    )
    out = capsys.readouterr().out
    report = json.loads(out)
    assert rc != 0
    assert report["num_targets"] == 0
    assert "unknown target" in (report.get("error") or "")


def test_cli_exit_code_fails_on_hard_statuses():
    """Isolated timeout/crash/budget overrun must flip the process exit code."""
    assert cli._cli_exit_code({"all_equivalent": True, "all_within_budget": True, "summary": {}, "num_targets": 1}) == 0
    assert cli._cli_exit_code({"all_equivalent": False, "summary": {}, "num_targets": 1}) == 1
    assert cli._cli_exit_code({"all_equivalent": True, "all_within_budget": False, "summary": {}, "num_targets": 1}) == 1
    assert cli._cli_exit_code({"all_equivalent": True, "summary": {"timeout": 1}, "num_targets": 1}) == 1
    assert cli._cli_exit_code({"all_equivalent": True, "summary": {"child_crash": 1}, "num_targets": 1}) == 1
    assert cli._cli_exit_code({"error": "unknown target", "num_targets": 0, "summary": {}}) == 2
