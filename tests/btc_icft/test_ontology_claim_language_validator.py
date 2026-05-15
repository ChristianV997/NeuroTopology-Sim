from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(tmp_path: Path, *extra: str):
    cmd = [sys.executable, "tools/validate_ontology_claim_language.py", "--root", str(tmp_path), "--json-out", "outputs/btc_icft/ontology_claim_language_validation.json", "--markdown-out", "outputs/btc_icft/ontology_claim_language_validation.md", *extra]
    return subprocess.run(cmd, cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)


def test_forbidden_phrase_markdown(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("this proves consciousness\n", encoding="utf-8")
    result = run_cli(tmp_path)
    assert result.returncode == 1


def test_case_insensitive(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("EEG PROVES CONSCIOUSNESS\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 1


def test_unsafe_categories(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("q_abs proves x\nsedated means no_experience\nq = soul\n", encoding="utf-8")
    data = json.loads((run_cli(tmp_path), (tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").read_text())[1])
    cats = {v["category"] for v in data["violations"]}
    assert "metric_to_ontology_shortcut" in cats
    assert "state_label_shortcut" in cats
    assert "forbidden_equivalence" in cats


def test_safe_phrases_not_flagged(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("bridge hypothesis and theory consistency\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 0


def test_missing_output_root_ok(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("clean\n", encoding="utf-8")
    assert run_cli(tmp_path, "--output-roots", "outputs/missing").returncode == 0


def test_reports_written_and_quiet(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("clean\n", encoding="utf-8")
    res = run_cli(tmp_path, "--quiet")
    assert "PASS" not in res.stdout
    assert (tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").exists()
    assert (tmp_path / "outputs/btc_icft/ontology_claim_language_validation.md").exists()


def test_skip_tests_default_and_include_tests(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "x.md").write_text("soul proven\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 0
    assert run_cli(tmp_path, "--include-tests").returncode == 1


def test_json_forbidden_key_skipped(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.json").write_text('{"forbidden_claims": "soul proven"}\n', encoding="utf-8")
    assert run_cli(tmp_path).returncode == 0


def test_guardrail_heading_skipped(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("## Forbidden phrases\nproves consciousness\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 0


def test_generated_report_not_flagged(tmp_path: Path):
    (tmp_path / "outputs/btc_icft").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("clean\n", encoding="utf-8")
    (tmp_path / "outputs/btc_icft/ontology_claim_language_validation.md").write_text("proves consciousness\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 0


def test_cli_exit_codes(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("clean\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 0
    (tmp_path / "docs" / "b.md").write_text("ontology solved\n", encoding="utf-8")
    assert run_cli(tmp_path).returncode == 1


def test_makefile_target_present():
    makefile = Path(__file__).resolve().parents[2] / "Makefile"
    assert "ontology-language-check:" in makefile.read_text(encoding="utf-8")
