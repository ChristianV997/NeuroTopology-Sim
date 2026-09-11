"""Acceptance test suite for research execution platform acceptance harness.

Verifies:
- Complete harness execution, schema conformance, and tamper-evident checksums;
- Bounded data access, metadata registration, and unregistered access rejection;
- Cache bounds, atomic partial cleanup, checksum mismatch, retry classification, and eviction;
- Process timeout and descendant cleanup;
- Output containment and path traversal rejection;
- Finite JSON serialization (no NaN/Inf);
- PowerShell command quoting, construction, and execution;
- Non-Windows unsupported classification (Windows cases are NEVER marked PASS on POSIX);
- Windows-specific tests (process-tree termination, path normalization, file locks, atomic replacement, symlinks);
- Strict offline execution;
- CLI runner subprocess execution.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.platform_acceptance.research_execution.harness import (
    ResearchExecutionAcceptanceHarness,
)
from tools.platform_acceptance.research_execution.probes import (
    build_powershell_command,
    detect_platform_capability,
    ps_single_quote,
)
from tools.platform_acceptance.research_execution.types import (
    AcceptanceCategory,
    AcceptanceReport,
    PlatformCapability,
    TestStatus,
    compute_report_checksum,
    json_safe,
    write_atomic_json,
)

_IS_WINDOWS = os.name == "nt"


def test_harness_execution_and_report_schema(tmp_path: Path):
    """Full execution of the acceptance harness produces a compliant, verified report."""
    harness = ResearchExecutionAcceptanceHarness(timeout_s=5.0)
    report = harness.run_all(target_dir=tmp_path)

    assert report.schema_version == "research_execution_platform_acceptance_v1"
    assert report.total_tests >= 15
    assert report.failed == 0, f"Acceptance test failures detected: {[r for r in report.results if r.status == TestStatus.FAIL]}"
    assert report.all_passed is True

    # Validate report checksum
    report_dict = report.to_dict()
    recalculated = compute_report_checksum(report_dict)
    assert report.checksum == recalculated

    # Validate platform matrix structure
    matrix = report.platform_matrix
    assert matrix.os_name == os.name
    assert matrix.is_windows == _IS_WINDOWS
    assert isinstance(matrix.supported_categories, list)
    assert isinstance(matrix.unsupported_categories, list)


def test_non_windows_unsupported_classification(tmp_path: Path):
    """On non-Windows hosts, Windows-specific test cases must be classified as UNSUPPORTED, never PASS."""
    fake_posix_capability = PlatformCapability(
        os_name="posix",
        platform_release="Linux-6.5.0-generic-x86_64",
        is_windows=False,
        powershell_available=False,
        powershell_binary=None,
        powershell_version=None,
        symlink_supported=True,
        file_locking_supported=True,
    )

    harness = ResearchExecutionAcceptanceHarness(capability=fake_posix_capability, timeout_s=2.0)
    report = harness.run_all(target_dir=tmp_path)

    win_results = [r for r in report.results if r.windows_specific]
    assert len(win_results) >= 5, "Expected at least 5 Windows-specific cases"

    for r in win_results:
        assert r.status == TestStatus.UNSUPPORTED, f"Case {r.name} had status {r.status} instead of UNSUPPORTED"
        assert r.status != TestStatus.PASS, f"CRITICAL: Windows-specific case {r.name} was marked PASS on POSIX!"


def test_powershell_wrapper_quoting_and_escaping():
    """PowerShell single-quote escaping and command formatting contracts."""
    assert ps_single_quote("plain") == "'plain'"
    assert ps_single_quote("o'brien") == "'o''brien'"
    assert ps_single_quote("C:\\My Documents\\test.py") == "'C:\\My Documents\\test.py'"
    assert ps_single_quote("quote 'inside' text") == "'quote ''inside'' text'"

    argv = [sys.executable, "-c", "print('hello world')", "--flag", "value with spaces"]
    cmd = build_powershell_command(argv, binary="powershell")

    assert cmd[0] == "powershell"
    assert "-NoProfile" in cmd
    assert "-NonInteractive" in cmd
    assert "-ExecutionPolicy" in cmd
    assert "Bypass" in cmd
    assert "-Command" in cmd
    assert cmd[-1].startswith("& ")
    assert ps_single_quote(sys.executable) in cmd[-1]

    with pytest.raises(ValueError):
        build_powershell_command([])


def test_bounded_metadata_and_unregistered_object_rejection(tmp_path: Path):
    """Cache strictly rejects access to unregistered objects, preserving manifest-first rules."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_local_metadata_registration(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.DATA_ACCESS


def test_cache_bounds_and_budget_enforcement(tmp_path: Path):
    """Cache strictly rejects objects exceeding total allocated cache capacity."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_bounded_cache_budget_enforcement(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.DATA_ACCESS


def test_atomic_partial_and_checksum_mismatch(tmp_path: Path):
    """Checksum mismatch must abort transfer and unlink intermediate .part files."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_atomic_partial_and_checksum_mismatch(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.CACHE_EVICTION


def test_retry_classification(tmp_path: Path):
    """Transient network errors must be retried with recovery."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_retry_classification(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.CACHE_EVICTION


def test_lru_eviction_and_lease_protection(tmp_path: Path):
    """LRU eviction removes unleased items under pressure while active leases remain protected."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_lru_eviction_and_lease_protection(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.CACHE_EVICTION


def test_process_timeout_and_cleanup(tmp_path: Path):
    """Subprocess exceeding timeout is terminated along with process group."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_process_timeout_and_cleanup(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.PROCESS_EXECUTION


def test_output_containment_and_traversal_rejection(tmp_path: Path):
    """Path traversal attempts are rejected across all path formats."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_output_containment_and_traversal_rejection(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.OUTPUT_CONTAINMENT


def test_finite_json_and_malformed_artifact_rejection(tmp_path: Path):
    """Serialization guarantees finite JSON without NaN or Inf."""
    harness = ResearchExecutionAcceptanceHarness()
    res = harness._case_finite_json_and_malformed_artifact_rejection(tmp_path)
    assert res.status == TestStatus.PASS
    assert res.category == AcceptanceCategory.ARTIFACT_INTEGRITY


@pytest.mark.skipif(not _IS_WINDOWS, reason="Windows-specific behavior")
def test_windows_specifics_on_windows(tmp_path: Path):
    """On Windows hosts, Windows-specific cases pass and exercise native OS primitives."""
    harness = ResearchExecutionAcceptanceHarness()

    res_tree = harness._case_windows_process_tree_termination(tmp_path)
    assert res_tree.status == TestStatus.PASS

    res_path = harness._case_windows_path_separators_normalization(tmp_path)
    assert res_path.status == TestStatus.PASS

    res_lock = harness._case_windows_file_locking(tmp_path)
    assert res_lock.status == TestStatus.PASS

    res_replace = harness._case_windows_atomic_replacement(tmp_path)
    assert res_replace.status == TestStatus.PASS

    res_sym = harness._case_windows_symlink_privilege_handling(tmp_path)
    assert res_sym.status == TestStatus.PASS


def test_cli_acceptance_runner(tmp_path: Path):
    """CLI script runs acceptance suite, outputs valid JSON, and writes output file."""
    cli_path = Path(__file__).resolve().parents[3] / "scripts" / "run_research_execution_acceptance.py"
    output_file = tmp_path / "acceptance_output.json"

    proc = subprocess.run(
        [sys.executable, str(cli_path), "--output", str(output_file), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"CLI runner failed: {proc.stderr}"
    assert output_file.exists()

    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == "research_execution_platform_acceptance_v1"
    assert data["all_passed"] is True
    assert data["failed"] == 0
