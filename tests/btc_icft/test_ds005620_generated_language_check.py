from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _run_wrapper(tmp_path: Path):
    cmd = [
        sys.executable,
        "tools/validate_ds005620_generated_language.py",
        "--root", str(tmp_path),
        "--json-out", "outputs/btc_icft/ds005620_generated_language_validation.json",
        "--markdown-out", "outputs/btc_icft/ds005620_generated_language_validation.md",
    ]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)


def test_wrapper_exists():
    assert (REPO / "tools/validate_ds005620_generated_language.py").is_file()


def test_wrapper_writes_json_and_markdown_reports(tmp_path: Path):
    root = tmp_path / "outputs/btc_icft/ds005620_real_benchmark_execution_mock"
    root.mkdir(parents=True)
    (root / "safe.md").write_text("runtime association observed\n", encoding="utf-8")
    result = _run_wrapper(tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "outputs/btc_icft/ds005620_generated_language_validation.json").is_file()
    assert (tmp_path / "outputs/btc_icft/ds005620_generated_language_validation.md").is_file()


def test_wrapper_exits_0_on_safe_generated_fixture(tmp_path: Path):
    root = tmp_path / "outputs/btc_icft/ds005620_ontology_evaluation_mock"
    root.mkdir(parents=True)
    (root / "safe.md").write_text("engineering evidence only\n", encoding="utf-8")
    assert _run_wrapper(tmp_path).returncode == 0


def test_wrapper_exits_1_on_unsafe_generated_fixture(tmp_path: Path):
    root = tmp_path / "outputs/btc_icft/ds005620_publication_package"
    root.mkdir(parents=True)
    (root / "unsafe.md").write_text("eeg proves consciousness\n", encoding="utf-8")
    assert _run_wrapper(tmp_path).returncode == 1


def test_makefile_contains_generated_language_targets():
    txt = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "ds005620-generated-language-check:" in txt
    assert "ds005620-generated-artifact-check:" in txt
    section = txt.split("ds005620-generated-artifact-check:", 1)[1]
    assert "ds005620-generated-language-check" in section


def test_workflow_includes_generated_language_check():
    txt = (REPO / ".github/workflows/ds005620-e2e.yml").read_text(encoding="utf-8")
    assert "make ds005620-generated-language-check" in txt
    assert "ds005620_generated_language_validation.json" in txt
    assert "ds005620_generated_language_validation.md" in txt
