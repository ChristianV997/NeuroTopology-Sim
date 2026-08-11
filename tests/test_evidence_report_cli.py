"""Subprocess CLI tests for `python -m reports.export_report`.

Builds a real EvidenceBundle first (via evidence.builder, against the real
committed contracts/btc_icft/ds005620/pitnn_cohort/ artifact and the real
committed benchmarks/registry_seed.json), then exercises the report CLI
against it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evidence.builder import build_evidence_bundle

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "reports.export_report", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _build_real_bundle(tmp_path) -> Path:
    out = tmp_path / "bundle_out"
    build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_phase_space=True,
    )
    return out / "EvidenceBundle.json"


def test_cli_generates_report_json_and_markdown(tmp_path):
    bundle_path = _build_real_bundle(tmp_path)
    out = tmp_path / "report_out"
    result = _run_cli("--bundle", str(bundle_path), "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["dataset_id"] == "ds005620"
    assert payload["validation_status"] == "valid"
    assert (out / "EvidenceReport.md").exists()
    assert (out / "EvidenceReport.json").exists()


def test_cli_prints_concise_summary(tmp_path):
    bundle_path = _build_real_bundle(tmp_path)
    out = tmp_path / "report_out"
    result = _run_cli("--bundle", str(bundle_path), "--out", str(out))
    payload = json.loads(result.stdout)
    for key in (
        "report_id", "bundle_id", "dataset_id", "output_paths",
        "validation_status", "limitation_count", "coordinate_status_counts",
    ):
        assert key in payload, key


def test_cli_markdown_only_format(tmp_path):
    bundle_path = _build_real_bundle(tmp_path)
    out = tmp_path / "report_out"
    result = _run_cli("--bundle", str(bundle_path), "--out", str(out), "--format", "markdown")
    assert result.returncode == 0, result.stderr
    assert (out / "EvidenceReport.md").exists()
    assert not (out / "EvidenceReport.json").exists()


def test_cli_json_only_format(tmp_path):
    bundle_path = _build_real_bundle(tmp_path)
    out = tmp_path / "report_out"
    result = _run_cli("--bundle", str(bundle_path), "--out", str(out), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert not (out / "EvidenceReport.md").exists()
    assert (out / "EvidenceReport.json").exists()


def test_cli_fails_clearly_on_missing_bundle(tmp_path):
    result = _run_cli("--bundle", str(tmp_path / "does_not_exist.json"), "--out", str(tmp_path / "out"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert "does not exist" in result.stdout


def test_cli_fails_clearly_on_invalid_bundle(tmp_path):
    bad_bundle = tmp_path / "bad_bundle.json"
    bad_bundle.write_text("{}", encoding="utf-8")
    result = _run_cli("--bundle", str(bad_bundle), "--out", str(tmp_path / "out"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_fails_clearly_on_malformed_json_bundle(tmp_path):
    bad_bundle = tmp_path / "bad_bundle.json"
    bad_bundle.write_text("{not valid json", encoding="utf-8")
    result = _run_cli("--bundle", str(bad_bundle), "--out", str(tmp_path / "out"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_unknown_format_rejected(tmp_path):
    bundle_path = _build_real_bundle(tmp_path)
    result = _run_cli("--bundle", str(bundle_path), "--out", str(tmp_path / "out"), "--format", "pdf")
    assert result.returncode == 1
    assert "unknown format" in result.stdout


def test_cli_report_is_valid_when_read_back(tmp_path):
    bundle_path = _build_real_bundle(tmp_path)
    out = tmp_path / "report_out"
    _run_cli("--bundle", str(bundle_path), "--out", str(out))
    from reports.evidence_report import EvidenceReportV1

    report = EvidenceReportV1.from_json((out / "EvidenceReport.json").read_text(encoding="utf-8"))
    assert report.validate() == []
