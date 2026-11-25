"""Offline tests for the bounded ds000245 access seam.

These tests use the canonical in-memory transfer adapter and verify
rejection of legacy full-dataset calls. They intentionally do not
enumerate OpenNeuro or materialize a complete NIfTI object.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.data_access.chunk_cache import ChunkRange, MockTransferAdapter
from tools.fetch_ds000245 import BoundedAccessError, BoundedObjectRequest, fetch


def _request(tmp_path, payload: bytes = b"0123456789", *, allow_network: bool = True, chunk_sha256: str | None = None):
    source_sha256 = hashlib.sha256(payload).hexdigest()
    return BoundedObjectRequest(
        dataset_id="ds000245",
        bids_path="sub-CTL01/func/sub-CTL01_task-rest_bold.nii.gz",
        source_uri="mock://ds000245/sub-CTL01/bold",
        expected_size_bytes=len(payload),
        source_sha256=source_sha256,
        cache_root=tmp_path / "cache",
        output_root=tmp_path / "outputs",
        max_cache_bytes=64,
        chunk_range=ChunkRange(0, 3, total_file_size=len(payload)),
        final_consumer="ds000245-test",
        eviction_metadata={
            "consumer_id": "ds000245-test",
            "final_consumer": "ds000245-test",
            "delete_after_final_consumer": True,
        },
        allow_network=allow_network,
        chunk_sha256=chunk_sha256 or hashlib.sha256(payload[:4]).hexdigest(),
    )


def test_bounded_fetch_uses_fake_remote_and_evicts_after_consume(tmp_path: Path):
    payload = b"0123456789"
    request = _request(tmp_path, payload)
    adapter = MockTransferAdapter()
    adapter.register_remote_object(request.source_uri, payload)
    consumed: list[bytes] = []

    result = fetch(
        [request],
        transfer_adapter=adapter,
        consume=lambda path: consumed.append(path.read_bytes()),
    )

    assert result["results"][0]["success"] is True
    assert result["results"][0]["checksum_verified"] is True
    assert result["results"][0]["cleanup"]["status"] == "deleted"
    assert consumed == [payload[:4]]
    assert list((tmp_path / "cache").rglob("*.part*")) == []


def test_bounded_fetch_is_network_disabled_by_default(tmp_path: Path):
    payload = b"0123456789"
    request = _request(tmp_path, payload, allow_network=False)
    adapter = MockTransferAdapter()
    adapter.register_remote_object(request.source_uri, payload)

    result = fetch([request], transfer_adapter=adapter)

    assert result["results"][0]["success"] is False
    assert result["results"][0]["error_code"] == "NETWORK_DISABLED"


def test_checksum_mismatch_does_not_complete(tmp_path: Path):
    payload = b"0123456789"
    request = _request(tmp_path, payload, chunk_sha256="0" * 64)
    adapter = MockTransferAdapter()
    adapter.register_remote_object(request.source_uri, payload)

    result = fetch([request], transfer_adapter=adapter)

    assert result["results"][0]["success"] is False
    assert result["results"][0]["error_code"] == "CHECKSUM_MISMATCH"


def test_legacy_full_dataset_arguments_are_rejected(tmp_path: Path):
    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path / "data")


def test_legacy_subject_and_limit_filters_are_rejected(tmp_path: Path):
    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path, subjects=["sub-CTL01"])
    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path, limit=1)


def test_empty_or_missing_bounded_request_is_rejected(tmp_path: Path):
    with pytest.raises(BoundedAccessError, match="explicit"):
        fetch(None)
    with pytest.raises(BoundedAccessError, match="at least one"):
        fetch([])
