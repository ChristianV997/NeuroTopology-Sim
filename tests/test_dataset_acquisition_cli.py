"""Subprocess CLI tests for `python -m dataset_acquisition.export_plan`.
Synthetic fixtures only -- no network access, no raw data download.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from dataset_importers.candidate_record import DatasetCandidateRecordV1

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "dataset_acquisition.export_plan", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _candidate(**overrides) -> DatasetCandidateRecordV1:
    kwargs = dict(
        source_catalog="synthetic_fixture",
        source_dataset_id=overrides.pop("source_dataset_id", "ds-cli-1"),
        display_name="CLI fixture dataset",
        license="CC0",
        license_risk="permissive_low",
        access_status="public",
        download_required="true",
        modalities=["EEG"],
        condition_labels=["rest", "task"],
        subject_count=10,
        transition_readiness="candidate_transition_possible",
        benchmark_role_recommendation="development_candidate",
        risks=["r"],
        limitations=["l"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DatasetCandidateRecordV1.make(**kwargs)


def _write_candidates_file(tmp_path: Path, *candidates: DatasetCandidateRecordV1) -> Path:
    path = tmp_path / "candidates.json"
    payload = {
        "schema": "NeuroTopologySim.DatasetCandidateExport.v1",
        "candidates": [c.to_dict() for c in candidates],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_metadata_only_works(tmp_path):
    candidate = _candidate(source_dataset_id="ds-cli-meta")
    cfile = _write_candidates_file(tmp_path, candidate)
    out = tmp_path / "plan.json"
    result = _run_cli(
        "--candidate-file", str(cfile), "--candidate-id", candidate.candidate_id,
        "--target-root", "outputs/datasets/cli-meta-test", "--requested-action", "metadata_only",
        "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["requested_action"] == "metadata_only"
    assert payload["dry_run"] is True
    assert out.exists()


def test_cli_plan_download_works_without_executing(tmp_path):
    candidate = _candidate(source_dataset_id="ds-cli-plandl")
    cfile = _write_candidates_file(tmp_path, candidate)
    out = tmp_path / "plan.json"
    result = _run_cli(
        "--candidate-file", str(cfile), "--candidate-id", candidate.candidate_id,
        "--target-root", "outputs/datasets/cli-plandl-test", "--requested-action", "plan_download",
        "--disk-limit-mb", "500", "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["disk_limit_bytes"] == 500 * 1024 * 1024
    assert payload["dry_run"] is True

    root = _REPO_ROOT / "outputs" / "datasets" / "cli-plandl-test"
    assert not root.exists()


def test_cli_execute_blocked_without_flags(tmp_path):
    candidate = _candidate(source_dataset_id="ds-cli-execblocked", metadata={"estimated_size_bytes": 1000})
    cfile = _write_candidates_file(tmp_path, candidate)
    plan_path = tmp_path / "plan.json"
    plan_result = _run_cli(
        "--candidate-file", str(cfile), "--candidate-id", candidate.candidate_id,
        "--target-root", "outputs/datasets/cli-execblocked-test", "--requested-action", "execute_download",
        "--acquisition-mode", "local_bids_scan", "--disk-limit-mb", "500", "--out", str(plan_path),
    )
    assert plan_result.returncode == 0, plan_result.stdout
    plan_payload = json.loads(plan_result.stdout)
    assert plan_payload["blocked_reasons"]

    manifest_out = tmp_path / "manifest.json"
    exec_result = _run_cli("--plan", str(plan_path), "--execute", "--manifest-out", str(manifest_out))
    assert exec_result.returncode == 0, exec_result.stdout
    manifest_payload = json.loads(exec_result.stdout)
    assert manifest_payload["execution_status"] == "blocked"


def test_cli_local_scan_works(tmp_path):
    name = "cli-local-scan-test"
    root = _REPO_ROOT / "outputs" / "datasets" / name
    if root.exists():
        shutil.rmtree(root)
    (root / "sub-01" / "eeg").mkdir(parents=True, exist_ok=True)
    (root / "dataset_description.json").write_text('{"Name": "CLI scan fixture"}', encoding="utf-8")
    (root / "participants.tsv").write_text("participant_id\nsub-01\n", encoding="utf-8")
    (root / "sub-01" / "eeg" / "sub-01_task-rest_events.tsv").write_text(
        "onset\tduration\ttrial_type\n0\t1\trest\n", encoding="utf-8"
    )
    try:
        candidate = _candidate(source_dataset_id="ds-cli-localscan")
        cfile = _write_candidates_file(tmp_path, candidate)
        plan_path = tmp_path / "plan.json"
        plan_result = _run_cli(
            "--candidate-file", str(cfile), "--candidate-id", candidate.candidate_id,
            "--target-root", f"outputs/datasets/{name}", "--requested-action", "scan_existing_local",
            "--out", str(plan_path),
        )
        assert plan_result.returncode == 0, plan_result.stdout

        manifest_out = tmp_path / "manifest.json"
        exec_result = _run_cli(
            "--plan", str(plan_path), "--execute", "--manifest-out", str(manifest_out), "--scan-bids-after-acquisition"
        )
        assert exec_result.returncode == 0, exec_result.stdout + exec_result.stderr
        payload = json.loads(exec_result.stdout)
        assert payload["execution_status"] == "acquired"
        assert "bids_metadata_summary" in payload
        manifest_json = json.loads(manifest_out.read_text(encoding="utf-8"))
        assert manifest_json["execution_status"] == "acquired"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cli_output_json_validates_against_schema(tmp_path):
    from dataset_acquisition.acquisition_plan import DatasetAcquisitionPlanV1

    candidate = _candidate(source_dataset_id="ds-cli-validate")
    cfile = _write_candidates_file(tmp_path, candidate)
    out = tmp_path / "plan.json"
    result = _run_cli(
        "--candidate-file", str(cfile), "--candidate-id", candidate.candidate_id,
        "--target-root", "outputs/datasets/cli-validate-test", "--requested-action", "metadata_only",
        "--out", str(out),
    )
    assert result.returncode == 0
    plan = DatasetAcquisitionPlanV1.from_json(out.read_text(encoding="utf-8"))
    assert plan.validate() == []


def test_cli_target_root_outside_allowed_directories_fails(tmp_path):
    candidate = _candidate(source_dataset_id="ds-cli-badroot")
    cfile = _write_candidates_file(tmp_path, candidate)
    out = tmp_path / "plan.json"
    result = _run_cli(
        "--candidate-file", str(cfile), "--candidate-id", candidate.candidate_id,
        "--target-root", "/etc/evil", "--requested-action", "metadata_only", "--out", str(out),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert not out.exists()


def test_cli_missing_candidate_id_fails(tmp_path):
    candidate = _candidate(source_dataset_id="ds-cli-nomatch")
    cfile = _write_candidates_file(tmp_path, candidate)
    out = tmp_path / "plan.json"
    result = _run_cli(
        "--candidate-file", str(cfile), "--candidate-id", "not-a-real-id",
        "--target-root", "outputs/datasets/cli-nomatch-test", "--requested-action", "metadata_only",
        "--out", str(out),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_missing_required_args_fails():
    result = _run_cli("--requested-action", "metadata_only")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_never_downloads_raw_data():
    source = (_REPO_ROOT / "dataset_acquisition" / "export_plan.py").read_text(encoding="utf-8")
    for banned in (".get_data(", "requests.get(", "urllib.request"):
        assert banned not in source
