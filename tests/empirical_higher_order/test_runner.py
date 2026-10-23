from __future__ import annotations

import hashlib
import json
import weakref
from pathlib import Path

import numpy as np
import pytest

from analysis.empirical_higher_order import runner as runner_module
from analysis.empirical_higher_order import validation as validation_module
from analysis.empirical_higher_order.runner import run_empirical
from analysis.empirical_higher_order.schema import finite_json
from analysis.empirical_higher_order.validation import ReadinessState, validate_manifest


def _manifest(tmp_path: Path, subjects: int = 2, *, synthetic=False, respiration=False, montage=True, labels=True):
    data = tmp_path / "dataset.bin"; data.write_bytes(b"declared local dataset")
    recordings = []
    for subject_index in range(subjects):
        subject = f"sub-{subject_index:02d}"
        for condition_index, condition in enumerate(("rest", "transition")):
            stem = tmp_path / f"{subject}_{condition}"
            n = 6
            rng = np.random.default_rng(subject_index * 10 + condition_index)
            for family, width in (("psd", 3), ("pairwise_fc", 2), ("triadic_fc", 2), ("directed_hypergraph", 2)):
                np.save(stem.with_name(stem.name + f"_{family}.npy"), rng.normal(size=(n, width)))
            np.save(stem.with_name(stem.name + "_target.npy"), np.array([0, 1, 0, 1, 0, 1]))
            feature_times = np.arange(n) + subject_index * 20 + condition_index * 10
            np.save(stem.with_name(stem.name + "_time.npy"), feature_times)
            artifacts = {
                family: stem.with_name(stem.name + f"_{family}.npy")
                for family in ("psd", "pairwise_fc", "triadic_fc", "directed_hypergraph")
            }
            artifacts["target"] = stem.with_name(stem.name + "_target.npy")
            artifacts["timestamps"] = stem.with_name(stem.name + "_time.npy")
            recordings.append({
                "subject_id": subject, "session_id": "ses-01", "run_id": f"run-{condition_index+1:02d}",
                "condition_label": condition if labels else "", "pairing_key": "paired-cohort",
                "sampling_rate_hz": 250, "channel_count": 3,
                "montage_coordinates": [[0, 0, 0], [1, 0, 0], [0, 1, 0]] if montage else None,
                "recording_quality_state": "PASS", "origin": "synthetic" if synthetic else "empirical",
                "feature_paths": {family: f"{stem.name}_{family}.npy" for family in ("psd", "pairwise_fc", "triadic_fc", "directed_hypergraph")},
                "target_path": f"{stem.name}_target.npy", "timestamps_path": f"{stem.name}_time.npy",
                "artifact_checksums": {name: hashlib.sha256(artifact.read_bytes()).hexdigest() for name, artifact in artifacts.items()},
                "target_timestamps": (feature_times + 1).tolist(),
                "physiology": {"respiration": "resp.npy"} if respiration else {},
            })
    manifest = {"schema_version": "NeuroTopologySim.EmpiricalHigherOrderManifest.v1", "dataset_id": "fixture",
                "dataset_path": data.name, "dataset_checksum": hashlib.sha256(data.read_bytes()).hexdigest(),
                "source_type": "synthetic" if synthetic else "empirical_local", "synthetic": synthetic,
                "provenance": {"source": "local fixture", "complete": True},
                "prediction_horizon": 1, "target_definition": "declared transition", "recordings": recordings}
    path = tmp_path / "manifest.json"; path.write_text(json.dumps(manifest), encoding="utf-8"); return path


def test_empty_data(tmp_path):
    path = tmp_path / "empty.json"; path.write_text(json.dumps({"recordings": []}), encoding="utf-8")
    assert validate_manifest(path).status is ReadinessState.NO_DATA


def test_invalid_checksum(tmp_path):
    path = _manifest(tmp_path); data = json.loads(path.read_text()); data["dataset_checksum"] = "0" * 64; path.write_text(json.dumps(data))
    assert validate_manifest(path).status is ReadinessState.INCONCLUSIVE


def test_ambiguous_labels(tmp_path):
    path = _manifest(tmp_path, labels=False)
    assert validate_manifest(path).status is ReadinessState.INCONCLUSIVE


def test_one_pair_is_descriptive_only(tmp_path):
    assert validate_manifest(_manifest(tmp_path, subjects=1)).status is ReadinessState.INSUFFICIENT_PAIRED_SUBJECTS


def test_multiple_pairs_are_forecasting_ready(tmp_path):
    report = run_empirical(_manifest(tmp_path, subjects=2))
    assert report["status"] == ReadinessState.READY_FOR_FORECASTING.value
    assert report["scientific_pass"] is False and report["formal_bayes_factor"] is None
    assert "FORMAL_FORECAST_EVIDENCE" not in {entry["incremental_status"] for entry in report["model_ladder"] if "incremental_status" in entry}


def test_missing_respiration_is_explicit(tmp_path):
    report = run_empirical(_manifest(tmp_path, respiration=False))
    assert report["missingness"]["respiration"]["state"] == "MISSING_OPTIONAL_PHYSIOLOGY"


def test_missing_montage_is_not_ready(tmp_path):
    assert validate_manifest(_manifest(tmp_path, montage=False)).status is ReadinessState.INCOMPLETE_PROVENANCE


def test_synthetic_input_never_forecasts(tmp_path):
    assert validate_manifest(_manifest(tmp_path, synthetic=True)).status is ReadinessState.SYNTHETIC_DEMO_ONLY


def test_bounded_memory_contract(tmp_path, monkeypatch):
    loaded_feature_arrays = []
    max_live_previous_feature_arrays = 0
    original_load_recording = runner_module._load_recording

    def tracked_load_recording(record):
        nonlocal loaded_feature_arrays, max_live_previous_feature_arrays
        loaded_feature_arrays = [reference for reference in loaded_feature_arrays if reference() is not None]
        max_live_previous_feature_arrays = max(
            max_live_previous_feature_arrays, len(loaded_feature_arrays)
        )
        result = original_load_recording(record)
        arrays = result[2] if len(result) == 4 else result[1]
        loaded_feature_arrays.extend(weakref.ref(array) for array in arrays.values())
        return result

    monkeypatch.setattr(runner_module, "_load_recording", tracked_load_recording)
    report = run_empirical(_manifest(tmp_path, subjects=3))
    assert max_live_previous_feature_arrays == 0
    assert report["bounded_memory"]["max_recordings_loaded"] == 1
    assert report["bounded_memory"]["feature_arrays_retained_between_recordings"] == 0


def test_auc_metrics_use_linear_size_rank_arrays_and_preserve_ties(monkeypatch):
    original_mean = runner_module.np.mean

    def reject_pairwise_mean(values, *args, **kwargs):
        assert np.asarray(values).ndim <= 1, "AUROC must not allocate pairwise score matrices"
        return original_mean(values, *args, **kwargs)

    monkeypatch.setattr(runner_module.np, "mean", reject_pairwise_mean)
    metrics = runner_module._metrics(
        np.array([0, 0, 1, 1]),
        np.array([0.1, 0.4, 0.4, 0.8]),
    )

    assert metrics["auroc"] == pytest.approx(0.875)


def test_unreadable_dataset_checksum_is_reported_not_raised(tmp_path, monkeypatch):
    path = _manifest(tmp_path)
    dataset_path = (tmp_path / "dataset.bin").resolve()
    original_sha256_file = validation_module.sha256_file

    def fail_dataset_hash(candidate):
        if candidate.resolve() == dataset_path:
            raise OSError("permission denied")
        return original_sha256_file(candidate)

    monkeypatch.setattr(validation_module, "sha256_file", fail_dataset_hash)
    result = validate_manifest(path)

    assert result.status is ReadinessState.INCONCLUSIVE
    assert any("dataset checksum cannot be read" in reason for reason in result.reasons)


def test_subject_split_has_no_train_test_overlap(tmp_path):
    result = run_empirical(_manifest(tmp_path, subjects=3))["model_ladder"][0]
    assert result["subject_split"]["overlap"] == []
    assert set(result["subject_split"]["train_subjects"]).isdisjoint(result["subject_split"]["test_subjects"])


def test_deterministic_and_finite_json(tmp_path):
    path = _manifest(tmp_path); first = run_empirical(path); second = run_empirical(path)
    first.pop("checksum", None); second.pop("checksum", None)
    assert finite_json(first) == finite_json(second)
    json.dumps(first, allow_nan=False)


def test_no_network_manifest_is_rejected(tmp_path):
    path = _manifest(tmp_path); data = json.loads(path.read_text()); data["dataset_path"] = "https://example.invalid/data"; path.write_text(json.dumps(data))
    result = validate_manifest(path)
    assert result.status is ReadinessState.INCONCLUSIVE
    assert any("network" in reason for reason in result.reasons)


def test_manifest_local_path_escape_is_rejected(tmp_path):
    path = _manifest(tmp_path)
    outside = tmp_path.parent / "outside-dataset.bin"
    outside.write_bytes(b"must not be read through the manifest")
    data = json.loads(path.read_text())
    data["dataset_path"] = "../outside-dataset.bin"
    data["dataset_checksum"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    result = validate_manifest(path)
    assert result.status is ReadinessState.INCONCLUSIVE
    assert any("escapes the manifest root" in reason for reason in result.reasons)


def test_missing_or_mismatched_artifact_checksum_is_not_forecasting_ready(tmp_path):
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["recordings"][0]["artifact_checksums"].pop("triadic_fc")
    path.write_text(json.dumps(data))
    assert validate_manifest(path).status is ReadinessState.INCOMPLETE_PROVENANCE

    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["recordings"][0]["artifact_checksums"]["triadic_fc"] = "0" * 64
    path.write_text(json.dumps(data))
    assert validate_manifest(path).status is ReadinessState.INCONCLUSIVE


def test_declared_checksum_for_missing_feature_is_reported_not_raised(tmp_path):
    # Regression (#357): _validate_artifact_checksums hashed each declared artifact without guarding the read, so a
    # declared but absent feature file escaped validate_manifest as FileNotFoundError. main reports INCONCLUSIVE.
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    (tmp_path / data["recordings"][0]["feature_paths"]["triadic_fc"]).unlink()
    assert validate_manifest(path).status is ReadinessState.INCONCLUSIVE


def test_declared_checksum_for_unreadable_feature_is_reported_not_raised(tmp_path):
    # Regression (#357): a feature path that resolves to a directory raised IsADirectoryError from the checksum helper.
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    (tmp_path / "dir_as_feature").mkdir()
    data["recordings"][0]["feature_paths"]["psd"] = "dir_as_feature"
    path.write_text(json.dumps(data))
    assert validate_manifest(path).status is ReadinessState.INCONCLUSIVE


def test_declared_checksum_for_missing_target_is_not_forecasting_ready(tmp_path):
    # Regression (#357): a declared but absent target raised FileNotFoundError. A missing target is never forecasting-ready.
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    (tmp_path / data["recordings"][0]["target_path"]).unlink()
    assert validate_manifest(path).status is not ReadinessState.READY_FOR_FORECASTING


def test_optional_spectra_is_classified(tmp_path):
    report = run_empirical(_manifest(tmp_path))
    assert report["model_ladder"][-1]["status"] == ReadinessState.MISSING_OPTIONAL_DEPENDENCY.value


def test_future_window_leakage_is_inconclusive(tmp_path):
    path = _manifest(tmp_path); data = json.loads(path.read_text()); data["recordings"][0]["target_timestamps"] = [-1, 0, 1, 2, 3, 4]; path.write_text(json.dumps(data))
    assert run_empirical(path)["status"] == ReadinessState.INCONCLUSIVE.value


def test_missing_target_timestamps_is_inconclusive(tmp_path):
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    for recording in data["recordings"]:
        recording.pop("target_timestamps", None)
    path.write_text(json.dumps(data))
    report = run_empirical(path)
    assert report["status"] == ReadinessState.INCONCLUSIVE.value
    assert any("TEMPORAL_LINEAGE_REQUIRED" in reason for reason in report["validation"]["reasons"])


def test_target_timestamp_length_mismatch_is_inconclusive(tmp_path):
    path = _manifest(tmp_path)
    data = json.loads(path.read_text())
    data["recordings"][0]["target_timestamps"] = [1, 2]
    path.write_text(json.dumps(data))
    report = run_empirical(path)
    assert report["status"] == ReadinessState.INCONCLUSIVE.value
    assert any("TEMPORAL_LINEAGE_INVALID" in reason for reason in report["validation"]["reasons"])
