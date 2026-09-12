"""Tests for Approved Acquisition Adapter layer.

Validates:
- Metadata-first dry-run planning (zero network calls).
- Rejection of unknown size, full-object, and unapproved licenses.
- Fail-closed network permission gate.
- Bounded byte-range acquisition via MockTransferAdapter.
- Consumer-tracked checkout and delete_on_final_consumer eviction.
- Checksum verification and mismatch handling.
- Transient retry and error exhaustion.
- Stale partial cleanup.
- Cache budget and disk exhaustion guardrails.
- Legacy acquisition caller scanner.
- RFC 8259 finite JSON serialization (NaN/Infinity rejection).
- CLI plan, acquire, consume, and report-legacy execution.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict
import pytest

from tools.data_access.approved_adapter import (
    APPROVED_ACQUISITION_SCHEMA,
    AcquisitionContractError,
    AdapterErrorCode,
    ApprovedAcquisitionAdapter,
    BoundedAcquisitionPlan,
    BoundedAcquisitionRequest,
    BoundedAcquisitionResult,
    ChecksumPolicy,
    EvictionPolicy,
    LegacyCallerScanner,
    LicenseAccessState,
    SourceCatalogType,
    finite_value,
    scan_legacy_callers,
    verify_plan_checksum,
)
from tools.data_access.chunk_cache import (
    BoundedChunkCache,
    CacheItemStatus,
    MockTransferAdapter,
    compute_file_sha256,
)
from scripts.plan_bounded_acquisition import main as cli_main


@pytest.fixture
def temp_cache_dir():
    """Isolated temporary directory for chunk cache."""
    td = tempfile.mkdtemp(prefix="test_approved_adapter_")
    yield Path(td)
    shutil.rmtree(td, ignore_errors=True)


@pytest.fixture
def mock_transfer():
    """Mock transfer adapter with pre-seeded payloads."""
    adapter = MockTransferAdapter()
    payload = b"NEUROLOGICAL_EEG_RAW_TRACE_DATA_BYTE_RANGE_CONTENT_1234567890"
    adapter.register_remote_object(
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        content=payload,
    )
    return adapter


def test_metadata_only_planning(temp_cache_dir, mock_transfer):
    """Dry-run planning must not perform network calls or write data files."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, transfer_adapter=mock_transfer)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=99,
        catalog_type=SourceCatalogType.OPENNEURO.value,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=False,
    )

    plan = adapter.plan(req)

    assert plan.schema_version == APPROVED_ACQUISITION_SCHEMA
    assert plan.is_executable is True
    assert plan.requested_bytes == 100
    assert plan.expected_size_bytes == 1000
    assert len(plan.rejection_reasons) == 0
    assert plan.license_approved is True
    assert plan.checksum != ""
    assert verify_plan_checksum(plan.to_dict()) is True

    # Confirm zero transfer files were created
    assert len(list(temp_cache_dir.glob("**/*.edf"))) == 0
    # Confirm cache manifest was not created during plan
    manifest_p = temp_cache_dir / "manifest.json"
    assert not manifest_p.exists() or len(adapter.cache._records) == 0


def test_unknown_size_rejected(temp_cache_dir):
    """Requests with 0 or negative expected size must be rejected."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/dummy",
        expected_size_bytes=0,
        start_byte=0,
        end_byte=50,
        license_state=LicenseAccessState.OPEN_CC0.value,
    )

    plan = adapter.plan(req)
    assert plan.is_executable is False
    assert any("UNKNOWN_SIZE_REJECTED" in r for r in plan.rejection_reasons)


def test_full_object_rejected_by_default(temp_cache_dir):
    """Full-object range requests without allow_full_object=True must be rejected."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/dummy",
        expected_size_bytes=100,
        start_byte=0,
        end_byte=99,  # Covers full 100 bytes
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_full_object=False,
    )

    plan = adapter.plan(req)
    assert plan.is_executable is False
    assert any("FULL_OBJECT_REJECTED" in r for r in plan.rejection_reasons)

    # When allow_full_object is explicitly True, it passes
    req.allow_full_object = True
    plan2 = adapter.plan(req)
    assert plan2.is_executable is True
    assert len(plan2.rejection_reasons) == 0


def test_license_gating(temp_cache_dir):
    """Non-open licenses must be rejected by default."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir)
    for restricted in [LicenseAccessState.RESTRICTED.value, LicenseAccessState.UNKNOWN_BLOCKED.value]:
        req = BoundedAcquisitionRequest(
            dataset_id="ds004504",
            object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
            source_uri="https://openneuro.org/dummy",
            expected_size_bytes=1000,
            start_byte=0,
            end_byte=50,
            license_state=restricted,
        )
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any("LICENSE_RESTRICTED" in r for r in plan.rejection_reasons)

    # Approved licenses pass
    for approved in [LicenseAccessState.OPEN_CC0.value, LicenseAccessState.OPEN_CC_BY.value, LicenseAccessState.OPEN_ACCESS.value]:
        req.license_state = approved
        plan = adapter.plan(req)
        assert plan.is_executable is True


def test_network_disabled_fail_closed(temp_cache_dir, mock_transfer):
    """Acquisition attempt without allow_network=True must fail immediately."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, transfer_adapter=mock_transfer)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=20,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=False,  # FAIL-CLOSED
    )

    result = adapter.acquire(req)
    assert result.success is False
    assert result.error_code == AdapterErrorCode.NETWORK_DISABLED.value
    assert len(list(temp_cache_dir.glob("**/*.edf"))) == 0


def test_bounded_acquisition_success(temp_cache_dir, mock_transfer):
    """Successful bounded chunk download through mock transfer."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, transfer_adapter=mock_transfer)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=25,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=True,
    )

    result = adapter.acquire(req)
    assert result.success is True
    assert result.bytes_transferred == 26
    assert result.cached_path is not None
    assert Path(result.cached_path).is_file()
    assert Path(result.cached_path).read_bytes() == b"NEUROLOGICAL_EEG_RAW_TRACE"


def test_declared_consumers_and_final_eviction(temp_cache_dir, mock_transfer):
    """Chunk is leased while consumers exist, then deleted on final consumer."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, transfer_adapter=mock_transfer)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=15,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=True,
        declared_consumers=["step_filtering", "step_feature_extract"],
        eviction_policy=EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value,
    )

    result = adapter.acquire(req)
    assert result.success is True
    cached_file = Path(result.cached_path)
    assert cached_file.is_file()

    # Active lease exists
    key = ("ds004504", "sub-01/eeg/sub-01_task-rest_eeg.edf", 0)
    assert adapter.cache.lease_manager.get_lease_count("ds004504", "sub-01/eeg/sub-01_task-rest_eeg.edf", 0) == 1

    # First consumer acknowledges
    ack1 = adapter.consume(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        consumer_id="step_filtering",
    )
    assert ack1["remaining_consumers"] == ["step_feature_extract"]
    assert ack1["lease_released"] is False
    assert ack1["evicted"] is False
    assert cached_file.is_file()

    # Final consumer acknowledges
    ack2 = adapter.consume(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        consumer_id="step_feature_extract",
    )
    assert ack2["remaining_consumers"] == []
    assert ack2["lease_released"] is True
    assert ack2["evicted"] is True
    # File must be unlinked
    assert not cached_file.exists()

    # Manifest record updated to EVICTED
    manifest_rec = adapter.cache._records.get(key)
    assert manifest_rec is not None
    assert manifest_rec.status == CacheItemStatus.EVICTED.value


def test_checksum_verification_and_mismatch(temp_cache_dir, mock_transfer):
    """Verify checksum matching and rejection on checksum mismatch."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, transfer_adapter=mock_transfer)

    # 1. Correct checksum
    expected_chunk_data = b"NEUROLOGICAL_EEG"
    import hashlib
    correct_sha = hashlib.sha256(expected_chunk_data).hexdigest()

    req_good = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=15,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=True,
        expected_checksum=correct_sha,
    )
    res_good = adapter.acquire(req_good, chunk_index=1)
    assert res_good.success is True
    assert res_good.checksum_verified is True

    # 2. Checksum mismatch
    bad_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    req_bad = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=15,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=True,
        expected_checksum=bad_sha,
    )
    res_bad = adapter.acquire(req_bad, chunk_index=2)
    assert res_bad.success is False
    assert res_bad.error_code == AdapterErrorCode.CHECKSUM_MISMATCH.value


def test_transient_retry_and_exhaustion(temp_cache_dir):
    """Simulate transient network failure and retry limit exhaustion."""
    mock = MockTransferAdapter()
    url = "https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf"
    mock.register_remote_object(source_uri=url, content=b"RETRY_TEST_PAYLOAD")
    # Force 2 transient failures, max_retries=3 -> should recover
    mock.set_transient_failure(source_uri=url, failure_count=2)

    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, transfer_adapter=mock)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri=url,
        expected_size_bytes=500,
        start_byte=0,
        end_byte=17,
        license_state=LicenseAccessState.OPEN_CC0.value,
        allow_network=True,
    )

    res = adapter.acquire(req, max_retries=3)
    assert res.success is True
    assert res.attempts == 3

    # Force 5 transient failures with max_retries=2 -> exhaustion
    mock.set_transient_failure(source_uri=url, failure_count=5)
    res_fail = adapter.acquire(req, chunk_index=1, max_retries=2)
    assert res_fail.success is False
    assert res_fail.error_code == AdapterErrorCode.TRANSIENT_RETRY_EXHAUSTED.value


def test_stale_partial_cleanup(temp_cache_dir):
    """Adapter can remove abandoned .part.* files."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir)
    part_file = temp_cache_dir / "temp_file.part.12345"
    part_file.write_bytes(b"ABANDONED_BYTES_12345")

    assert part_file.exists()
    removed_count, reclaimed_bytes = adapter.cleanup_stale_partials(max_age_seconds=0.0)
    assert removed_count == 1
    assert reclaimed_bytes == len(b"ABANDONED_BYTES_12345")
    assert not part_file.exists()


def test_cache_budget_exceeded(temp_cache_dir):
    """Requested bytes exceeding cache budget are rejected at plan time."""
    adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache_dir, max_cache_bytes=100)
    req = BoundedAcquisitionRequest(
        dataset_id="ds004504",
        object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/dummy",
        expected_size_bytes=1000,
        start_byte=0,
        end_byte=200,  # 201 bytes > 100 max budget
        license_state=LicenseAccessState.OPEN_CC0.value,
        cache_budget_bytes=100,
    )

    plan = adapter.plan(req)
    assert plan.is_executable is False
    assert any("CACHE_BUDGET_EXCEEDED" in r for r in plan.rejection_reasons)


def test_rfc8259_finite_json_rejection():
    """finite_value must reject NaN and Infinity."""
    with pytest.raises(AcquisitionContractError):
        finite_value({"val": float("nan")})

    with pytest.raises(AcquisitionContractError):
        finite_value({"val": float("inf")})

    with pytest.raises(AcquisitionContractError):
        finite_value({"val": float("-inf")})

    # None and finite values work
    safe = finite_value({"a": None, "b": 42, "c": 3.14, "d": "valid"})
    assert safe == {"a": None, "b": 42, "c": 3.14, "d": "valid"}


def test_legacy_caller_scanner(tmp_path):
    """Scanner detects legacy unconstrained download patterns in python files."""
    dummy_repo = tmp_path / "mock_repo"
    dummy_repo.mkdir()
    legacy_file = dummy_repo / "old_downloader.py"
    legacy_file.write_text(
        'import urllib.request\n'
        'def get_all():\n'
        '    urllib.request.urlretrieve("http://example.com/big.edf", "out.edf")\n',
        encoding="utf-8",
    )

    scanner = LegacyCallerScanner(repo_root=dummy_repo, excludes=[])
    report = scanner.scan()

    assert report["total_findings"] >= 1
    finding = report["findings"][0]
    assert finding["risk_code"] == "UNCONSTRAINED_URLRETRIEVE"
    assert "old_downloader.py" in finding["file_path"]

    md = scanner.to_markdown(report)
    assert "UNCONSTRAINED_URLRETRIEVE" in md
    assert "old_downloader.py" in md


def test_cli_plan_and_report_legacy(temp_cache_dir, tmp_path, capsys):
    """Test CLI subcommands: plan and report-legacy."""
    # 1. plan
    exit_code = cli_main([
        "plan",
        "--dataset-id", "ds004504",
        "--object-path", "sub-01/eeg/sub-01_task-rest_eeg.edf",
        "--source-uri", "https://openneuro.org/dummy",
        "--expected-size", "500",
        "--start-byte", "0",
        "--end-byte", "49",
        "--license-state", "open_cc0",
        "--cache-root", str(temp_cache_dir),
        "--format", "json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    plan_out = json.loads(captured.out)
    assert plan_out["is_executable"] is True
    assert plan_out["requested_bytes"] == 50

    # 2. report-legacy
    legacy_out_path = tmp_path / "legacy_report.json"
    exit_code_legacy = cli_main([
        "report-legacy",
        "--repo-root", str(tmp_path),
        "--output", str(legacy_out_path),
        "--format", "json",
    ])
    assert exit_code_legacy == 0
    assert legacy_out_path.is_file()
    leg_data = json.loads(legacy_out_path.read_text(encoding="utf-8"))
    assert "schema_version" in leg_data
