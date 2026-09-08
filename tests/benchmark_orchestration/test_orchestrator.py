"""Tests for deterministic benchmark orchestration.

Engineering triage scaffolding only — never scientific evidence.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import pytest

from tools.benchmark_orchestration.executor import classify_exit, run_case_with_retries
from tools.benchmark_orchestration.json_util import dumps
from tools.benchmark_orchestration.matrix import MatrixValidationError, load_matrix, validate_matrix
from tools.benchmark_orchestration.orchestrator import run_campaign, write_manifest
from tools.benchmark_orchestration.report import dumps_json, render_markdown, write_reports
from tools.benchmark_orchestration.schema import (
    MATRIX_SCHEMA_VERSION,
    CampaignConfig,
    CaseSpec,
    CaseStatus,
    MatrixSpec,
)


def _matrix(cases, **kwargs):
    return {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "provenance_label": kwargs.get("provenance_label", "test-matrix"),
        "defaults": kwargs.get("defaults", {"timeout_s": 30, "max_retries": 0}),
        "cases": cases,
    }


def test_valid_matrix(tmp_path):
    path = tmp_path / "ok.json"
    path.write_text(
        json.dumps(
            _matrix(
                [
                    {"id": "b-case", "command": ["python", "-c", "print(1)"]},
                    {"id": "a-case", "command": ["python", "-c", "print(2)"]},
                ]
            )
        ),
        encoding="utf-8",
    )
    spec = load_matrix(path)
    assert len(spec.cases) == 2
    assert [c.case_id for c in spec.cases] == ["a-case", "b-case"]  # deterministic order


def test_malformed_matrix():
    with pytest.raises(MatrixValidationError):
        validate_matrix({"schema_version": "1.0", "cases": []})
    with pytest.raises(MatrixValidationError):
        validate_matrix({"schema_version": "9.9", "cases": [{"id": "x", "command": ["true"]}]})
    with pytest.raises(MatrixValidationError):
        validate_matrix({"schema_version": "1.0", "cases": "nope"})


def test_duplicate_case_ids():
    with pytest.raises(MatrixValidationError, match="duplicate"):
        validate_matrix(
            _matrix(
                [
                    {"id": "same", "command": ["python", "-c", "print(1)"]},
                    {"id": "same", "command": ["python", "-c", "print(2)"]},
                ]
            )
        )


def test_deterministic_ordering():
    raw = _matrix(
        [
            {"id": "zeta", "command": ["python", "-c", "print(1)"]},
            {"id": "alpha", "command": ["python", "-c", "print(1)"]},
            {"id": "mu", "command": ["python", "-c", "print(1)"]},
        ]
    )
    a = validate_matrix(raw)
    b = validate_matrix(raw)
    assert [c.case_id for c in a.cases] == ["alpha", "mu", "zeta"]
    assert [c.case_id for c in a.cases] == [c.case_id for c in b.cases]


def test_timeout(tmp_path):
    spec = CaseSpec(
        case_id="sleep-case",
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_s=1,
        max_retries=0,
    )
    result = run_case_with_retries(spec, timeout_s=1, max_retries=0, work_dir=tmp_path / "logs")
    assert result.status == CaseStatus.TIMEOUT
    assert result.timed_out is True
    assert result.exit_code == 124
    # Never convert timeout to pass.
    assert result.status != CaseStatus.PASS


def test_child_crash(tmp_path):
    # Raise SIGABRT-like via os.abort on POSIX for CHILD_CRASH classification,
    # or exit 139-style. Using a negative-return simulation: kill self with SIGKILL
    # is hard to do cleanly; exit with code 139 instead and classify via helper,
    # plus a real abort subprocess when available.
    assert classify_exit(139, False) == CaseStatus.CHILD_CRASH
    assert classify_exit(-9, False) == CaseStatus.CHILD_CRASH
    crash_code = "import sys; sys.exit(139)" if os.name == "nt" else "import os; os.abort()"
    spec = CaseSpec(
        case_id="abort-case",
        command=[sys.executable, "-c", crash_code],
        timeout_s=10,
    )
    result = run_case_with_retries(spec, timeout_s=10, max_retries=0, work_dir=tmp_path / "logs")
    assert result.status in {CaseStatus.CHILD_CRASH, CaseStatus.CORRECTNESS_FAILURE}
    assert result.status != CaseStatus.PASS


def test_retry_limit(tmp_path):
    # Always crash → retries exhausted, never infinite.
    crash_code = "import sys; sys.exit(139)" if os.name == "nt" else "import os; os.abort()"
    spec = CaseSpec(
        case_id="retry-crash",
        command=[sys.executable, "-c", crash_code],
        timeout_s=10,
        max_retries=2,
    )
    result = run_case_with_retries(spec, timeout_s=10, max_retries=2, work_dir=tmp_path / "logs")
    assert result.attempts == 3  # initial + 2 retries
    assert result.retries_used == 2
    assert result.status != CaseStatus.PASS
    # Correctness failures are not retried:
    fail = CaseSpec(
        case_id="retry-fail",
        command=[sys.executable, "-c", "raise SystemExit(1)"],
        timeout_s=10,
        max_retries=5,
    )
    result2 = run_case_with_retries(fail, timeout_s=10, max_retries=5, work_dir=tmp_path / "logs")
    assert result2.status == CaseStatus.CORRECTNESS_FAILURE
    assert result2.attempts == 1


def test_resume(tmp_path):
    matrix = validate_matrix(
        _matrix(
            [
                {"id": "one", "command": [sys.executable, "-c", "print('one')"]},
                {"id": "two", "command": [sys.executable, "-c", "print('two')"]},
            ]
        )
    )
    out = tmp_path / "camp1"
    # First run both.
    r1 = run_campaign(matrix, CampaignConfig(max_workers=1), output_dir=out)
    assert all(r.status == CaseStatus.PASS for r in r1.results)
    # Corrupt second case in manifest to force re-run only of a new third? Instead:
    # Build a larger matrix and resume after partial.
    matrix2 = validate_matrix(
        _matrix(
            [
                {"id": "one", "command": [sys.executable, "-c", "print('one')"]},
                {"id": "two", "command": [sys.executable, "-c", "print('two')"]},
                {"id": "three", "command": [sys.executable, "-c", "print('three')"]},
            ]
        )
    )
    # Keep prior manifest (one, two PASS) and resume.
    r2 = run_campaign(
        matrix2,
        CampaignConfig(max_workers=1, resume=True),
        output_dir=out,
    )
    by_id = {r.case_id: r for r in r2.results}
    assert by_id["one"].status == CaseStatus.PASS
    assert by_id["two"].status == CaseStatus.PASS
    assert by_id["three"].status == CaseStatus.PASS
    assert by_id["three"].attempts >= 1
    assert r2.resumed_from is not None


def test_worker_cap(tmp_path):
    # Three short cases with max_workers=2 should all PASS; config records the cap.
    cases = [
        {"id": f"w{i}", "command": [sys.executable, "-c", "print(1)"]}
        for i in range(3)
    ]
    matrix = validate_matrix(_matrix(cases))
    report = run_campaign(
        matrix,
        CampaignConfig(max_workers=2),
        output_dir=tmp_path / "workers",
    )
    assert report.campaign["max_workers"] == 2
    assert all(r.status == CaseStatus.PASS for r in report.results)


def test_total_timeout(tmp_path):
    cases = [
        {
            "id": "long-a",
            "command": [sys.executable, "-c", "import time; time.sleep(5)"],
            "timeout_s": 10,
        },
        {
            "id": "long-b",
            "command": [sys.executable, "-c", "import time; time.sleep(5)"],
            "timeout_s": 10,
        },
        {
            "id": "long-c",
            "command": [sys.executable, "-c", "import time; time.sleep(5)"],
            "timeout_s": 10,
        },
    ]
    matrix = validate_matrix(_matrix(cases))
    t0 = time.monotonic()
    report = run_campaign(
        matrix,
        CampaignConfig(max_workers=1, total_timeout_s=2, per_case_timeout_s=10),
        output_dir=tmp_path / "total",
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 8  # should not run all three full sleeps
    statuses = [r.status for r in report.results]
    assert CaseStatus.NOT_RUN in statuses or CaseStatus.TIMEOUT in statuses
    assert CaseStatus.PASS not in statuses or statuses.count(CaseStatus.PASS) < 3
    # Critically: no timeout remapped to PASS via total budget.
    for r in report.results:
        if r.timed_out:
            assert r.status == CaseStatus.TIMEOUT


def test_missing_optional_dependency(tmp_path):
    spec = CaseSpec(
        case_id="need-fake",
        command=[sys.executable, "-c", "print('hi')"],
        timeout_s=5,
        optional_deps=["definitely_not_a_real_module_xyz"],
    )
    result = run_case_with_retries(spec, timeout_s=5, max_retries=0, work_dir=tmp_path / "logs")
    assert result.status == CaseStatus.OPTIONAL_DEPENDENCY_MISSING
    assert result.exit_code is None


def test_finite_json(tmp_path):
    matrix = validate_matrix(
        _matrix([{"id": "j", "command": [sys.executable, "-c", "print(1)"]}])
    )
    report = run_campaign(matrix, CampaignConfig(dry_run=True), output_dir=tmp_path / "json")
    text = dumps_json(report)
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    json.dumps(data, allow_nan=False)
    md = render_markdown(report)
    assert "Benchmark Orchestration Report" in md
    paths = write_reports(report, tmp_path / "json")
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()


def test_no_network_dry_run(tmp_path):
    # Network-looking command rejected under local_only validation.
    with pytest.raises(MatrixValidationError, match="non-local"):
        validate_matrix(
            _matrix(
                [
                    {
                        "id": "net",
                        "command": ["curl", "https://example.com"],
                        "timeout_s": 5,
                    }
                ]
            ),
            local_only=True,
        )
    # Dry-run of a local matrix never executes children (NOT_RUN).
    matrix = validate_matrix(
        _matrix(
            [
                {"id": "a", "command": [sys.executable, "-c", "raise SystemExit('should not run')"]},
                {"id": "b", "command": [sys.executable, "-c", "raise SystemExit('should not run')"]},
            ]
        )
    )
    report = run_campaign(
        matrix,
        CampaignConfig(dry_run=True, local_only=True),
        output_dir=tmp_path / "dry",
    )
    assert report.dry_run is True
    assert all(r.status == CaseStatus.NOT_RUN for r in report.results)
    assert all(r.dry_run for r in report.results)


def test_classify_exit_helpers():
    assert classify_exit(0, False) == CaseStatus.PASS
    assert classify_exit(1, False) == CaseStatus.CORRECTNESS_FAILURE
    assert classify_exit(124, True) == CaseStatus.TIMEOUT
    assert classify_exit(None, False) == CaseStatus.CHILD_CRASH
