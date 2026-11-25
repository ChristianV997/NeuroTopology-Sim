from __future__ import annotations

import json
from pathlib import Path

from tools.simulation_artifacts.extractor import extract_run, render_markdown
from tools.simulation_artifacts.models import dumps_finite


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _complete_run(tmp_path: Path, *, synthetic=False) -> Path:
    run = tmp_path / "run"
    _write_json(run / "RunRecord.json", {"run_id": "run-001", "run_kind": "psi", "created_at": "2026-09-10T00:00:00Z", "source": "local simulation", "data_mode": "synthetic" if synthetic else "simulation", "synthetic": synthetic, "claim_scope": "computational_artifact", "input": {"seed": 7}, "dependencies": {"python": "3.x"}})
    _write_json(run / "summary.json", {"status": "complete", "parent": "RunRecord.json"})
    _write_json(run / "metrics.json", {"loss": 0.25, "finite": True})
    (run / "metrics.csv").write_text("step,loss\n1,0.25\n", encoding="utf-8")
    _write_json(run / "checkpoint_manifest.json", {"status": "complete", "parent_checkpoint": "RunRecord.json"})
    _write_json(run / "validation_report.json", {"status": "complete"})
    _write_json(run / "resource_telemetry.json", {"peak_memory_mb": 12.5})
    _write_json(run / "null_model.json", {"status": "complete", "p": 0.5})
    return run


def test_clean_complete_run_and_relationships(tmp_path):
    report = extract_run(_complete_run(tmp_path))
    assert report["status"] == "COMPLETE"
    assert report["solver_executed"] is False
    assert report["relationships"]
    assert report["provenance"]["run_id"] == "run-001"
    assert all(item["sha256"] for item in report["artifact_manifest"]["artifacts"])


def test_partial_run_never_complete(tmp_path):
    run = _complete_run(tmp_path)
    (run / "partial_output.json").write_text('{"status":"partial"}', encoding="utf-8")
    assert extract_run(run)["status"] == "PARTIAL"


def test_failed_run_never_complete(tmp_path):
    run = _complete_run(tmp_path)
    (run / "failed.marker").write_text("failed", encoding="utf-8")
    assert extract_run(run)["status"] == "FAILED"


def test_duplicate_content_is_detected(tmp_path):
    run = _complete_run(tmp_path)
    (run / "copy_metrics.json").write_bytes((run / "metrics.json").read_bytes())
    report = extract_run(run)
    assert any(len(item["paths"]) == 2 for item in report["artifact_manifest"]["duplicate_content"])


def test_changed_content_is_not_reused(tmp_path):
    run = _complete_run(tmp_path)
    first = extract_run(run)
    cache = tmp_path / "manifest.json"; cache.write_text(dumps_finite(first), encoding="utf-8")
    metrics = run / "metrics.json"; metrics.write_text('{"finite":true,"loss":0.9}', encoding="utf-8")
    second = extract_run(run, previous_manifest=cache)
    item = next(item for item in second["artifact_manifest"]["artifacts"] if item["relative_path"] == "metrics.json")
    assert item["checksum_reused"] is False


def test_unchanged_content_reuses_checksum_and_removed_is_stale(tmp_path):
    run = _complete_run(tmp_path)
    first = extract_run(run)
    cache = tmp_path / "manifest.json"; cache.write_text(dumps_finite(first), encoding="utf-8")
    (run / "null_model.json").unlink()
    second = extract_run(run, previous_manifest=cache)
    metrics = next(item for item in second["artifact_manifest"]["artifacts"] if item["relative_path"] == "metrics.json")
    assert metrics["checksum_reused"] is True
    assert "null_model.json" in second["diagnostics"]["stale"]


def test_invalid_json_is_blocked(tmp_path):
    run = _complete_run(tmp_path); (run / "bad.json").write_text("{not json", encoding="utf-8")
    assert extract_run(run)["status"] == "BLOCKED"


def test_nonfinite_json_is_blocked(tmp_path):
    run = _complete_run(tmp_path); (run / "bad.json").write_text('{"value": NaN}', encoding="utf-8")
    report = extract_run(run)
    assert report["status"] == "BLOCKED"
    assert any("non-finite" in item for item in report["diagnostics"]["errors"])


def test_missing_provenance_is_incomplete(tmp_path):
    run = _complete_run(tmp_path); (run / "RunRecord.json").write_text('{"run_id":"only-id"}', encoding="utf-8")
    report = extract_run(run)
    assert report["status"] == "INCOMPLETE"
    assert any("missing provenance" in item for item in report["diagnostics"]["errors"])


def test_synthetic_output_is_labeled(tmp_path):
    report = extract_run(_complete_run(tmp_path, synthetic=True))
    assert report["evidence"]["evidence_class"] == "synthetic_demo_only"


def test_deterministic_repeat(tmp_path):
    run = _complete_run(tmp_path)
    first = extract_run(run); second = extract_run(run)
    assert dumps_finite(first) == dumps_finite(second)
    assert render_markdown(first) == render_markdown(second)


def test_no_solver_import_in_extractor_source():
    source = Path("tools/simulation_artifacts/extractor.py").read_text(encoding="utf-8")
    assert "numpy" not in source and "scipy" not in source and "subprocess" not in source


def test_no_network_execution_and_url_rejected(tmp_path):
    try:
        extract_run("https://example.invalid/run")
    except ValueError as exc:
        assert "URL" in str(exc) or "URLs" in str(exc)
    else:
        raise AssertionError("URL input was accepted")


def test_finite_json_report(tmp_path):
    report = extract_run(_complete_run(tmp_path))
    serialized = dumps_finite(report)
    assert "NaN" not in serialized and "Infinity" not in serialized
