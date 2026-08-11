"""Subprocess CLI tests for `python -m adapters.mne_bids`. Synthetic
miniature fixtures only -- no network access.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "adapters.mne_bids", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _write_features(tmp_path: Path, dataset_id: str) -> tuple[Path, Path]:
    features = tmp_path / "features.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition"])
        w.writerow(["sub-01", "awake", "sedated", "spectral.alpha_power", "1.5", "0.8", "Welch PSD alpha power"])
        w.writerow(["sub-02", "awake", "sedated", "spectral.alpha_power", "1.2", "0.9", "Welch PSD alpha power"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": dataset_id, "modality": "EEG",
        "preprocessing_provenance": {"pipeline": "mne", "source_tool_version": "mne==1.x"},
    }), encoding="utf-8")
    return features, mapping


def test_cli_happy_path_succeeds(tmp_path):
    features, mapping = _write_features(tmp_path, "cli_smoke_test_ds")
    out = tmp_path / "out"
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(out),
        "--registry", str(_SEED_REGISTRY), "--updated-registry-out", str(out / "reg.json"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_transitions_written"] == 2
    assert payload["n_errors"] == 0


def test_cli_prints_concise_summary(tmp_path):
    features, mapping = _write_features(tmp_path, "cli_smoke_test_ds2")
    out = tmp_path / "out"
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(out),
        "--registry", str(_SEED_REGISTRY), "--updated-registry-out", str(out / "reg.json"),
    )
    payload = json.loads(result.stdout)
    for key in ("dataset_id", "n_groups_parsed", "n_transitions_written", "n_skipped_rows", "transitions_dir", "registry_decisions"):
        assert key in payload, key


def test_cli_missing_mapping_fails(tmp_path):
    features, _ = _write_features(tmp_path, "cli_smoke_test_ds3")
    result = _run_cli("--features", str(features), "--out", str(tmp_path / "out"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert "mapping" in result.stdout


def test_cli_ambiguous_pairing_fails(tmp_path):
    features = tmp_path / "features_wide.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "awake_alpha", "sedated_alpha"])
        w.writerow(["sub-01", "1.5", "0.8"])
    mapping = tmp_path / "mapping_wide.json"
    mapping.write_text(json.dumps({
        "format": "wide", "dataset_id": "cli_wide_ds", "modality": "EEG",
        "feature_definitions": {"spectral.alpha_power": "alpha power"},
        "features": [{"canonical_name": "spectral.alpha_power", "source_column": "awake_alpha", "target_column": "sedated_alpha"}],
        "preprocessing_provenance": {"pipeline": "mne"},
    }), encoding="utf-8")  # source_state/target_state deliberately omitted
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(tmp_path / "out"),
        "--registry", str(_SEED_REGISTRY),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_invalid_feature_namespace_fails(tmp_path):
    features = tmp_path / "features_bad_ns.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition"])
        w.writerow(["sub-01", "awake", "sedated", "consciousness.detected", "1.0", "0.0", "bad namespace"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": "cli_bad_ns_ds", "modality": "EEG",
        "preprocessing_provenance": {"pipeline": "mne"},
    }), encoding="utf-8")
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(tmp_path / "out"),
        "--registry", str(_SEED_REGISTRY),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_denied_registry_use_fails(tmp_path):
    features, mapping = _write_features(tmp_path, "cli_smoke_test_ds4")
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(tmp_path / "out"),
        "--registry", str(_SEED_REGISTRY), "--requested-use", "final_claim_confirmation",
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_no_scan_no_features_fails(tmp_path):
    result = _run_cli("--out", str(tmp_path / "out"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_scan_bids_writes_dataset_records(tmp_path):
    root = tmp_path / "bids_root"
    (root / "sub-01" / "eeg").mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text(json.dumps({"Name": "CLI Scan Test"}), encoding="utf-8")
    (root / "participants.tsv").write_text("participant_id\nsub-01\n", encoding="utf-8")
    out_json = tmp_path / "scan_result.json"
    result = _run_cli("--scan-bids", str(root), "--write-dataset-records", str(out_json))
    assert result.returncode == 0, result.stdout + result.stderr
    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["dataset_record"]["dataset_id"] == "cli-scan-test"
    assert "transition_export" not in payload["dataset_record"]["allowed_uses"]


def test_cli_scan_bids_prints_summary(tmp_path):
    root = tmp_path / "bids_root"
    (root / "sub-01" / "eeg").mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text(json.dumps({"Name": "CLI Scan Summary Test"}), encoding="utf-8")
    result = _run_cli("--scan-bids", str(root))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["dataset_id"] == "cli-scan-summary-test"
    assert "dataset_record" in payload


def test_cli_scan_bids_fails_closed_on_missing_root(tmp_path):
    result = _run_cli("--scan-bids", str(tmp_path / "does_not_exist"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout
