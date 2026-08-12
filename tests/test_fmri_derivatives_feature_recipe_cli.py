"""Subprocess CLI tests for
`python -m adapters.fmri_derivatives_feature_recipe_cli`. Synthetic
fixtures only -- no network access, no raw dataset download.
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
        [sys.executable, "-m", "adapters.fmri_derivatives_feature_recipe_cli", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _write_spec(tmp_path: Path, name: str, **overrides) -> Path:
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    kwargs = dict(
        dataset_id=f"cli_test_{name}", feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo", target_state="drug", atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.mean_connectivity", "qc.valid_timepoints"],
        max_subjects=5, max_runs=5, max_timepoints_per_state=100, max_total_timepoints=10000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={
            "connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation.",
            "qc.valid_timepoints": "Number of valid timepoints used per state.",
        },
        confound_policy={"description": "No confounds regression applied."},
        input_kind="timeseries_table",
        limitations=["cli test"], provenance="cli test fixture",
    )
    kwargs.update(overrides)
    spec = FmriFeatureRecipeSpecV1.make(**kwargs)
    path = tmp_path / f"{name}_spec.json"
    spec.write_json(path)
    return path


def _write_timeseries_table(tmp_path: Path, name: str) -> Path:
    rng = np.random.RandomState(0)

    def ts(coupling):
        base = rng.randn(6, 50)
        if coupling:
            shared = rng.randn(1, 50)
            base = base * (1 - coupling) + shared * coupling
        return base.tolist()

    data = {
        "dataset_id": f"cli_test_{name}", "atlas_or_parcellation": "Schaefer100",
        "subjects": {"sub-01": {"session": None, "timeseries": {"placebo_label": ts(0.0), "drug_label": ts(0.85)}}},
    }
    path = tmp_path / f"{name}_timeseries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_cli_happy_path_works(tmp_path):
    spec_path = _write_spec(tmp_path, "happy")
    table_path = _write_timeseries_table(tmp_path, "happy")
    out = _REPO_ROOT / "outputs" / "feature_recipes" / "cli-test-fmri-happy"
    try:
        result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-happy")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["features_written"] == 2
        assert payload["transitions_exportable"] == 1
        assert (out / "derived_features.csv").exists()
        assert (out / "mapping.json").exists()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_cli_dry_run_writes_no_features(tmp_path):
    spec_path = _write_spec(tmp_path, "dryrun")
    table_path = _write_timeseries_table(tmp_path, "dryrun")
    out = _REPO_ROOT / "outputs" / "feature_recipes" / "cli-test-fmri-dryrun"
    try:
        result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-dryrun", "--dry-run")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert not out.exists()
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_cli_invalid_output_root_fails(tmp_path):
    spec_path = _write_spec(tmp_path, "badroot")
    table_path = _write_timeseries_table(tmp_path, "badroot")
    result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "/etc/evil")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_invalid_feature_fails(tmp_path):
    spec_path = _write_spec(
        tmp_path, "badfeature",
        requested_features=["clinical.diagnostic_score"],
        feature_definitions={"clinical.diagnostic_score": "not supported"},
    )
    table_path = _write_timeseries_table(tmp_path, "badfeature")
    result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-badfeature")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_state_mapping_fails(tmp_path):
    spec_path = _write_spec(tmp_path, "nomapping", state_mapping={})
    table_path = _write_timeseries_table(tmp_path, "nomapping")
    result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-nomapping")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_atlas_fails(tmp_path):
    spec_path = _write_spec(tmp_path, "noatlas", atlas_or_parcellation="")
    table_path = _write_timeseries_table(tmp_path, "noatlas")
    result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-noatlas")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_confound_policy_fails(tmp_path):
    spec_path = _write_spec(tmp_path, "noconfound", confound_policy={})
    table_path = _write_timeseries_table(tmp_path, "noconfound")
    result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-noconfound")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_graph_policy_threshold_fails(tmp_path):
    spec_path = _write_spec(
        tmp_path, "nographpolicy",
        requested_features=["connectivity.global_efficiency"],
        feature_definitions={"connectivity.global_efficiency": "Global efficiency."},
        graph_policy={},
    )
    table_path = _write_timeseries_table(tmp_path, "nographpolicy")
    result = _run_cli("--spec", str(spec_path), "--timeseries-table", str(table_path), "--out", "outputs/feature_recipes/cli-test-fmri-nographpolicy")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_run_fmri_derivatives_adapter_end_to_end(tmp_path):
    spec_path = _write_spec(tmp_path, "adapter")
    table_path = _write_timeseries_table(tmp_path, "adapter")
    out = _REPO_ROOT / "outputs" / "feature_recipes" / "cli-test-fmri-adapter"
    try:
        result = _run_cli(
            "--spec", str(spec_path), "--timeseries-table", str(table_path),
            "--out", "outputs/feature_recipes/cli-test-fmri-adapter",
            "--run-fmri-derivatives-adapter", "--registry", "benchmarks/registry_seed.json",
            "--updated-registry-out", "outputs/feature_recipes/cli-test-fmri-adapter/adapter_export/reg.json",
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
    source = (_REPO_ROOT / "adapters" / "fmri_derivatives_feature_recipe_cli.py").read_text(encoding="utf-8")
    source += (_REPO_ROOT / "adapters" / "fmri_derivatives_feature_recipe.py").read_text(encoding="utf-8")
    for banned in ("requests.get(", "urllib.request", "boto3", "s3.download", "nilearn.datasets.fetch"):
        assert banned not in source
