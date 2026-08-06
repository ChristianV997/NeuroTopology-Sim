from __future__ import annotations

import csv
import json

import pytest

from tools.command_center.real_results_adapter import (
    build_command_center_registry,
    build_pitnn_cohort_persistence_artifact,
    build_pitnn_cohort_spatial_artifact,
    build_real_results,
    get_downloadable_artifact,
    build_visualization_payload,
)
from tools.visualization.osc_broadcaster import frames, write_jsonl


def _write_csv(path):
    fields = ["row_id", "subject_id", "task_label", "window_id", "window_start_s", "window_end_s", "q_net", "q_abs", "f_dress", "defect_density", "topology_quality", "null_method", "warnings", "source_file"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"row_id": "one", "subject_id": "sub-01", "task_label": "awake", "window_id": "win-0", "window_start_s": "0", "window_end_s": "4", "q_net": "0.1", "q_abs": "0.2", "f_dress": "0.3", "defect_density": "0.02", "topology_quality": "1", "null_method": "real_none", "warnings": "", "source_file": "demo"})
        writer.writerow({"row_id": "two", "subject_id": "sub-01", "task_label": "sed2", "window_id": "win-1", "window_start_s": "4", "window_end_s": "8", "q_net": "0.2", "q_abs": "0.3", "f_dress": "0.4", "defect_density": "0.03", "topology_quality": "0.9", "null_method": "real_none", "warnings": "", "source_file": "demo"})


def test_adapter_parses_manifest_csv_and_report(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"processed_subjects": {"sub-01": {}}, "failed_subjects": {}}), encoding="utf-8")
    (tmp_path / "REPORT_TEST.md").write_text("# report", encoding="utf-8")
    _write_csv(tmp_path / "sub-01_features_t.csv")
    payload = build_real_results(tmp_path)
    assert payload["status"] == "available"
    assert payload["state_order"] == ["awake", "sed2"]
    assert len(payload["windows"]) == 2
    assert payload["subject_summaries"][0]["subject_id"] == "sub-01"
    assert payload["subject_summaries"][0]["states"][1]["task_label"] == "sed2"
    assert payload["data_quality"]["level_t_artifact_count"] == 1
    assert payload["spatial_artifact"]["status"] == "unavailable"
    assert payload["metric_provenance"]["f_dress"].startswith("topology dressing proxy")


def test_visualization_and_jsonl_replay(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"processed_subjects": {}, "failed_subjects": {}}), encoding="utf-8")
    _write_csv(tmp_path / "sub-01_features_t.csv")
    payload = build_visualization_payload(tmp_path)
    assert len(payload["frames"]) == 2
    assert len(payload["subject_summaries"]) == 1
    assert len(list(frames(tmp_path))) == 2
    destination = tmp_path / "replay.jsonl"
    assert write_jsonl(destination, tmp_path) == 2
    assert len(destination.read_text(encoding="utf-8").splitlines()) == 2


def test_registry_exposes_only_allowlisted_downloads(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"processed_subjects": {"sub-01": {}}, "failed_subjects": {}}), encoding="utf-8")
    (tmp_path / "REPORT_TEST.md").write_text("# report", encoding="utf-8")
    _write_csv(tmp_path / "sub-01_features_t.csv")
    registry = build_command_center_registry(tmp_path)
    assert registry["data_mode"] == "real"
    assert registry["dataset_registry"][0]["participant_count"] == 1
    assert registry["command_registry"][0]["execution_allowed"] is False
    assert get_downloadable_artifact("manifest", tmp_path) == tmp_path / "manifest.json"
    assert get_downloadable_artifact("../../manifest", tmp_path) is None


def _write_pitnn_cohort_subject(root, subject_id, *, awake=True, sedated=True, bottleneck=0.5):
    (root / "subjects").mkdir(parents=True, exist_ok=True)
    def snapshot():
        return {
            "beta1": 2,
            "channel_coordinates": [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
            "phase": [0.1, 0.2, 0.3],
            "coordinate_frame": "sensor_2d_projection_of_standard_1020_montage",
            "defects": {
                "triangle_indices": [[0, 1, 2]],
                "signed_winding": [0.1],
                "centroid_xy": [[0.33, 0.33]],
                "chirality": [1],
                "n_valid_triangles": 1,
            },
            "wave_vectors": None,
            "h1_cycles": [{"birth_cell": [0, 1], "death_cell": [0, 2], "birth": 0.1, "death": 0.4}],
            "zone_band_power": {
                "frontal": {
                    "bands_power_rel": {"delta": 0.3, "theta": 0.1, "alpha": 0.05, "beta": 0.02, "gamma_low": 0.01},
                    "n_channels": 5,
                    "centroid_xy": [0.1, 0.9],
                },
            },
            "quality_control": {"n_channels": 3, "all_finite": True},
        }
    record = {
        "subject": subject_id,
        "cubical_h1_bottleneck_distance_last_window": bottleneck,
        "spatial": {
            "awake": snapshot() if awake else None,
            "sedated": snapshot() if sedated else None,
        },
    }
    (root / "subjects" / f"{subject_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_pitnn_cohort_spatial_artifact_unavailable_when_no_subjects_dir(tmp_path):
    result = build_pitnn_cohort_spatial_artifact(tmp_path / "does_not_exist")
    assert result["status"] == "unavailable"
    assert "channel_coordinates" in result["required_fields"]


def test_pitnn_cohort_spatial_artifact_unavailable_when_no_run_had_export_spatial(tmp_path):
    (tmp_path / "subjects").mkdir()
    (tmp_path / "subjects" / "sub-01.json").write_text(
        json.dumps({"subject": "sub-01", "spatial": {"awake": None, "sedated": None}}), encoding="utf-8"
    )
    result = build_pitnn_cohort_spatial_artifact(tmp_path)
    assert result["status"] == "unavailable"
    assert "export-spatial" in result["reason"]


def test_pitnn_cohort_spatial_artifact_available_with_real_defect_map(tmp_path):
    _write_pitnn_cohort_subject(tmp_path, "sub-1010", bottleneck=0.42)
    result = build_pitnn_cohort_spatial_artifact(tmp_path)
    assert result["status"] == "available"
    assert result["subject_count"] == 1
    subject = result["subjects"][0]
    assert subject["subject_id"] == "sub-1010"
    assert set(subject["conditions"]) == {"awake", "sedated"}
    assert subject["bottleneck_distance_h1_last_window"] == pytest.approx(0.42)
    assert subject["conditions"]["awake"]["wave_vectors"] is None
    assert subject["conditions"]["awake"]["defects"]["n_valid_triangles"] == 1
    assert subject["conditions"]["awake"]["h1_cycles"] == [
        {"birth_cell": [0, 1], "death_cell": [0, 2], "birth": 0.1, "death": 0.4}
    ]
    assert subject["conditions"]["awake"]["zone_band_power"]["frontal"]["bands_power_rel"]["delta"] == 0.3
    assert subject["conditions"]["awake"]["zone_band_power"]["frontal"]["n_channels"] == 5
    assert subject["conditions"]["awake"]["zone_band_power"]["frontal"]["centroid_xy"] == [0.1, 0.9]


def test_pitnn_cohort_spatial_artifact_skips_subjects_with_no_snapshot(tmp_path):
    _write_pitnn_cohort_subject(tmp_path, "sub-01", awake=False, sedated=False)
    _write_pitnn_cohort_subject(tmp_path, "sub-02")
    result = build_pitnn_cohort_spatial_artifact(tmp_path)
    assert result["status"] == "available"
    assert result["subject_count"] == 1
    assert result["subjects"][0]["subject_id"] == "sub-02"


def test_visualization_payload_includes_pitnn_cohort_spatial_artifact(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(json.dumps({"processed_subjects": {}, "failed_subjects": {}}), encoding="utf-8")
    _write_csv(tmp_path / "sub-01_features_t.csv")

    cohort_root = tmp_path / "pitnn_cohort"
    _write_pitnn_cohort_subject(cohort_root, "sub-1010")
    monkeypatch.setenv("NEUROTOPOLOGY_PITNN_COHORT_ROOT", str(cohort_root))

    payload = build_visualization_payload(tmp_path)
    assert payload["spatial_artifact"]["status"] == "unavailable"  # CSV path is untouched
    assert payload["pitnn_cohort_spatial_artifact"]["status"] == "available"
    assert payload["pitnn_cohort_spatial_artifact"]["subject_count"] == 1


def test_registry_reflects_pitnn_cohort_spatial_availability(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(json.dumps({"processed_subjects": {"sub-01": {}}, "failed_subjects": {}}), encoding="utf-8")
    _write_csv(tmp_path / "sub-01_features_t.csv")

    cohort_root = tmp_path / "pitnn_cohort"
    _write_pitnn_cohort_subject(cohort_root, "sub-1010")
    monkeypatch.setenv("NEUROTOPOLOGY_PITNN_COHORT_ROOT", str(cohort_root))

    registry = build_command_center_registry(tmp_path)
    assert registry["guardrails"]["pitnn_cohort_spatial_data"]["status"] == "available"
    pilot = next(p for p in registry["proposed_runs"] if p["proposal_id"] == "spatial-topology-pilot")
    assert pilot["status"] == "available"


def _write_pitnn_cohort_subject_with_persistence(
    root, subject_id, *, awake=True, sedated=True, bottleneck=0.19,
    awake_windows_h1=None, sedated_windows_h1=None,
):
    """Mirror tools/stream_pitnn_cohort_ds005620.py's real record shape for the
    --export-persistence path: topology_windows.{label}[-1].cubical_persistence.
    diagrams['1'] is exactly what build_pitnn_cohort_persistence_artifact reads.
    `*_windows_h1`, when given, is a list of per-window H1 diagrams (real windows,
    mirroring topology_windows.{label} having multiple rows), so multi-window
    (vineyard) behavior can be exercised; otherwise a single window is written."""
    (root / "subjects").mkdir(parents=True, exist_ok=True)

    def window(h1, idx=0):
        return {
            "window": idx, "start_s": float(idx * 10), "channels": 3, "beta1": 1,
            "filtration_beta1_max": 1, "integrated_landscape_area": 0.01,
            "mean_plv": 0.5, "q_spatial": 0.0,
            "cubical_persistence": {
                "betti_numbers": [1, 0, 0],
                "diagrams": {"0": [[0.0, 1.0]], "1": h1},
                "statistics": {"0": {}, "1": {}},
            },
        }

    awake_rows = (
        [window(h1, i) for i, h1 in enumerate(awake_windows_h1)] if awake_windows_h1 is not None
        else ([window([[0.1, 0.2]])] if awake else [])
    )
    sedated_rows = (
        [window(h1, i) for i, h1 in enumerate(sedated_windows_h1)] if sedated_windows_h1 is not None
        else ([window([[0.15, 0.35], [0.2, 0.4]])] if sedated else [])
    )
    record = {
        "subject": subject_id,
        "cubical_h1_bottleneck_distance_last_window": bottleneck,
        "topology_windows": {"awake": awake_rows, "sedated": sedated_rows},
    }
    (root / "subjects" / f"{subject_id}.json").write_text(json.dumps(record), encoding="utf-8")


def test_pitnn_cohort_persistence_artifact_unavailable_when_no_subjects_dir(tmp_path):
    result = build_pitnn_cohort_persistence_artifact(tmp_path / "does_not_exist")
    assert result["status"] == "unavailable"


def test_pitnn_cohort_persistence_artifact_unavailable_without_export_persistence(tmp_path):
    """A cohort run without --export-persistence has topology_windows but no
    cubical_persistence key on each row -- must report unavailable, not an
    empty-but-'available' payload."""
    (tmp_path / "subjects").mkdir()
    record = {
        "subject": "sub-01",
        "topology_windows": {"awake": [{"window": 0, "beta1": 1}], "sedated": [{"window": 0, "beta1": 2}]},
    }
    (tmp_path / "subjects" / "sub-01.json").write_text(json.dumps(record), encoding="utf-8")
    result = build_pitnn_cohort_persistence_artifact(tmp_path)
    assert result["status"] == "unavailable"


def test_pitnn_cohort_persistence_artifact_available_with_real_diagrams(tmp_path):
    _write_pitnn_cohort_subject_with_persistence(tmp_path, "sub-1010", bottleneck=0.194)
    result = build_pitnn_cohort_persistence_artifact(tmp_path)
    assert result["status"] == "available"
    assert result["subject_count"] == 1
    subject = result["subjects"][0]
    assert subject["subject_id"] == "sub-1010"
    assert subject["diagrams_h1"]["awake"] == [[0.1, 0.2]]
    assert subject["diagrams_h1"]["sedated"] == [[0.15, 0.35], [0.2, 0.4]]
    assert subject["bottleneck_distance_h1_last_window"] == pytest.approx(0.194)
    # Single real window per condition -> the vineyard field has exactly one
    # entry, matching diagrams_h1 (no fabricated extra points).
    assert subject["diagrams_h1_by_window"]["awake"] == [[[0.1, 0.2]]]
    assert subject["diagrams_h1_by_window"]["sedated"] == [[[0.15, 0.35], [0.2, 0.4]]]


def test_pitnn_cohort_persistence_artifact_vineyard_carries_every_real_window(tmp_path):
    """A cohort run with 3 real windows per condition (this repo's actual
    streaming cadence) must expose all 3 in diagrams_h1_by_window, not just
    the last one that diagrams_h1 reports -- the whole point of the field."""
    awake_windows = [[[0.1, 0.2]], [[0.12, 0.25]], [[0.11, 0.3]]]
    sedated_windows = [[[0.2, 0.5]], [[0.25, 0.6]], [[0.3, 0.7]]]
    _write_pitnn_cohort_subject_with_persistence(
        tmp_path, "sub-1010",
        awake_windows_h1=awake_windows, sedated_windows_h1=sedated_windows,
    )
    result = build_pitnn_cohort_persistence_artifact(tmp_path)
    subject = result["subjects"][0]
    assert subject["diagrams_h1_by_window"]["awake"] == awake_windows
    assert subject["diagrams_h1_by_window"]["sedated"] == sedated_windows
    # diagrams_h1 (last-window, existing consumer) must still match the last
    # entry of the vineyard -- both describe the same window.
    assert subject["diagrams_h1"]["awake"] == awake_windows[-1]
    assert subject["diagrams_h1"]["sedated"] == sedated_windows[-1]


def test_pitnn_cohort_persistence_artifact_skips_subjects_missing_diagrams(tmp_path):
    _write_pitnn_cohort_subject_with_persistence(tmp_path, "sub-01", awake=False, sedated=False)
    _write_pitnn_cohort_subject_with_persistence(tmp_path, "sub-02")
    result = build_pitnn_cohort_persistence_artifact(tmp_path)
    assert result["status"] == "available"
    assert result["subject_count"] == 1
    assert result["subjects"][0]["subject_id"] == "sub-02"


def test_visualization_payload_includes_pitnn_cohort_persistence_artifact(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(json.dumps({"processed_subjects": {}, "failed_subjects": {}}), encoding="utf-8")
    _write_csv(tmp_path / "sub-01_features_t.csv")

    cohort_root = tmp_path / "pitnn_cohort"
    _write_pitnn_cohort_subject_with_persistence(cohort_root, "sub-1010")
    monkeypatch.setenv("NEUROTOPOLOGY_PITNN_COHORT_ROOT", str(cohort_root))

    payload = build_visualization_payload(tmp_path)
    assert payload["pitnn_cohort_persistence_artifact"]["status"] == "available"
    assert payload["pitnn_cohort_persistence_artifact"]["subject_count"] == 1
