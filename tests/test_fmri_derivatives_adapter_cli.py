"""Subprocess CLI tests for `python -m adapters.fmri_derivatives`. Synthetic
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
        [sys.executable, "-m", "adapters.fmri_derivatives", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _write_features(tmp_path: Path, dataset_id: str) -> tuple[Path, Path]:
    features = tmp_path / "features.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition", "atlas_or_parcellation"])
        w.writerow(["sub-01", "placebo", "drug", "connectivity.global_efficiency", "0.34", "0.29", "Graph global efficiency", "Schaefer100"])
        w.writerow(["sub-02", "placebo", "drug", "connectivity.global_efficiency", "0.30", "0.25", "Graph global efficiency", "Schaefer100"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": dataset_id, "modality": "fMRI",
        "preprocessing_provenance": {"pipeline": "fmriprep", "source_tool_version": "fmriprep==23.x"},
        "confound_policy": "24-param",
    }), encoding="utf-8")
    return features, mapping


def test_cli_happy_path_succeeds(tmp_path):
    features, mapping = _write_features(tmp_path, "cli_fmri_smoke_ds")
    out = tmp_path / "out"
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(out),
        "--registry", str(_SEED_REGISTRY), "--updated-registry-out", str(out / "reg.json"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_transitions_written"] == 2
    assert payload["n_errors"] == 0
    assert payload["atlas_or_parcellation"] == ["Schaefer100"]


def test_cli_prints_concise_summary(tmp_path):
    features, mapping = _write_features(tmp_path, "cli_fmri_smoke_ds2")
    out = tmp_path / "out"
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(out),
        "--registry", str(_SEED_REGISTRY), "--updated-registry-out", str(out / "reg.json"),
    )
    payload = json.loads(result.stdout)
    for key in (
        "dataset_id", "n_groups_parsed", "n_transitions_written", "n_cohort_records_written",
        "n_skipped_rows", "transitions_dir", "registry_decisions", "atlas_or_parcellation", "limitations_count",
    ):
        assert key in payload, key


def test_cli_missing_mapping_fails(tmp_path):
    features, _ = _write_features(tmp_path, "cli_fmri_smoke_ds3")
    result = _run_cli("--features", str(features), "--out", str(tmp_path / "out"), "--registry", str(_SEED_REGISTRY))
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_ambiguous_pairing_fails(tmp_path):
    features = tmp_path / "features_wide.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "placebo_ge", "drug_ge"])
        w.writerow(["sub-01", "0.34", "0.29"])
    mapping = tmp_path / "mapping_wide.json"
    mapping.write_text(json.dumps({
        "format": "wide", "dataset_id": "cli_wide_fmri_ds", "modality": "fMRI", "atlas_or_parcellation": "Schaefer100",
        "feature_definitions": {"connectivity.global_efficiency": "graph global efficiency"},
        "features": [{"canonical_name": "connectivity.global_efficiency", "source_column": "placebo_ge", "target_column": "drug_ge"}],
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
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
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition", "atlas_or_parcellation"])
        w.writerow(["sub-01", "placebo", "drug", "consciousness.detected", "1.0", "0.0", "bad namespace", "Schaefer100"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": "cli_bad_ns_fmri_ds", "modality": "fMRI",
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
    }), encoding="utf-8")
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(tmp_path / "out"),
        "--registry", str(_SEED_REGISTRY),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_atlas_for_connectivity_feature_fails(tmp_path):
    features = tmp_path / "features_no_atlas.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition"])
        w.writerow(["sub-01", "placebo", "drug", "connectivity.global_efficiency", "0.34", "0.29", "graph global efficiency"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": "cli_no_atlas_fmri_ds", "modality": "fMRI",
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
    }), encoding="utf-8")
    result = _run_cli(
        "--features", str(features), "--mapping", str(mapping), "--out", str(tmp_path / "out"),
        "--registry", str(_SEED_REGISTRY),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_denied_registry_use_fails(tmp_path):
    features, mapping = _write_features(tmp_path, "cli_fmri_smoke_ds4")
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


def test_cli_graph_summary_without_mapping_succeeds(tmp_path):
    summary = tmp_path / "graph_summary.json"
    summary.write_text(json.dumps({
        "format": "graph_summary", "dataset_id": "cli_graph_summary_ds", "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100", "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"pipeline": "fmriprep"}, "confound_policy": "24-param",
        "feature_definitions": {"connectivity.global_efficiency": "graph global efficiency"},
        "subjects": [{"subject_id": "sub-01", "metrics": {"connectivity.global_efficiency": {"source_value": 0.34, "target_value": 0.29}}}],
    }), encoding="utf-8")
    out = tmp_path / "out"
    result = _run_cli(
        "--features", str(summary), "--out", str(out),
        "--registry", str(_SEED_REGISTRY), "--updated-registry-out", str(out / "reg.json"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_transitions_written"] == 1


def test_cli_scan_derivatives_writes_dataset_records(tmp_path):
    root = tmp_path / "derivatives_root"
    (root / "sub-01" / "func").mkdir(parents=True, exist_ok=True)
    root.joinpath("dataset_description.json").write_text(json.dumps({"Name": "CLI Scan Test fMRI"}), encoding="utf-8")
    root.joinpath("participants.tsv").write_text("participant_id\nsub-01\n", encoding="utf-8")
    out_json = tmp_path / "scan_result.json"
    result = _run_cli("--scan-derivatives", str(root), "--write-dataset-records", str(out_json))
    assert result.returncode == 0, result.stdout + result.stderr
    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["dataset_record"]["dataset_id"] == "cli-scan-test-fmri"
    assert "transition_export" not in payload["dataset_record"]["allowed_uses"]


def test_cli_scan_derivatives_prints_summary(tmp_path):
    root = tmp_path / "derivatives_root"
    (root / "sub-01" / "func").mkdir(parents=True, exist_ok=True)
    root.joinpath("dataset_description.json").write_text(json.dumps({"Name": "CLI Scan Summary Test fMRI"}), encoding="utf-8")
    result = _run_cli("--scan-derivatives", str(root))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["dataset_id"] == "cli-scan-summary-test-fmri"
    assert "dataset_record" in payload


def test_cli_scan_derivatives_fails_closed_on_missing_root(tmp_path):
    result = _run_cli("--scan-derivatives", str(tmp_path / "does_not_exist"))
    assert result.returncode == 1
    assert "FAILED" in result.stdout
