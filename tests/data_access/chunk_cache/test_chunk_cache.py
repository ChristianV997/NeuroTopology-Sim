"""Comprehensive test suite for OpenNeuro/BIDS bounded chunk cache.

Tests cover:
1. Dry-run plan with zero network access.
2. Fail-closed network policy (allow_network=False).
3. Manifest-first registration requirement.
4. Bounded cache budget enforcement and LRU eviction.
5. Active lease protection against eviction.
6. Lease release and lease TTL auto-expiration.
7. Eviction security containment check.
8. Stale .part.* partial download cleanup.
9. Checksum mismatch detection and atomic partial wipe.
10. Pre-flight disk exhaustion check.
11. Transient error retry with exponential backoff.
12. Retry exhaustion on persistent network resets.
13. BIDS path validation and structural constraints.
14. Strict path traversal prevention (../ escaping).
15. Windows backslash normalization.
16. Deterministic tamper-evident reports with SHA-256 integrity.
17. Non-finite float rejection in reports.
18. CLI execution (plan, register, fetch, inspect, evict, cleanup).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.data_access.chunk_cache import (
    BIDSValidationError,
    BoundedChunkCache,
    BoundedEvictionManager,
    CacheErrorCode,
    CacheItemStatus,
    CacheReport,
    ChunkRange,
    EvictionSecurityError,
    LeaseManager,
    MockTransferAdapter,
    compute_file_sha256,
    normalize_bids_relative_path,
    validate_bids_path,
    verify_cache_report_checksum,
)


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Provide clean temporary directory for cache root."""
    cache_dir = tmp_path / "cache_root"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def mock_adapter() -> MockTransferAdapter:
    """Provide MockTransferAdapter populated with test fixtures."""
    adapter = MockTransferAdapter()
    # Register mock remote BIDS files
    adapter.register_remote_object(
        "https://openneuro.org/ds005620/sub-01/eeg/sub-01_task-rest_eeg.edf",
        b"HEADER" + b"DATA_CHUNK_12345" * 100,  # ~1.6 KB
    )
    adapter.register_remote_object(
        "https://openneuro.org/ds005620/sub-02/eeg/sub-02_task-rest_eeg.edf",
        b"HEADER" + b"DATA_CHUNK_67890" * 200,  # ~3.2 KB
    )
    adapter.register_remote_object(
        "https://openneuro.org/ds005620/participants.tsv",
        b"participant_id\tage\tsex\nsub-01\t25\tF\nsub-02\t30\tM\n",
    )
    return adapter


# -----------------------------------------------------------------------------
# 1. BIDS Path Validation & Traversal Security
# -----------------------------------------------------------------------------

def test_bids_validation_valid_paths() -> None:
    """Test valid BIDS paths parse correctly into components."""
    comp = validate_bids_path("ds005620", "sub-01/eeg/sub-01_task-rest_run-01_eeg.edf")
    assert comp.dataset_id == "ds005620"
    assert comp.subject == "sub-01"
    assert comp.session is None
    assert comp.datatype == "eeg"
    assert comp.task == "rest"
    assert comp.run == "01"
    assert comp.suffix == "eeg"
    assert comp.extension == ".edf"

    # With session
    comp_ses = validate_bids_path("ds005620", "sub-02/ses-pre/meg/sub-02_ses-pre_task-memory_meg.fif")
    assert comp_ses.session == "ses-pre"
    assert comp_ses.datatype == "meg"
    assert comp_ses.task == "memory"

    # Top-level dataset file
    comp_top = validate_bids_path("ds005620", "participants.tsv")
    assert comp_top.subject == ""
    assert comp_top.suffix == "participants"
    assert comp_top.extension == ".tsv"


def test_bids_validation_path_traversal_rejection() -> None:
    """Ensure directory traversal and absolute paths are strictly rejected."""
    with pytest.raises(BIDSValidationError, match="Directory traversal"):
        validate_bids_path("ds005620", "../../../etc/passwd")

    with pytest.raises(BIDSValidationError, match="Directory traversal"):
        validate_bids_path("ds005620", "sub-01/../../secret.txt")

    with pytest.raises(BIDSValidationError, match="Absolute paths are forbidden"):
        validate_bids_path("ds005620", "/etc/shadow")

    with pytest.raises(BIDSValidationError, match="Absolute paths are forbidden"):
        validate_bids_path("ds005620", "C:/Windows/System32/cmd.exe")


def test_windows_backslash_normalization() -> None:
    """Ensure Windows backslashes are normalized to POSIX relative paths."""
    norm = normalize_bids_relative_path("sub-01\\eeg\\sub-01_task-rest_eeg.edf")
    assert norm == "sub-01/eeg/sub-01_task-rest_eeg.edf"

    comp = validate_bids_path("ds005620", "sub-01\\eeg\\sub-01_task-rest_eeg.edf")
    assert comp.relative_path == "sub-01/eeg/sub-01_task-rest_eeg.edf"


# -----------------------------------------------------------------------------
# 2. Dry-Run Planning (Zero Network Calls)
# -----------------------------------------------------------------------------

def test_dry_run_plan_zero_network(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Dry-run planning must inspect disk and budget without making any network calls."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        max_cache_bytes=100_000,
        transfer_adapter=mock_adapter,
    )

    # Register items
    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/ds005620/sub-01/eeg/sub-01_task-rest_eeg.edf",
        size_bytes=1600,
    )
    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri="https://openneuro.org/ds005620/participants.tsv",
        size_bytes=52,
    )

    # Plan with requested items
    plan = cache.plan("ds005620")
    assert plan.is_executable is True
    assert plan.total_download_bytes == 1652
    assert len(plan.items_to_download) == 2
    assert len(plan.already_cached_items) == 0
    assert plan.eviction_required_bytes == 0


def test_dry_run_plan_rejection_on_budget_exceeded(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Dry-run plan rejects downloads larger than max cache capacity."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        max_cache_bytes=1000,  # 1 KB max budget
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/ds005620/sub-01/eeg/sub-01_task-rest_eeg.edf",
        size_bytes=5000,
    )

    plan = cache.plan("ds005620")
    assert plan.is_executable is False
    assert plan.rejection_reason is not None
    assert "exceed total cache capacity" in plan.rejection_reason


# -----------------------------------------------------------------------------
# 3. Fail-Closed Network & Manifest-First Fetch
# -----------------------------------------------------------------------------

def test_fetch_fail_closed_network(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Network access must fail closed when allow_network=False."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        max_cache_bytes=50_000,
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri="https://openneuro.org/ds005620/participants.tsv",
        size_bytes=52,
    )

    res = cache.fetch("ds005620", "participants.tsv", allow_network=False)
    assert res.success is False
    assert res.error_code == CacheErrorCode.NETWORK_DISABLED.value
    assert "fail-closed" in res.error_message


def test_fetch_unregistered_object_rejected(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Fetching an object without registering it first in manifest is rejected."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    res = cache.fetch("ds005620", "participants.tsv", allow_network=True)
    assert res.success is False
    assert res.error_code == CacheErrorCode.MISSING_OBJECT.value
    assert "Manifest-first" in res.error_message


def test_fetch_success_and_cache_hit(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Successful fetch caches file; second fetch is a local cache hit with 0 attempts."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri="https://openneuro.org/ds005620/participants.tsv",
        size_bytes=52,
    )

    res1 = cache.fetch("ds005620", "participants.tsv", allow_network=True)
    assert res1.success is True
    assert res1.cached_path is not None
    assert Path(res1.cached_path).exists()
    assert res1.bytes_transferred > 0

    # Second fetch: cache hit
    res2 = cache.fetch("ds005620", "participants.tsv", allow_network=False)
    assert res2.success is True
    assert res2.attempts == 0
    assert res2.cached_path == res1.cached_path


# -----------------------------------------------------------------------------
# 4. Checksum Verification & Tamper Detection
# -----------------------------------------------------------------------------

def test_checksum_mismatch_fails_and_cleans_partial(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Checksum mismatch fails immediately without infinite retry and unlinks partial."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    bad_checksum = "0000000000000000000000000000000000000000000000000000000000000000"
    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri="https://openneuro.org/ds005620/participants.tsv",
        size_bytes=52,
        expected_checksum=bad_checksum,
    )

    res = cache.fetch("ds005620", "participants.tsv", allow_network=True)
    assert res.success is False
    assert res.error_code == CacheErrorCode.CHECKSUM_MISMATCH.value

    # Target path should not exist
    target = temp_cache_dir / "ds005620" / "participants.tsv"
    assert not target.exists()

    # No leftover .part files
    parts = list(temp_cache_dir.glob("**/*.part.*"))
    assert len(parts) == 0


# -----------------------------------------------------------------------------
# 5. Bounded Cache Eviction & Active Lease Protection
# -----------------------------------------------------------------------------

def test_lru_eviction_under_budget_pressure(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Eviction manager frees oldest unleased items to satisfy budget."""
    # Capacity: 2500 bytes. Item 1: 1600 bytes. Item 2: 1600 bytes.
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        max_cache_bytes=2500,
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/ds005620/sub-01/eeg/sub-01_task-rest_eeg.edf",
        size_bytes=1600,
    )
    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="sub-02/eeg/sub-02_task-rest_eeg.edf",
        source_uri="https://openneuro.org/ds005620/sub-02/eeg/sub-02_task-rest_eeg.edf",
        size_bytes=1600,
    )

    # Fetch item 1
    res1 = cache.fetch("ds005620", "sub-01/eeg/sub-01_task-rest_eeg.edf", allow_network=True)
    assert res1.success is True
    assert cache.budget.current_bytes > 0

    # Sleep slightly so timestamps differ
    time.sleep(0.01)

    # Fetch item 2: requires evicting item 1
    res2 = cache.fetch("ds005620", "sub-02/eeg/sub-02_task-rest_eeg.edf", allow_network=True)
    assert res2.success is True

    # Item 1 should now be evicted from disk, but preserved in manifest
    rec1 = cache._records.get(("ds005620", "sub-01/eeg/sub-01_task-rest_eeg.edf", 0))
    assert rec1 is not None
    assert rec1.status == CacheItemStatus.EVICTED.value
    assert rec1.cached_path is None
    assert rec1.last_evicted_at is not None

    # Item 2 is cached
    rec2 = cache._records.get(("ds005620", "sub-02/eeg/sub-02_task-rest_eeg.edf", 0))
    assert rec2 is not None
    assert rec2.status == CacheItemStatus.CACHED.value


def test_active_lease_protects_chunk_from_eviction(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Active lease prevents chunk from being evicted; if eviction fails, returns ACTIVE_LEASE_LOCKED."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        max_cache_bytes=2500,
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        source_uri="https://openneuro.org/ds005620/sub-01/eeg/sub-01_task-rest_eeg.edf",
        size_bytes=1600,
    )
    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="sub-02/eeg/sub-02_task-rest_eeg.edf",
        source_uri="https://openneuro.org/ds005620/sub-02/eeg/sub-02_task-rest_eeg.edf",
        size_bytes=1600,
    )

    # Fetch item 1 and acquire lease on it
    cache.fetch("ds005620", "sub-01/eeg/sub-01_task-rest_eeg.edf", allow_network=True)
    handle = cache.acquire_lease("ds005620", "sub-01/eeg/sub-01_task-rest_eeg.edf")
    assert handle.lease_id != ""

    # Attempt to fetch item 2: cannot evict item 1 because of active lease
    res2 = cache.fetch("ds005620", "sub-02/eeg/sub-02_task-rest_eeg.edf", allow_network=True)
    assert res2.success is False
    assert res2.error_code == CacheErrorCode.ACTIVE_LEASE_LOCKED.value

    # Release lease
    released = cache.release_lease(handle)
    assert released is True

    # Now fetch item 2 succeeds because item 1 can be evicted
    res3 = cache.fetch("ds005620", "sub-02/eeg/sub-02_task-rest_eeg.edf", allow_network=True)
    assert res3.success is True


def test_lease_ttl_auto_expiration(temp_cache_dir: Path) -> None:
    """Leases with a TTL expire automatically."""
    lm = LeaseManager()
    handle = lm.acquire_lease("ds005620", "sub-01/eeg/test.edf", ttl_seconds=0.05)
    assert lm.is_leased("ds005620", "sub-01/eeg/test.edf") is True

    time.sleep(0.08)
    assert lm.is_leased("ds005620", "sub-01/eeg/test.edf") is False
    assert lm.total_active_leases() == 0


# -----------------------------------------------------------------------------
# 6. Eviction Security & Stale Partial Cleanup
# -----------------------------------------------------------------------------

def test_eviction_outside_cache_root_forbidden(temp_cache_dir: Path) -> None:
    """Eviction manager strictly forbids deleting files outside cache_root."""
    lm = LeaseManager()
    evict_mgr = BoundedEvictionManager(cache_root=temp_cache_dir, lease_manager=lm)

    outside_file = temp_cache_dir.parent / "unauthorized.txt"
    outside_file.write_text("critical data")

    with pytest.raises(EvictionSecurityError, match="Security violation"):
        evict_mgr._verify_containment(outside_file)

    assert outside_file.exists()
    outside_file.unlink()


def test_stale_partial_cleanup(temp_cache_dir: Path) -> None:
    """Cleanup removes abandoned .part.* files and ignores regular files."""
    part1 = temp_cache_dir / "ds005620" / "test.edf.part.1234abcd"
    part1.parent.mkdir(parents=True, exist_ok=True)
    part1.write_bytes(b"partial content 1")

    part2 = temp_cache_dir / "ds005620" / "test2.edf.part.5678efgh"
    part2.write_bytes(b"partial content 2")

    regular = temp_cache_dir / "ds005620" / "intact.edf"
    regular.write_bytes(b"intact content")

    cache = BoundedChunkCache(cache_root=temp_cache_dir)
    count, reclaimed = cache.cleanup_stale_partials(max_age_seconds=0.0)

    assert count == 2
    assert reclaimed == len(b"partial content 1") + len(b"partial content 2")
    assert not part1.exists()
    assert not part2.exists()
    assert regular.exists()


# -----------------------------------------------------------------------------
# 7. Transient Errors & Retry Backoff
# -----------------------------------------------------------------------------

def test_transient_reset_retry_success(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Transient connection resets are retried and succeed within max_retries."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    uri = "https://openneuro.org/ds005620/participants.tsv"
    # Set 2 transient failures (attempts 1 and 2 fail, 3 succeeds)
    mock_adapter.set_transient_failure(uri, failure_count=2)

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri=uri,
        size_bytes=52,
    )

    res = cache.fetch("ds005620", "participants.tsv", allow_network=True, max_retries=3)
    assert res.success is True
    assert res.attempts == 3


def test_transient_reset_retry_exhaustion(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """When transient failures exceed max_retries, fails with NETWORK_ERROR."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    uri = "https://openneuro.org/ds005620/participants.tsv"
    # Set 5 transient failures, max_retries=2
    mock_adapter.set_transient_failure(uri, failure_count=5)

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri=uri,
        size_bytes=52,
    )

    res = cache.fetch("ds005620", "participants.tsv", allow_network=True, max_retries=2)
    assert res.success is False
    assert res.error_code == CacheErrorCode.NETWORK_ERROR.value
    assert res.attempts == 2


# -----------------------------------------------------------------------------
# 8. Pre-Flight Disk Headroom Check
# -----------------------------------------------------------------------------

def test_preflight_disk_exhaustion_detected(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """Pre-flight check detects when available disk space is insufficient."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri="https://openneuro.org/ds005620/participants.tsv",
        size_bytes=52,
    )

    # Mock disk_usage to report only 100 bytes free while headroom requires 50 MB
    with patch("shutil.disk_usage") as mock_disk:
        mock_disk.return_value = MagicMock(total=10**9, used=10**9 - 100, free=100)
        res = cache.fetch("ds005620", "participants.tsv", allow_network=True)
        assert res.success is False
        assert res.error_code == CacheErrorCode.DISK_EXHAUSTION.value
        assert "Disk exhaustion detected" in res.error_message


# -----------------------------------------------------------------------------
# 9. Deterministic Reports & Cryptographic Verification
# -----------------------------------------------------------------------------

def test_tamper_evident_report_and_hash_verification(temp_cache_dir: Path, mock_adapter: MockTransferAdapter) -> None:
    """CacheReport includes deterministic SHA-256 and passes verification."""
    cache = BoundedChunkCache(
        cache_root=temp_cache_dir,
        transfer_adapter=mock_adapter,
    )

    cache.register_manifest_item(
        dataset_id="ds005620",
        bids_path="participants.tsv",
        source_uri="https://openneuro.org/ds005620/participants.tsv",
        size_bytes=52,
    )
    cache.fetch("ds005620", "participants.tsv", allow_network=True)

    rep = cache.inspect()
    assert rep.cached_items_count == 1
    assert rep.report_checksum_sha256 != ""

    rep_dict = rep.to_dict()
    assert verify_cache_report_checksum(rep_dict) is True

    # Tampering with report invalidates checksum
    rep_dict["total_manifest_items"] = 999
    assert verify_cache_report_checksum(rep_dict) is False


def test_report_rejects_non_finite_floats() -> None:
    """CacheReport serialization strictly rejects NaN and Infinity."""
    rep = CacheReport(
        schema_version="v1.0.0",
        report_timestamp="2026-09-11T00:00:00Z",
        budget={"max_cache_bytes": float("nan")},
    )
    with pytest.raises(ValueError, match="Non-compliant float"):
        rep.to_dict()

    rep_inf = CacheReport(
        schema_version="v1.0.0",
        report_timestamp="2026-09-11T00:00:00Z",
        budget={"max_cache_bytes": float("inf")},
    )
    with pytest.raises(ValueError, match="Non-compliant float"):
        rep_inf.to_dict()


# -----------------------------------------------------------------------------
# 10. CLI Subprocess Integration
# -----------------------------------------------------------------------------

def test_cli_plan_register_inspect(temp_cache_dir: Path) -> None:
    """Test CLI commands: register, plan, and inspect via subprocess."""
    cli_script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "openneuro_chunk_fetch.py"

    # 1. Register
    reg_cmd = [
        sys.executable,
        str(cli_script),
        "--cache-root", str(temp_cache_dir),
        "register",
        "--dataset-id", "ds005620",
        "--bids-path", "participants.tsv",
        "--source-uri", "https://openneuro.org/ds005620/participants.tsv",
        "--size-bytes", "52",
    ]
    proc_reg = subprocess.run(reg_cmd, capture_output=True, text=True)
    assert proc_reg.returncode == 0
    reg_data = json.loads(proc_reg.stdout)
    assert reg_data["dataset_id"] == "ds005620"

    # 2. Plan
    plan_cmd = [
        sys.executable,
        str(cli_script),
        "--cache-root", str(temp_cache_dir),
        "plan",
        "--dataset-id", "ds005620",
    ]
    proc_plan = subprocess.run(plan_cmd, capture_output=True, text=True)
    assert proc_plan.returncode == 0
    plan_data = json.loads(proc_plan.stdout)
    assert plan_data["is_executable"] is True
    assert plan_data["total_download_bytes"] == 52

    # 3. Inspect (Markdown)
    insp_cmd = [
        sys.executable,
        str(cli_script),
        "--cache-root", str(temp_cache_dir),
        "--format", "markdown",
        "inspect",
    ]
    proc_insp = subprocess.run(insp_cmd, capture_output=True, text=True)
    assert proc_insp.returncode == 0
    assert "# OpenNeuro Bounded Chunk Cache Audit Report" in proc_insp.stdout
    assert "participants.tsv" in proc_insp.stdout
