from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_cli(tmp_path: Path, *extra: str):
    cmd = [sys.executable, "tools/validate_ontology_claim_language.py", "--root", str(tmp_path), "--json-out", "outputs/btc_icft/ontology_claim_language_validation.json", "--markdown-out", "outputs/btc_icft/ontology_claim_language_validation.md", *extra]
    return subprocess.run(cmd, cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)


def _write_baseline(tmp_path: Path, entries: list[dict]):
    p = tmp_path / "contracts/btc_icft/ontology_claims"
    p.mkdir(parents=True)
    (p / "claim_language_baseline.json").write_text(json.dumps({"baseline_version": "0.1", "purpose": "Known legacy ontology-language findings allowed only until cleaned up.", "entries": entries}), encoding="utf-8")


def test_baseline_file_suppresses_matching_violation(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("proves consciousness\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "docs/a.md", "line": None, "phrase": "proves consciousness", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    assert run_cli(tmp_path).returncode == 0


def test_baseline_match_ignores_line_number(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("\n\nproves consciousness\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "docs/a.md", "line": 1, "phrase": "proves consciousness", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    assert run_cli(tmp_path).returncode == 0


def test_unbaselined_violation_exits_1(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    assert run_cli(tmp_path, "--no-baseline").returncode == 1


def test_baselined_violation_appears_in_baselined_violations(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "docs/a.md", "line": None, "phrase": "ontology solved", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    run_cli(tmp_path)
    data = json.loads((tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").read_text())
    assert len(data["baselined_violations"]) == 1


def test_fail_on_baseline_exits_1(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "docs/a.md", "line": None, "phrase": "ontology solved", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    assert run_cli(tmp_path, "--fail-on-baseline").returncode == 1


def test_no_baseline_ignores_baseline_and_exits_1(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "docs/a.md", "line": None, "phrase": "ontology solved", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    assert run_cli(tmp_path, "--no-baseline").returncode == 1


def test_write_baseline_writes_candidate(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    run_cli(tmp_path, "--no-baseline", "--write-baseline", "outputs/candidate.json")
    candidate = json.loads((tmp_path / "outputs/candidate.json").read_text())
    assert candidate["entries"][0]["reason"] == "pending_review"


def test_strict_outputs_scans_outputs_only(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    (tmp_path / "outputs/btc_icft").mkdir(parents=True); (tmp_path / "outputs/btc_icft/o.md").write_text("clean\n", encoding="utf-8")
    assert run_cli(tmp_path, "--strict-outputs", "--no-baseline", "--scan-mode", "outputs").returncode == 0


def test_strict_outputs_fails_on_generated_unsafe_output(tmp_path: Path):
    (tmp_path / "outputs/btc_icft").mkdir(parents=True); (tmp_path / "outputs/btc_icft/o.md").write_text("eeg proves consciousness\n", encoding="utf-8")
    assert run_cli(tmp_path, "--strict-outputs", "--no-baseline", "--scan-mode", "outputs").returncode == 1


def test_scan_mode_docs_only(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("clean\n", encoding="utf-8")
    (tmp_path / "outputs/btc_icft").mkdir(parents=True); (tmp_path / "outputs/btc_icft/o.md").write_text("ontology solved\n", encoding="utf-8")
    assert run_cli(tmp_path, "--scan-mode", "docs", "--no-baseline").returncode == 0


def test_scan_mode_outputs_skips_docs(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    (tmp_path / "outputs/btc_icft").mkdir(parents=True); (tmp_path / "outputs/btc_icft/o.md").write_text("clean\n", encoding="utf-8")
    assert run_cli(tmp_path, "--scan-mode", "outputs", "--no-baseline").returncode == 0


def test_markdown_skip_what_cannot_be_claimed(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("## What cannot be claimed\nproves consciousness\n", encoding="utf-8")
    assert run_cli(tmp_path, "--no-baseline").returncode == 0


def test_markdown_skip_unsafe_examples(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("## Unsafe examples\nproves consciousness\n", encoding="utf-8")
    assert run_cli(tmp_path, "--no-baseline").returncode == 0


def test_report_separates_unbaselined_and_baselined(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("proves consciousness\nontology solved\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "docs/a.md", "line": None, "phrase": "proves consciousness", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    run_cli(tmp_path)
    data = json.loads((tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").read_text())
    assert data["baselined_violation_count"] == 1 and data["unbaselined_violation_count"] == 1


def test_makefile_and_workflow_and_baseline_contract_present():
    repo = Path(__file__).resolve().parents[2]
    mk = (repo / "Makefile").read_text(encoding="utf-8")
    wf = (repo / ".github/workflows/ontology-claim-language.yml").read_text(encoding="utf-8")
    baseline = json.loads((repo / "contracts/btc_icft/ontology_claims/claim_language_baseline.json").read_text())
    assert "ontology-language-check-strict-outputs:" in mk
    assert "--baseline contracts/btc_icft/ontology_claims/claim_language_baseline.json" in wf
    assert "--no-baseline" not in wf
    assert baseline["baseline_version"] == "0.1" and isinstance(baseline["entries"], list)


def test_generated_ds005620_profile_scans_only_ds005620_output_roots(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    out = tmp_path / "outputs/btc_icft/ds005620_real_benchmark_execution_mock"
    out.mkdir(parents=True)
    (out / "safe.md").write_text("clean\n", encoding="utf-8")
    assert run_cli(tmp_path, "--scan-mode", "generated", "--generated-output-profile", "ds005620", "--strict-outputs", "--no-baseline").returncode == 0


def test_generated_ds005620_profile_missing_roots_listed_without_failure(tmp_path: Path):
    result = run_cli(tmp_path, "--scan-mode", "generated", "--generated-output-profile", "ds005620", "--strict-outputs", "--no-baseline")
    assert result.returncode == 0
    data = json.loads((tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").read_text())
    assert len(data["missing_generated_roots"]) > 0


def test_generated_ds005620_profile_does_not_scan_docs_contracts_or_configs(tmp_path: Path):
    (tmp_path / "docs").mkdir(); (tmp_path / "docs/a.md").write_text("ontology solved\n", encoding="utf-8")
    (tmp_path / "contracts").mkdir(); (tmp_path / "contracts/a.md").write_text("ontology solved\n", encoding="utf-8")
    (tmp_path / "configs").mkdir(); (tmp_path / "configs/a.md").write_text("ontology solved\n", encoding="utf-8")
    (tmp_path / "sciencer_d").mkdir(); (tmp_path / "sciencer_d/a.md").write_text("ontology solved\n", encoding="utf-8")
    assert run_cli(tmp_path, "--scan-mode", "generated", "--generated-output-profile", "ds005620", "--strict-outputs", "--no-baseline").returncode == 0


def test_generated_report_includes_scanned_generated_roots(tmp_path: Path):
    out = tmp_path / "outputs/btc_icft/ds005620_ontology_evaluation_mock"
    out.mkdir(parents=True)
    (out / "safe.md").write_text("clean\n", encoding="utf-8")
    run_cli(tmp_path, "--scan-mode", "generated", "--generated-output-profile", "ds005620", "--strict-outputs", "--no-baseline")
    data = json.loads((tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").read_text())
    assert "outputs/btc_icft/ds005620_ontology_evaluation_mock" in data["scanned_generated_roots"]


def test_generated_report_includes_missing_generated_roots(tmp_path: Path):
    run_cli(tmp_path, "--scan-mode", "generated", "--generated-output-profile", "ds005620", "--strict-outputs", "--no-baseline")
    data = json.loads((tmp_path / "outputs/btc_icft/ontology_claim_language_validation.json").read_text())
    assert "outputs/btc_icft/ds005620_real_execution_gate" in data["missing_generated_roots"]


def test_strict_outputs_generated_no_baseline_does_not_allow_baselined_generated_violations(tmp_path: Path):
    out = tmp_path / "outputs/btc_icft/ds005620_real_benchmark_execution_mock"
    out.mkdir(parents=True)
    (out / "unsafe.md").write_text("ontology solved\n", encoding="utf-8")
    _write_baseline(tmp_path, [{"path": "outputs/btc_icft/ds005620_real_benchmark_execution_mock/unsafe.md", "line": None, "phrase": "ontology solved", "category": "forbidden_phrase", "reason": "pending_cleanup", "expires": None, "owner": "repo"}])
    assert run_cli(tmp_path, "--scan-mode", "generated", "--generated-output-profile", "ds005620", "--strict-outputs", "--no-baseline").returncode == 1
