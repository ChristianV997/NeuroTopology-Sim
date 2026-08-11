"""Subprocess CLI tests for `python -m evidence.export_bundle`.

Exercises the actual CLI against the real committed ds005620/ds000245
contract artifacts and the real committed benchmarks/registry_seed.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = "contracts/btc_icft/ds005620/pitnn_cohort"
_DS000245_SOURCE = "contracts/fmri_tda/ds000245"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "evidence.export_bundle", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def test_cli_builds_ds005620_cohort_summary_bundle(tmp_path):
    out = tmp_path / "out"
    result = _run_cli(
        "--dataset", "ds005620", "--feature-set", "cohort_summary",
        "--registry", str(_SEED_REGISTRY), "--source", _DS005620_SOURCE, "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dataset_id"] == "ds005620"
    assert payload["n_transition_records"] == 21
    assert (out / "EvidenceBundle.json").exists()


def test_cli_builds_ds000245_bundle_with_phase_space(tmp_path):
    out = tmp_path / "out"
    result = _run_cli(
        "--dataset", "ds000245", "--feature-set", "schaefer100_motcorr",
        "--registry", str(_SEED_REGISTRY), "--source", _DS000245_SOURCE, "--out", str(out),
        "--include-phase-space",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_transition_records"] == 3
    assert payload["n_phase_space_coordinates"] > 0
    assert (out / "phase_space").is_dir()


def test_cli_forbidden_use_fails_closed(tmp_path):
    out = tmp_path / "out"
    result = _run_cli(
        "--dataset", "ds005620", "--feature-set", "cohort_summary",
        "--registry", str(_SEED_REGISTRY), "--source", _DS005620_SOURCE, "--out", str(out),
        "--requested-use", "clinical_claim",
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert not out.exists()


def test_cli_mark_seen_writes_updated_registry(tmp_path):
    out = tmp_path / "out"
    updated_out = tmp_path / "updated.json"
    result = _run_cli(
        "--dataset", "ds005620", "--feature-set", "cohort_summary",
        "--registry", str(_SEED_REGISTRY), "--source", _DS005620_SOURCE, "--out", str(out),
        "--mark-seen", "--updated-registry-out", str(updated_out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["contamination_updates"]
    assert updated_out.exists()


def test_cli_seed_registry_never_mutated_by_cli_run(tmp_path):
    before = _SEED_REGISTRY.read_bytes()
    _run_cli(
        "--dataset", "ds005620", "--feature-set", "cohort_summary",
        "--registry", str(_SEED_REGISTRY), "--source", _DS005620_SOURCE, "--out", str(tmp_path / "out"),
        "--mark-seen", "--updated-registry-out", str(tmp_path / "updated.json"),
    )
    after = _SEED_REGISTRY.read_bytes()
    assert before == after


def test_cli_no_registry_and_no_flag_fails_closed(tmp_path):
    result = _run_cli(
        "--dataset", "ds005620", "--feature-set", "cohort_summary",
        "--source", _DS005620_SOURCE, "--out", str(tmp_path / "out"),
    )
    assert result.returncode == 1
    assert "registry_path is required" in result.stdout


def test_cli_no_registry_legacy_mode_succeeds(tmp_path):
    out = tmp_path / "out"
    result = _run_cli(
        "--dataset", "ds005620", "--feature-set", "cohort_summary",
        "--no-registry", "--source", _DS005620_SOURCE, "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    assert (out / "EvidenceBundle.json").exists()


def test_cli_unsupported_dataset_argument_rejected():
    result = _run_cli(
        "--dataset", "ds005917", "--feature-set", "anything",
        "--registry", str(_SEED_REGISTRY), "--source", ".", "--out", "/tmp/never",
    )
    assert result.returncode != 0
    assert "ds005917" in result.stderr or "invalid choice" in result.stderr
