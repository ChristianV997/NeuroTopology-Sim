"""Subprocess CLI tests for `python -m adapters.mne_bids_feature_recipe_cli`.
Synthetic fixtures only -- no network access, no raw dataset download.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "adapters.mne_bids_feature_recipe_cli", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _write_spec(tmp_path: Path, name: str, **overrides) -> Path:
    from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1

    kwargs = dict(
        dataset_id=f"cli_test_{name}",
        feature_set_id="mne_bids_spectral_v1",
        source_state="rest",
        target_state="task",
        requested_features=["spectral.alpha_power", "qc.valid_epoch_count"],
        max_subjects=5,
        max_runs=5,
        max_epochs_per_state=10,
        max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={
            "spectral.alpha_power": "Mean relative alpha-band power over valid epochs.",
            "qc.valid_epoch_count": "Count of valid epochs used per state.",
        },
        input_kind="epoch_table",
        limitations=["cli test"],
        provenance="cli test fixture",
    )
    kwargs.update(overrides)
    spec = FeatureRecipeSpecV1.make(**kwargs)
    path = tmp_path / f"{name}_spec.json"
    spec.write_json(path)
    return path


def _write_epoch_table(tmp_path: Path, name: str) -> Path:
    rng = np.random.RandomState(0)
    sfreq = 100.0
    n_samples = 200

    def epoch(alpha_boost):
        t = np.arange(n_samples) / sfreq
        sig = rng.randn(n_samples) * 1e-5 + alpha_boost * np.sin(2 * np.pi * 10 * t) * 1e-5
        return [sig.tolist(), sig.tolist()]

    table = {
        "sfreq": sfreq, "channels": ["C3", "C4"],
        "subjects": {"sub-01": {"session": None, "epochs": {
            "rest_marker": [epoch(0.0) for _ in range(5)],
            "task_marker": [epoch(3.0) for _ in range(5)],
        }}},
    }
    path = tmp_path / f"{name}_epoch_table.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def test_cli_happy_path_works(tmp_path):
    spec_path = _write_spec(tmp_path, "happy")
    table_path = _write_epoch_table(tmp_path, "happy")
    out = _REPO_ROOT / "outputs" / "feature_recipes" / "cli-test-happy"
    try:
        result = _run_cli("--spec", str(spec_path), "--epoch-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-happy")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["features_written"] == 2
        assert payload["transitions_exportable"] == 1
        assert (out / "derived_features.csv").exists()
        assert (out / "mapping.json").exists()
        assert (out / "recipe_manifest.json").exists()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_cli_dry_run_writes_no_features(tmp_path):
    spec_path = _write_spec(tmp_path, "dryrun")
    table_path = _write_epoch_table(tmp_path, "dryrun")
    out = _REPO_ROOT / "outputs" / "feature_recipes" / "cli-test-dryrun"
    try:
        result = _run_cli(
            "--spec", str(spec_path), "--epoch-table", str(table_path),
            "--out", "outputs/feature_recipes/cli-test-dryrun", "--dry-run",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert not out.exists()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_cli_invalid_output_root_fails(tmp_path):
    spec_path = _write_spec(tmp_path, "badroot")
    table_path = _write_epoch_table(tmp_path, "badroot")
    result = _run_cli("--spec", str(spec_path), "--epoch-table", str(table_path), "--out", "/etc/evil")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_invalid_feature_fails(tmp_path):
    spec_path = _write_spec(
        tmp_path, "badfeature",
        requested_features=["connectivity.plv"],
        feature_definitions={"connectivity.plv": "not supported"},
    )
    table_path = _write_epoch_table(tmp_path, "badfeature")
    result = _run_cli("--spec", str(spec_path), "--epoch-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-badfeature")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_mapping_fails():
    """No --spec at all is a missing required arg -- argparse itself fails."""
    result = _run_cli("--out", "outputs/feature_recipes/cli-test-nospec")
    assert result.returncode != 0


def test_cli_missing_event_state_mapping_fails(tmp_path):
    spec_path = _write_spec(tmp_path, "nomapping", event_state_mapping={})
    table_path = _write_epoch_table(tmp_path, "nomapping")
    result = _run_cli("--spec", str(spec_path), "--epoch-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-nomapping")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_run_mne_bids_adapter_end_to_end(tmp_path):
    spec_path = _write_spec(tmp_path, "adapter")
    table_path = _write_epoch_table(tmp_path, "adapter")
    out = _REPO_ROOT / "outputs" / "feature_recipes" / "cli-test-adapter"
    try:
        result = _run_cli(
            "--spec", str(spec_path), "--epoch-table", str(table_path),
            "--out", "outputs/feature_recipes/cli-test-adapter",
            "--run-mne-bids-adapter", "--registry", "benchmarks/registry_seed.json",
            "--updated-registry-out", "outputs/feature_recipes/cli-test-adapter/adapter_export/reg.json",
            "--include-evidence-bundle", "--include-report",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["adapter_n_transitions_written"] == 1
        assert "adapter_evidence_bundle_id" in payload
        assert "adapter_report" in payload
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_cli_never_downloads_raw_data():
    source = (_REPO_ROOT / "adapters" / "mne_bids_feature_recipe_cli.py").read_text(encoding="utf-8")
    source += (_REPO_ROOT / "adapters" / "mne_bids_feature_recipe.py").read_text(encoding="utf-8")
    for banned in ("requests.get(", "urllib.request", "boto3", "s3.download"):
        assert banned not in source
