"""Feature extraction: epoch_table (always run) and bids_raw (real,
synthetic MNE-generated fixture -- no external dataset download). Synthetic
fixtures only.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from adapters.mne_bids_feature_recipe import (
    FeatureRecipeError,
    compute_features_for_epochs,
    run_feature_recipe,
    write_recipe_outputs,
)
from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1

_SFREQ = 100.0
_N_SAMPLES = 200  # 2s epochs at 100Hz


def _make_epoch(rng: np.random.RandomState, alpha_boost: float = 0.0) -> list[list[float]]:
    t = np.arange(_N_SAMPLES) / _SFREQ
    sig = rng.randn(_N_SAMPLES) * 1e-5
    if alpha_boost:
        sig = sig + alpha_boost * np.sin(2 * np.pi * 10 * t) * 1e-5
    return [sig.tolist(), sig.tolist()]  # 2 channels, identical for determinism


def _write_epoch_table(tmp_path, *, n_subjects=2, n_epochs=5, alpha_boost=3.0, seed=0):
    rng = np.random.RandomState(seed)
    subjects = {}
    for i in range(1, n_subjects + 1):
        subjects[f"sub-{i:02d}"] = {
            "session": None,
            "epochs": {
                "rest_marker": [_make_epoch(rng, 0.0) for _ in range(n_epochs)],
                "task_marker": [_make_epoch(rng, alpha_boost) for _ in range(n_epochs)],
            },
        }
    table = {"sfreq": _SFREQ, "channels": ["C3", "C4"], "subjects": subjects}
    path = tmp_path / "epoch_table.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def _minimal_spec(**overrides) -> FeatureRecipeSpecV1:
    kwargs = dict(
        dataset_id="feature_test_ds",
        feature_set_id="mne_bids_spectral_v1",
        source_state="rest",
        target_state="task",
        requested_features=["spectral.alpha_power", "qc.valid_epoch_count", "complexity.spectral_entropy"],
        max_subjects=5,
        max_runs=5,
        max_epochs_per_state=10,
        max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={
            "spectral.alpha_power": "Mean relative alpha-band power over valid epochs.",
            "qc.valid_epoch_count": "Count of valid epochs used per state.",
            "complexity.spectral_entropy": "Normalized Shannon entropy of the Welch PSD.",
        },
        input_kind="epoch_table",
        limitations=["synthetic fixture test"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return FeatureRecipeSpecV1.make(**kwargs)


# ── compute_features_for_epochs (unit-level) ──────────────────────────────


def test_compute_features_deterministic():
    rng = np.random.RandomState(42)
    epochs = [np.array(_make_epoch(rng, 0.0)) for _ in range(3)]
    result1 = compute_features_for_epochs(
        epochs, sfreq=_SFREQ, requested_features=["spectral.alpha_power"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    result2 = compute_features_for_epochs(
        epochs, sfreq=_SFREQ, requested_features=["spectral.alpha_power"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    assert result1 == result2


def test_compute_features_empty_epochs_returns_nan():
    result = compute_features_for_epochs(
        [], sfreq=_SFREQ, requested_features=["spectral.alpha_power", "qc.valid_epoch_count"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    assert np.isnan(result["spectral.alpha_power"])
    assert np.isnan(result["qc.valid_epoch_count"])


def test_alpha_power_discriminates_injected_alpha():
    rng = np.random.RandomState(7)
    rest_epochs = [np.array(_make_epoch(rng, 0.0)) for _ in range(5)]
    task_epochs = [np.array(_make_epoch(rng, 5.0)) for _ in range(5)]
    rest_result = compute_features_for_epochs(
        rest_epochs, sfreq=_SFREQ, requested_features=["spectral.alpha_power"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    task_result = compute_features_for_epochs(
        task_epochs, sfreq=_SFREQ, requested_features=["spectral.alpha_power"],
        frequency_bands={"alpha": [8.0, 13.0]},
    )
    assert task_result["spectral.alpha_power"] > rest_result["spectral.alpha_power"]


def test_qc_channel_count_and_duration():
    rng = np.random.RandomState(1)
    epochs = [np.array(_make_epoch(rng, 0.0)) for _ in range(4)]
    result = compute_features_for_epochs(
        epochs, sfreq=_SFREQ, requested_features=["qc.channel_count", "qc.duration_seconds"],
        frequency_bands={}, epoch_length_seconds=2.0,
    )
    assert result["qc.channel_count"] == 2.0
    assert result["qc.duration_seconds"] == 8.0  # 4 epochs * 2s


def test_qc_missing_value_fraction():
    epoch = np.array([[1.0, np.nan, 3.0, 4.0], [1.0, 2.0, np.nan, 4.0]])
    result = compute_features_for_epochs(
        [epoch], sfreq=_SFREQ, requested_features=["qc.missing_value_fraction"], frequency_bands={},
    )
    assert result["qc.missing_value_fraction"] == pytest.approx(2 / 8)


# ── epoch_table extraction (full pipeline) ────────────────────────────────


def test_epoch_table_writes_derived_features_csv(tmp_path):
    table_path = _write_epoch_table(tmp_path)
    spec = _minimal_spec()
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/test-epoch-table-1")
    try:
        assert features_path.exists()
        text = features_path.read_text(encoding="utf-8")
        assert "feature_name" in text.splitlines()[0]
        assert len(result.rows) == 2 * 3  # 2 subjects x 3 features
    finally:
        _cleanup(features_path.parent)


def test_epoch_table_writes_mapping_compatible_with_adapter(tmp_path):
    from adapters.validation import validate_mapping

    table_path = _write_epoch_table(tmp_path)
    spec = _minimal_spec()
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/test-epoch-table-2")
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        assert validate_mapping(mapping) == []
    finally:
        _cleanup(features_path.parent)


def test_epoch_table_computes_deterministic_feature_values(tmp_path):
    table_path = _write_epoch_table(tmp_path)
    spec = _minimal_spec()
    result1 = run_feature_recipe(spec, epoch_table_path=table_path)
    result2 = run_feature_recipe(spec, epoch_table_path=table_path)
    values1 = sorted((r["subject_id"], r["feature_name"], r["source_value"], r["target_value"]) for r in result1.rows)
    values2 = sorted((r["subject_id"], r["feature_name"], r["source_value"], r["target_value"]) for r in result2.rows)
    assert values1 == values2


def test_epoch_table_does_not_fabricate_null_control(tmp_path):
    table_path = _write_epoch_table(tmp_path)
    spec = _minimal_spec()
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/test-epoch-table-3")
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        assert mapping["null_control_status"] == "not_provided"
    finally:
        _cleanup(features_path.parent)


def test_epoch_table_records_preprocessing_provenance(tmp_path):
    table_path = _write_epoch_table(tmp_path)
    spec = _minimal_spec()
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, "outputs/feature_recipes/test-epoch-table-4")
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        assert mapping["preprocessing_provenance"]["recipe"] == "adapters.mne_bids_feature_recipe"
        assert mapping["preprocessing_provenance"]["recipe_id"] == spec.recipe_id
    finally:
        _cleanup(features_path.parent)


def test_respects_max_subjects(tmp_path):
    table_path = _write_epoch_table(tmp_path, n_subjects=5)
    spec = _minimal_spec(max_subjects=2)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    assert len(result.subjects_used) + len(result.skipped_subjects) <= 5
    assert len(result.subjects_used) <= 2


def test_respects_max_epochs_per_state(tmp_path):
    table_path = _write_epoch_table(tmp_path, n_subjects=1, n_epochs=20)
    spec = _minimal_spec(max_subjects=1, max_epochs_per_state=3, max_total_epochs=1000)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    assert result.qc_summary["epoch_counts_by_subject"]["sub-01"]["rest"] == 3
    assert result.qc_summary["epoch_counts_by_subject"]["sub-01"]["task"] == 3


def test_respects_max_total_epochs(tmp_path):
    table_path = _write_epoch_table(tmp_path, n_subjects=3, n_epochs=10)
    spec = _minimal_spec(max_subjects=3, max_epochs_per_state=10, max_total_epochs=8)
    result = run_feature_recipe(spec, epoch_table_path=table_path)
    total_used = result.qc_summary["total_source_epochs"] + result.qc_summary["total_target_epochs"]
    assert total_used <= 8


def test_skips_subject_missing_states_with_explicit_reason(tmp_path):
    table = {
        "sfreq": _SFREQ, "channels": ["C3", "C4"],
        "subjects": {"sub-01": {"session": None, "epochs": {"rest_marker": [_make_epoch(np.random.RandomState(0))]}}},
    }
    path = tmp_path / "epoch_table.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    spec = _minimal_spec()
    result = run_feature_recipe(spec, epoch_table_path=path)
    assert result.subjects_used == []
    assert result.skipped_subjects
    assert "missing epochs" in result.skipped_subjects[0]["reason"]


def test_epoch_table_missing_file_raises():
    spec = _minimal_spec()
    with pytest.raises(FeatureRecipeError):
        run_feature_recipe(spec, epoch_table_path="/tmp/does-not-exist-recipe-test.json")


def test_epoch_table_requires_path_argument():
    spec = _minimal_spec()
    with pytest.raises(FeatureRecipeError):
        run_feature_recipe(spec, epoch_table_path=None)


def _cleanup(path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


# ── bids_raw extraction (real MNE, synthetic in-test fixture only) ───────


def _write_bids_raw_fixture(tmp_path):
    import mne

    rng = np.random.RandomState(3)
    sfreq = 100.0
    n_seconds = 20
    n_samples = int(sfreq * n_seconds)
    t = np.arange(n_samples) / sfreq
    sig1 = rng.randn(n_samples) * 1e-5
    sig2 = rng.randn(n_samples) * 1e-5
    mask = (t >= 10) & (t < 14)
    sig1[mask] += np.sin(2 * np.pi * 10 * t[mask]) * 3e-5
    sig2[mask] += np.sin(2 * np.pi * 10 * t[mask]) * 3e-5

    info = mne.create_info(["C3", "C4"], sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(np.vstack([sig1, sig2]), info, verbose=False)

    root = tmp_path / "bids_root" / "sub-01" / "eeg"
    root.mkdir(parents=True, exist_ok=True)
    raw.save(str(root / "sub-01_task-rest_eeg.fif"), overwrite=True, verbose=False)
    (root / "sub-01_task-rest_events.tsv").write_text(
        "onset\tduration\ttrial_type\n0.0\t2.0\trest_marker\n10.0\t2.0\ttask_marker\n", encoding="utf-8"
    )
    return tmp_path / "bids_root"


def test_bids_raw_extraction_on_real_synthetic_mne_fixture(tmp_path):
    pytest.importorskip("mne")
    bids_root = _write_bids_raw_fixture(tmp_path)
    spec = _minimal_spec(
        input_kind="bids_raw", bids_root=str(bids_root),
        requested_features=["spectral.alpha_power", "qc.duration_seconds"],
        feature_definitions={
            "spectral.alpha_power": "Mean relative alpha-band power over valid epochs.",
            "qc.duration_seconds": "Total signal duration used per state.",
        },
    )
    result = run_feature_recipe(spec)
    assert result.subjects_used == ["sub-01"]
    by_feature = {r["feature_name"]: r for r in result.rows}
    assert by_feature["spectral.alpha_power"]["target_value"] > by_feature["spectral.alpha_power"]["source_value"]
    assert by_feature["qc.duration_seconds"]["artifact_path"] == "sub-01/eeg/sub-01_task-rest_eeg.fif"


def test_bids_raw_skips_unmapped_events(tmp_path):
    pytest.importorskip("mne")
    import mne

    root = tmp_path / "bids_root2" / "sub-01" / "eeg"
    root.mkdir(parents=True, exist_ok=True)
    info = mne.create_info(["C3"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.RandomState(0).randn(1, 1000) * 1e-5, info, verbose=False)
    raw.save(str(root / "sub-01_task-rest_eeg.fif"), overwrite=True, verbose=False)
    (root / "sub-01_task-rest_events.tsv").write_text(
        "onset\tduration\ttrial_type\n0.0\t2.0\trest_marker\n3.0\t2.0\tunmapped_blink\n5.0\t2.0\ttask_marker\n",
        encoding="utf-8",
    )
    spec = _minimal_spec(input_kind="bids_raw", bids_root=str(tmp_path / "bids_root2"))
    result = run_feature_recipe(spec)
    assert any(e["trial_type"] == "unmapped_blink" for e in result.skipped_events)


def test_bids_raw_missing_root_raises():
    spec = _minimal_spec(input_kind="bids_raw", bids_root="/tmp/does-not-exist-bids-root")
    with pytest.raises(FeatureRecipeError):
        run_feature_recipe(spec)
