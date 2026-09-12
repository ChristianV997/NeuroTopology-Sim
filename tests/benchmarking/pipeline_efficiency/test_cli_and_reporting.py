"""CLI generate/validate, reporting artifacts, and validator gates."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarking.pipeline_efficiency.harness import run_all
from tools.benchmarking.pipeline_efficiency.reporting import generate
from tools.benchmarking.pipeline_efficiency.schema import REQUIRED_OUTPUT_FILES
from tools.benchmarking.pipeline_efficiency.validator import validate_report, validate_root

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_pipeline_efficiency_cli2",
    REPO_ROOT / "scripts" / "benchmark_pipeline_efficiency.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_generate_and_validate(tmp_path):
    out = tmp_path / "pack"
    report = generate(out, seed=0, size=8, repetitions=1)
    assert report["all_equivalent"] is True
    for rel in REQUIRED_OUTPUT_FILES:
        assert (out / rel).exists(), rel
    assert (out / "validation.json").exists()
    assert (out / "obsidian" / "Pipeline_Efficiency_Index.md").exists()
    notes = list((out / "obsidian").glob("*.md"))
    assert len(notes) >= 5
    payloads = list((out / "command_center").glob("*.json"))
    assert len(payloads) >= 3
    result = validate_root(out)
    assert result["ok"] is True, result["violations"]
    packed = json.loads((out / "pipeline_efficiency_report.json").read_text(encoding="utf-8"))
    assert packed["evidence_class"] == "performance_only"
    assert packed["optimization_candidates"] == report["optimization_candidates"]


def test_validate_report_rejects_wrong_evidence_class():
    report = run_all(seed=0, size=8, repetitions=1)
    report["evidence_class"] = "scientific"
    result = validate_report(report)
    assert result["ok"] is False
    assert "evidence_class_mismatch" in result["violations"]


def test_cli_in_process_json(capsys):
    rc = cli.main(["--size", "8", "--repetitions", "1", "--json"])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["schema"] == "pipeline_efficiency/v1"
    assert report["num_targets"] == 8
    assert rc in (0, 1)


def test_cli_generate_validate(tmp_path):
    out = tmp_path / "cli-pack"
    rc = cli.main(["generate", "--out", str(out), "--size", "8", "--repetitions", "1"])
    assert rc == 0
    rc2 = cli.main(["validate", "--root", str(out)])
    assert rc2 == 0
