"""Adversarial hardening tests for ApprovedAcquisitionAdapter.

Verifies:
1. Rejection of full-object ranges across API and CLI.
2. Rejection of full-dataset wildcards ('*', '**/*', 'sub-*', '.') with FULL_DATASET_REJECTED.
3. Rejection of unrestricted paths (traversal '..', absolute paths, drive letters) with UNRESTRICTED_PATH_REJECTED.
4. Rejection of unknown size (0, -1) with UNKNOWN_SIZE_REJECTED.
5. Rejection of missing/invalid cache budget with MISSING_CACHE_BUDGET.
6. Rejection of missing/invalid eviction policy with MISSING_EVICTION_POLICY.
7. Rejection of missing/invalid checksum policy with MISSING_CHECKSUM_POLICY.
8. Rejection of unpermitted network access with NETWORK_DISABLED.
9. Impossibility of CLI --allow-full-object bypass.
10. Machine-readable policy registration integrity.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
import tempfile

from scripts.plan_bounded_acquisition import main as cli_main
from tools.data_access.approved_adapter import (
    APPROVED_ADAPTER_REGISTRATION_SCHEMA,
    APPROVED_BOUNDED_ADAPTER_POLICY_RECORD,
    AdapterErrorCode,
    ApprovedAcquisitionAdapter,
    BoundedAcquisitionRequest,
    ChecksumPolicy,
    EvictionPolicy,
    LicenseAccessState,
    get_approved_adapter_policy_record,
)
from tools.data_access.chunk_cache import MockTransferAdapter


@pytest.fixture
def temp_cache():
    with tempfile.TemporaryDirectory() as td:
        yield td


def _base_valid_request(**overrides) -> BoundedAcquisitionRequest:
    kwargs = {
        "dataset_id": "ds004504",
        "object_path": "sub-01/eeg/sub-01_task-rest_eeg.edf",
        "source_uri": "https://openneuro.org/dummy",
        "expected_size_bytes": 10000,
        "start_byte": 0,
        "end_byte": 1023,
        "cache_budget_bytes": 100 * 1024 * 1024,
        "min_headroom_bytes": 10 * 1024 * 1024,
        "eviction_policy": EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value,
        "checksum_policy": ChecksumPolicy.SHA256_IF_AVAILABLE.value,
        "license_state": LicenseAccessState.OPEN_CC0.value,
        "allow_network": False,
    }
    kwargs.update(overrides)
    return BoundedAcquisitionRequest(**kwargs)


class TestFullObjectHardening:
    """Verifies complete prevention of full-object downloads in production."""

    def test_full_range_rejected(self, temp_cache):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        # Exactly covers full 10000 bytes (0 to 9999)
        req = _base_valid_request(expected_size_bytes=10000, start_byte=0, end_byte=9999)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.FULL_OBJECT_REJECTED.value in r for r in plan.rejection_reasons)

    def test_single_byte_full_range_rejected(self, temp_cache):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        # 1-byte file requested from 0 to 0 (full object)
        req = _base_valid_request(expected_size_bytes=1, start_byte=0, end_byte=0)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.FULL_OBJECT_REJECTED.value in r for r in plan.rejection_reasons)

    def test_test_only_attribute_ignored_without_env_var(self, temp_cache, monkeypatch):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        monkeypatch.delenv("NEUROTOPOLOGY_ALLOW_TEST_FULL_OBJECT", raising=False)
        req = _base_valid_request(
            expected_size_bytes=500,
            start_byte=0,
            end_byte=499,
            _test_only_allow_full_object=True,
        )
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.FULL_OBJECT_REJECTED.value in r for r in plan.rejection_reasons)

    def test_cli_rejects_allow_full_object_flag(self):
        """CLI must fail parser immediately if --allow-full-object is passed."""
        with pytest.raises(SystemExit) as exc_info:
            cli_main([
                "plan",
                "--dataset-id", "ds004504",
                "--object-path", "sub-01/eeg/test.edf",
                "--expected-size", "1000",
                "--allow-full-object",
            ])
        # argparse error exit code is 2
        assert exc_info.value.code == 2


class TestFullDatasetHardening:
    """Verifies rejection of wildcards and dataset-level unrestricted targets."""

    @pytest.mark.parametrize("bad_path", [
        "*",
        "**/*",
        "sub-*",
        "sub-01/*",
        "*.edf",
        "?",
        "sub-01/eeg/[a-z]*.edf",
        ".",
        "",
        "   ",
    ])
    def test_wildcards_and_dataset_paths_rejected(self, temp_cache, bad_path):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        req = _base_valid_request(object_path=bad_path)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(
            AdapterErrorCode.FULL_DATASET_REJECTED.value in r
            or AdapterErrorCode.UNRESTRICTED_PATH_REJECTED.value in r
            for r in plan.rejection_reasons
        )


class TestUnrestrictedPathHardening:
    """Verifies rejection of path traversals, drive letters, and root escapes."""

    @pytest.mark.parametrize("evil_path", [
        "../secret.txt",
        "sub-01/../../secret.txt",
        "/etc/passwd",
        "/var/data/eeg.edf",
        r"C:\Windows\System32\cmd.exe",
        r"D:\datasets\all",
        "sub-01/../..",
    ])
    def test_unrestricted_traversal_rejected(self, temp_cache, evil_path):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        req = _base_valid_request(object_path=evil_path)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(
            AdapterErrorCode.UNRESTRICTED_PATH_REJECTED.value in r
            or AdapterErrorCode.FULL_DATASET_REJECTED.value in r
            for r in plan.rejection_reasons
        )


class TestValidationHardening:
    """Verifies rejection of unknown size, missing cache budget, and invalid policies."""

    @pytest.mark.parametrize("bad_size", [0, -1, -500])
    def test_unknown_size_rejected(self, temp_cache, bad_size):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        req = _base_valid_request(expected_size_bytes=bad_size)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.UNKNOWN_SIZE_REJECTED.value in r for r in plan.rejection_reasons)

    @pytest.mark.parametrize("bad_budget", [0, -1024])
    def test_missing_cache_budget_rejected(self, temp_cache, bad_budget):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        req = _base_valid_request(cache_budget_bytes=bad_budget)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.MISSING_CACHE_BUDGET.value in r for r in plan.rejection_reasons)

    @pytest.mark.parametrize("bad_eviction", ["", "keep_forever", "invalid_mode"])
    def test_invalid_eviction_policy_rejected(self, temp_cache, bad_eviction):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        req = _base_valid_request(eviction_policy=bad_eviction)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.MISSING_EVICTION_POLICY.value in r for r in plan.rejection_reasons)

    @pytest.mark.parametrize("bad_checksum", ["", "crc32", "none"])
    def test_invalid_checksum_policy_rejected(self, temp_cache, bad_checksum):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        req = _base_valid_request(checksum_policy=bad_checksum)
        plan = adapter.plan(req)
        assert plan.is_executable is False
        assert any(AdapterErrorCode.MISSING_CHECKSUM_POLICY.value in r for r in plan.rejection_reasons)


class TestFailClosedNetworkGate:
    """Verifies fail-closed network execution gate."""

    def test_network_disabled_prevents_acquisition(self, temp_cache):
        mock_transfer = MockTransferAdapter()
        mock_transfer.register_remote_object(
            source_uri="https://openneuro.org/dummy",
            content=b"0123456789" * 100,
        )
        adapter = ApprovedAcquisitionAdapter(
            cache_root=temp_cache,
            transfer_adapter=mock_transfer,
        )
        # allow_network=False by default
        req = _base_valid_request(allow_network=False)
        res = adapter.acquire(req)
        assert res.success is False
        assert res.error_code == AdapterErrorCode.NETWORK_DISABLED.value
        assert res.bytes_transferred == 0
        assert res.cached_path is None


class TestPolicyRegistrationRecord:
    """Verifies machine-readable policy registration specification."""

    def test_policy_record_structure(self, temp_cache):
        adapter = ApprovedAcquisitionAdapter(cache_root=temp_cache)
        record = adapter.get_policy_registration()

        assert record["schema_version"] == APPROVED_ADAPTER_REGISTRATION_SCHEMA
        assert record["access_class"] == "approved_bounded_range_adapter"
        assert record["path"] == "tools/data_access/approved_adapter/adapter.py"
        assert "ApprovedAcquisitionAdapter.plan" in record["symbols"]
        assert record["invariants"]["network_enabled_by_default"] is False
        assert record["invariants"]["full_object_allowed_in_production"] is False
        assert record["invariants"]["full_dataset_allowed"] is False
        assert record["invariants"]["manifest_required_before_transfer"] is True
        assert record["invariants"]["bounded_transfer_required"] is True
        assert record["invariants"]["strict_finite_json_required"] is True
        assert record["invariants"]["lease_protection_required"] is True
        assert record["invariants"]["eviction_on_final_consumer_supported"] is True
        assert record["invariants"]["path_containment_enforced"] is True

        # Ensure canonical global record matches adapter method
        global_record = get_approved_adapter_policy_record()
        assert record == global_record
