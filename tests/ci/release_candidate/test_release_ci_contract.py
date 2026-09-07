"""Focused regression tests for the release-candidate CI contract."""

from pathlib import Path
import json

import pytest
import yaml

from scripts.validate_release_ci_contract import (
    audit_workflows,
    classify_failure,
    make_diagnostic,
)


ROOT = Path(__file__).resolve().parents[3]


def _write_workflow(root: Path, filename: str, jobs: dict, *, manual: bool = False) -> None:
    directory = root / ".github" / "workflows"
    directory.mkdir(parents=True, exist_ok=True)
    events = {"workflow_dispatch": {}} if manual else {"pull_request": {}}
    (directory / filename).write_text(
        yaml.safe_dump({"name": filename, "on": events, "jobs": jobs}, sort_keys=False),
        encoding="utf-8",
    )


def _job(*, name: str = "job", run: str = "true", timeout: int | None = 10, artifact: bool = False) -> dict:
    value = {
        "name": name,
        "runs-on": "ubuntu-latest",
        "steps": [{"run": run}],
    }
    if timeout is not None:
        value["timeout-minutes"] = timeout
    if artifact:
        value["steps"].append({"if": "always()", "uses": "actions/upload-artifact@v4", "with": {"path": "diagnostic.json"}})
    return value


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("AssertionError: 2 failed", "test_failure"),
        ("ModuleNotFoundError: No module named mne", "import_failure"),
        ("pip install: ResolutionImpossible", "dependency_resolution_failure"),
        ("OSError: [Errno 28] No space left on device", "disk_exhaustion"),
        ("Killed by the OOM killer", "memory_exhaustion"),
        ("Temporary failure in name resolution", "network_failure"),
        ("billing limit reached; no available runners", "billing_runner_blockage"),
        ("workflow has undefined needs", "workflow_configuration_failure"),
        ("BlobNotFound and no steps were recorded", "unknown_infrastructure_failure"),
    ],
)
def test_failure_classification_distinguishes_root_causes(message: str, expected: str) -> None:
    assert classify_failure(message)["failure_classification"] == expected


def test_undefined_needs_are_reported(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "broken.yml",
        {"broken": _job(run="pytest tests", artifact=True) | {"needs": "missing-job"}},
    )
    report = audit_workflows(tmp_path)
    assert any(issue["code"] == "undefined-needs" for issue in report["issues"])


def test_cpu_aggregate_profile_timeout_and_artifact_contracts_are_reported(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "broken.yml", {"core-tests": _job(name="core-tests", run="pip install -r requirements.txt\npytest tests", timeout=None)})
    report = audit_workflows(tmp_path)
    codes = {issue["code"] for issue in report["issues"]}
    assert {"aggregate-profile-in-cpu-job", "missing-timeout", "missing-failure-artifact"} <= codes


def test_duplicate_required_checks_are_reported(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "required-checks.yml", {"core-tests": _job(name="core-tests", run="pytest tests", artifact=True)})
    _write_workflow(tmp_path, "duplicate.yml", {"other": _job(name="core-tests", run="pytest tests", artifact=True)})
    report = audit_workflows(tmp_path)
    assert any(issue["code"] == "duplicate-required-check" for issue in report["issues"])


def test_silent_optional_skip_is_not_accepted(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "broken.yml", {"smoke": _job(name="Cross-system smoke", run="echo skipping optional MNE", artifact=True)})
    report = audit_workflows(tmp_path)
    assert any(issue["code"] == "silent-optional-skip" for issue in report["issues"])


def test_manual_heavy_profile_is_not_classified_as_automatic_cpu_install(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "optional.yml", {"optional-ml": _job(name="Optional ML", run="pip install -r requirements-ml.txt\npytest tests", artifact=True)}, manual=True)
    report = audit_workflows(tmp_path)
    assert not any(issue["code"] == "heavy-dependency-in-cpu-job" for issue in report["issues"])


def test_diagnostic_is_finite_and_contains_release_fields() -> None:
    diagnostic = make_diagnostic(
        workflow="CI",
        job="core-tests",
        step="pytest",
        exit_code=124,
        timeout_state="timed_out",
        message="pytest timed out",
        artifact_path="outputs/ci_diagnostics/core.json",
    )
    encoded = json.dumps(diagnostic, allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == "release-ci-diagnostic-v1"
    assert decoded["workflow"] == "CI"
    assert decoded["job"] == "core-tests"
    assert decoded["step"] == "pytest"
    assert decoded["exit_code"] == 124
    assert decoded["timeout_state"] == "timed_out"
    assert decoded["artifact_path"].endswith("core.json")
    assert decoded["actionable"] is True


def test_origin_main_workflow_set_satisfies_release_contract() -> None:
    report = audit_workflows(ROOT)
    assert report["status"] == "PASS", report["issues"]
    assert report["issues"] == []


def test_automatic_workflows_do_not_download_datasets_or_call_cloud_tools() -> None:
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        events = workflow.get("on", workflow.get(True, {}))
        if not isinstance(events, dict) or not ({"pull_request", "push"} & set(events)):
            continue
        text = path.read_text(encoding="utf-8").lower()
        assert "aws s3" not in text
        assert "openneuro" not in text
        assert "curl -f" not in text
        assert "wget " not in text
