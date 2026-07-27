from __future__ import annotations

import csv
import json

from tools.command_center.real_results_adapter import (
    build_command_center_registry,
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
