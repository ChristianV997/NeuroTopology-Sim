from __future__ import annotations

import json
from types import SimpleNamespace

from tools.ci_resource_audit.audit import (
    build_environment_report,
    classify_resource_state,
    collect_environment,
    serialize_report,
)
from tools.ci_resource_audit.log_parser import parse_ci_log


def _fake_usage(path):
    path_text = str(path)
    if "tmp" in path_text.lower() or "temp" in path_text.lower():
        return SimpleNamespace(total=100, used=99, free=1)
    return SimpleNamespace(total=1000, used=999, free=1)


def test_windows_like_and_posix_paths_are_reported_without_path_fabrication():
    fixture_env = {"PIP_CACHE_DIR": r"C:\missing\pip-cache"}
    windows = collect_environment(repo_path=r"C:\runner\_work\NeuroTopology-Sim", temp_dir=r"C:\Temp", include_packages=False, disk_usage_fn=_fake_usage, env=fixture_env)
    posix = collect_environment(repo_path="/workspace/NeuroTopology-Sim", temp_dir="/tmp", include_packages=False, disk_usage_fn=_fake_usage, env=fixture_env)
    assert windows["disk"]["repository"]["path"] == r"C:\runner\_work\NeuroTopology-Sim"
    assert posix["disk"]["repository"]["path"] == "/workspace/NeuroTopology-Sim"
    assert windows["disk"]["temporary_directory"]["free_bytes"] == 1


def test_low_disk_fixture_is_classified_without_touching_the_filesystem():
    environment = collect_environment(repo_path="/workspace", temp_dir="/tmp", include_packages=False, disk_usage_fn=_fake_usage, env={"PIP_CACHE_DIR": r"C:\missing\pip-cache"})
    state = classify_resource_state(environment, min_free_disk_bytes=10)
    assert state["classification"] == "disk_exhaustion"
    assert state["reasons"]


def test_unavailable_optional_packages_are_null_and_not_fabricated(monkeypatch):
    import tools.ci_resource_audit.audit as audit

    monkeypatch.setattr(audit, "_package_versions", lambda: {})
    monkeypatch.setattr(audit.importlib.util, "find_spec", lambda name: None)
    report = collect_environment(include_packages=True, env={"PIP_CACHE_DIR": r"C:\missing\pip-cache"})
    optional = report["optional_dependencies"]
    assert optional["torch"] == {"available": False, "version": None, "importable": False}
    assert report["cuda_nvidia"]["installed_packages"] == {}


def test_explicit_billing_block_is_distinct_and_never_marks_tests_passed():
    result = parse_ci_log("This workflow was not run because the repository billing account exceeded its spending limit.\n")
    assert result["classification"] == "billing_or_runner_blocked"
    assert result["billing_evidence"] is True
    assert result["job_never_started"] is True
    assert result["tests_passed"] is False
    assert result["pass_status"] == "not_evaluated"


def test_generic_timeout_is_not_billing_evidence():
    result = parse_ci_log("The runner timed out while waiting for a response.\n")
    assert result["classification"] == "unknown_infrastructure_failure"
    assert result["billing_evidence"] is False
    assert result["generic_timeout_only"] is True


def test_actual_test_failure_is_not_infrastructure_billing():
    result = parse_ci_log("test session starts\nFAILED tests/test_math.py::test_sum - AssertionError\n1 failed in 0.2s\n")
    assert result["classification"] == "test_failure"
    assert result["job_started"] is True
    assert result["tests_executed"] is True
    assert result["tests_passed"] is False
    assert result["billing_evidence"] is False


def test_import_dependency_and_network_signatures_are_distinct():
    assert parse_ci_log("ModuleNotFoundError: No module named 'mne'")["classification"] == "import_failure"
    assert parse_ci_log("ERROR: Could not find a version that satisfies the requirement made-up-package")["classification"] == "dependency_resolution_failure"
    assert parse_ci_log("Temporary failure in name resolution")["classification"] == "network_resolution_failure"


def test_invalid_and_empty_log_input_is_safe():
    invalid = parse_ci_log(None)
    empty = parse_ci_log("")
    assert invalid["input_valid"] is False
    assert invalid["classification"] == "unknown_infrastructure_failure"
    assert empty["input_valid"] is True
    assert empty["classification"] is None
    assert empty["failure_detected"] is False


def test_classification_is_deterministic():
    text = "pytest\nERROR: ResolutionImpossible\nCould not resolve host: pypi.org\n"
    assert parse_ci_log(text) == parse_ci_log(text)


def test_json_is_finite_and_unavailable_metrics_are_null():
    report = build_environment_report(include_packages=False, include_timestamp=False, env={"PIP_CACHE_DIR": r"C:\missing\pip-cache"})
    encoded = serialize_report(report)
    decoded = json.loads(encoded)
    assert "NaN" not in encoded and "Infinity" not in encoded
    assert decoded["environment"]["schema"] == "NeuroTopology.CIResourceAudit.v1"
    assert decoded["environment"]["generated_at_utc"] is None


def test_log_reports_are_json_safe_and_deterministic():
    first = {"schema": "NeuroTopology.CIResourceAudit.v1", "mode": "log", "failure_classes": [], "log": parse_ci_log("billing spending limit")}
    second = {"schema": "NeuroTopology.CIResourceAudit.v1", "mode": "log", "failure_classes": [], "log": parse_ci_log("billing spending limit")}
    assert serialize_report(first) == serialize_report(second)
    json.loads(serialize_report(first))
