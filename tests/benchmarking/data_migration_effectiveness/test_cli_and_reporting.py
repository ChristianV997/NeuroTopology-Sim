"""CLI generate/validate, reporting artifacts, and validator gates."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarking.data_migration_effectiveness.harness import run_all
from tools.benchmarking.data_migration_effectiveness.report import generate
from tools.benchmarking.data_migration_effectiveness.schema import REQUIRED_OUTPUT_FILES
from tools.benchmarking.data_migration_effectiveness.validator import validate_report, validate_root

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_data_migration_effectiveness_cli2",
    REPO_ROOT / "scripts" / "benchmark_data_migration_effectiveness.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_generate_and_validate(tmp_path):
    out = tmp_path / "pack"
    report = generate(out, seed=0, size=32, repetitions=1)
    assert report["all_checksums_match"] is True
    for rel in REQUIRED_OUTPUT_FILES:
        assert (out / rel).exists(), rel
    notes = list((out / "obsidian").glob("*.md"))
    assert len(notes) >= 5
    payloads = list((out / "command_center").glob("*.json"))
    assert len(payloads) >= 3
    result = validate_root(out)
    assert result["ok"] is True, result["violations"]
    packed = json.loads((out / "data_migration_effectiveness.json").read_text(encoding="utf-8"))
    assert packed["evidence_class"] == "performance_only"
    assert packed["scientific_improvement_claimed"] is False


def test_validate_report_rejects_wrong_evidence_class():
    report = run_all(seed=0, size=32, repetitions=1)
    report["evidence_class"] = "scientific"
    result = validate_report(report)
    assert result["ok"] is False
    assert "evidence_class_mismatch" in result["violations"]


def test_validate_report_rejects_scientific_claim():
    report = run_all(seed=0, size=32, repetitions=1)
    report["scientific_improvement_claimed"] = True
    result = validate_report(report)
    assert result["ok"] is False
    assert "scientific_improvement_claimed" in result["violations"]


def test_cli_in_process_json(tmp_path, capsys):
    rc = cli.main(
        [
            "--size",
            "32",
            "--repetitions",
            "1",
            "--json-stdout",
            "--output",
            str(tmp_path / "cli"),
        ]
    )
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["schema"] == "data_migration_effectiveness/v1"
    assert len(report["results"]) == 10
    assert rc in (0, 1)


def test_cli_generate_validate(tmp_path):
    out = tmp_path / "cli-pack"
    rc = cli.main(["generate", "--output", str(out), "--size", "32", "--repetitions", "1"])
    assert rc == 0
    rc2 = cli.main(["validate", "--output", str(out)])
    assert rc2 == 0
