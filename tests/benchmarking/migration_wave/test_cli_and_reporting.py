"""CLI generate/validate and finite JSON reports."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarking.migration_wave.schema import EVIDENCE_CLASS, REQUIRED_OUTPUT_FILES
from tools.benchmarking.migration_wave.validator import validate_report, validate_root
from tools.benchmarking.migration_wave.harness import run_all

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_migration_wave_cli",
    REPO_ROOT / "scripts" / "benchmark_migration_wave.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_generate_and_validate(tmp_path):
    out = tmp_path / "pack"
    rc = cli.main(
        [
            "generate",
            "--out",
            str(out),
            "--size",
            "32",
            "--repetitions",
            "1",
            "--variants",
            "current_main",
        ]
    )
    assert rc == 0
    for rel in REQUIRED_OUTPUT_FILES:
        assert (out / rel).exists(), rel
    packed = json.loads((out / "migration_wave_report.json").read_text(encoding="utf-8"))
    assert packed["evidence_class"] == EVIDENCE_CLASS
    assert packed["synthetic"] is True
    result = validate_root(out)
    assert result["ok"] is True, result["violations"]
    notes = list((out / "obsidian").glob("*.md"))
    assert len(notes) >= 8
    payloads = list((out / "command_center").glob("*.json"))
    assert len(payloads) >= 6


def test_validate_report_rejects_wrong_evidence_class():
    report = run_all(seed=0, size=32, repetitions=1, variants=["current_main"])
    report["evidence_class"] = "scientific"
    result = validate_report(report)
    assert result["ok"] is False
    assert "evidence_class_mismatch" in result["violations"]


def test_cli_json_with_output_skips_stdout_dump(tmp_path, capsys):
    dest = tmp_path / "report.json"
    rc = cli.main(
        ["--size", "32", "--repetitions", "1", "--json", "--output", str(dest), "--variants", "current_main"]
    )
    out = capsys.readouterr().out
    packed = json.loads(dest.read_text(encoding="utf-8"))
    assert packed["schema"] == "migration_wave/v1"
    assert "schema=migration_wave/v1" in out
    assert rc == 0
