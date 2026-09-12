"""Regression tests for the legacy OpenNeuro/BIDS caller migration.

All transfer tests use the canonical in-memory adapter.  No test contacts an
external service or downloads a dataset.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from tools.data_access.chunk_cache import ChunkRange, MockTransferAdapter
from tools.fetch_ds000245 import (
    BoundedAccessError,
    BoundedObjectRequest,
    fetch,
    plan,
)


def _request(tmp_path: Path, *, allow_network: bool = False) -> tuple[BoundedObjectRequest, bytes, MockTransferAdapter]:
    content = bytes(range(128))
    selected = content[16:32]
    source_uri = "mock://openneuro/ds000245/sub-01/func/sub-01_task-rest_bold.nii.gz"
    adapter = MockTransferAdapter()
    adapter.register_remote_object(source_uri, content)
    request = BoundedObjectRequest(
        dataset_id="ds000245",
        bids_path="sub-01/func/sub-01_task-rest_bold.nii.gz",
        source_uri=source_uri,
        expected_size_bytes=len(content),
        source_sha256=hashlib.sha256(content).hexdigest(),
        chunk_sha256=hashlib.sha256(selected).hexdigest(),
        cache_root=tmp_path / "cache",
        output_root=tmp_path / "output",
        max_cache_bytes=1024,
        chunk_range=ChunkRange(16, 31, total_file_size=len(content)),
        final_consumer="test-consumer",
        eviction_metadata={
            "consumer_id": "test-consumer",
            "final_consumer": "test-consumer",
            "delete_after_final_consumer": True,
        },
        allow_network=allow_network,
    )
    return request, selected, adapter


def test_bounded_request_requires_provenance_and_eviction_metadata(tmp_path: Path) -> None:
    with pytest.raises(BoundedAccessError, match="source_sha256"):
        BoundedObjectRequest(
            dataset_id="ds000245",
            bids_path="sub-01/func/sub-01_task-rest_bold.nii.gz",
            source_uri="mock://source",
            expected_size_bytes=10,
            source_sha256="",
            cache_root=tmp_path / "cache",
            output_root=tmp_path / "output",
            max_cache_bytes=100,
            chunk_range=ChunkRange(0, 1, total_file_size=10),
            final_consumer="consumer",
            eviction_metadata={},
        )


def test_full_object_and_oversized_range_are_rejected(tmp_path: Path) -> None:
    kwargs = dict(
        dataset_id="ds000245",
        bids_path="sub-01/func/sub-01_task-rest_bold.nii.gz",
        source_uri="mock://source",
        expected_size_bytes=10,
        source_sha256="a" * 64,
        cache_root=tmp_path / "cache",
        output_root=tmp_path / "output",
        max_cache_bytes=100,
        final_consumer="consumer",
        eviction_metadata={"consumer_id": "consumer", "final_consumer": "consumer", "delete_after_final_consumer": True},
    )
    with pytest.raises(BoundedAccessError, match="full-object"):
        BoundedObjectRequest(**kwargs, chunk_range=ChunkRange(0, 9, total_file_size=10))
    with pytest.raises(BoundedAccessError, match="exceeds expected"):
        BoundedObjectRequest(**kwargs, chunk_range=ChunkRange(9, 10, total_file_size=10))


def test_legacy_ds000245_arguments_are_rejected_without_network(tmp_path: Path) -> None:
    from tools.fetch_ds000245 import fetch

    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path, subjects=["sub-01"])


def test_plan_is_manifest_first_bounded_and_network_free(tmp_path: Path) -> None:
    request, _, adapter = _request(tmp_path)
    payload = plan([request], transfer_adapter=adapter)
    assert payload["network_accessed"] is False
    assert payload["is_executable"] is True
    assert payload["plans"][0]["total_download_bytes"] == 16
    assert payload["requests"][0]["chunk_range"]["start_byte"] == 16


def test_fetch_is_fail_closed_without_network_permission(tmp_path: Path) -> None:
    request, _, adapter = _request(tmp_path, allow_network=False)
    payload = fetch([request], transfer_adapter=adapter)
    assert payload["results"][0]["success"] is False
    assert payload["results"][0]["error_code"] == "NETWORK_DISABLED"


def test_fetch_transfers_only_range_and_deletes_after_consumer(tmp_path: Path) -> None:
    request, selected, adapter = _request(tmp_path, allow_network=True)
    seen: list[bytes] = []

    def consume(path: Path) -> None:
        seen.append(path.read_bytes())

    payload = fetch([request], transfer_adapter=adapter, consume=consume)
    result = payload["results"][0]
    assert result["success"] is True
    assert seen == [selected]
    assert result["cleanup"]["status"] == "deleted"
    assert result["bytes_transferred"] == len(selected)


def test_eeg_metadata_is_opt_in_and_download_switch_is_rejected(tmp_path: Path) -> None:
    import scripts.eeg_topology_ds005620 as eeg

    with pytest.raises(eeg.DataAccessBlocked, match="disabled"):
        eeg.openneuro_file_inventory("ds005620", "1.0.0")
    with pytest.raises(eeg.DataAccessBlocked, match="full OpenNeuro"):
        eeg.ensure_dataset(tmp_path, "ds005620", "1.0.0", download=True)


def test_eeg_window_planning_requires_checksum_and_is_deterministic(tmp_path: Path) -> None:
    import scripts.eeg_topology_ds005620 as eeg

    inventory = [{
        "filename": "sub-01/eeg/sub-01_task-awake_eeg.edf",
        "size": 100,
        "sha256": "b" * 64,
        "source_uri": "mock://openneuro/eeg",
    }]
    windows = {"sub-01/eeg/sub-01_task-awake_eeg.edf": {"start_byte": 2, "end_byte": 9}}
    first = eeg.plan_bounded_windows(
        inventory, dataset="ds005620", cache_root=tmp_path / "cache", output_root=tmp_path / "output",
        max_cache_bytes=1000, windows=windows, final_consumer="test-consumer",
        eviction_metadata={"consumer_id": "test-consumer", "final_consumer": "test-consumer", "delete_after_final_consumer": True},
    )
    second = eeg.plan_bounded_windows(
        inventory, dataset="ds005620", cache_root=tmp_path / "cache", output_root=tmp_path / "output",
        max_cache_bytes=1000, windows=windows, final_consumer="test-consumer",
        eviction_metadata={"consumer_id": "test-consumer", "final_consumer": "test-consumer", "delete_after_final_consumer": True},
    )
    assert first == second
    assert first["network_accessed"] is False
    with pytest.raises(eeg.DataAccessBlocked, match="SHA-256"):
        eeg.plan_bounded_windows(
            [{"filename": inventory[0]["filename"], "size": 100, "source_uri": "mock://x"}],
            dataset="ds005620", cache_root=tmp_path / "c2", output_root=tmp_path / "o2",
            max_cache_bytes=1000, windows=windows, final_consumer="test-consumer",
            eviction_metadata={"consumer_id": "test-consumer", "final_consumer": "test-consumer", "delete_after_final_consumer": True},
        )


def test_legacy_real_dataset_functions_fail_closed(tmp_path: Path) -> None:
    import scripts.fetch_real_datasets as legacy

    with pytest.raises(legacy.FullObjectDownloadRejected):
        legacy.download_pdb(tmp_path / "1jff.pdb")
    with pytest.raises(BoundedAccessError, match="bids_path"):
        legacy.download_eeg(tmp_path / "eeg.edf")


def test_owned_callers_have_no_legacy_transfer_calls() -> None:
    root = Path(__file__).resolve().parents[3]
    paths = [root / "tools" / "fetch_ds000245.py", root / "scripts" / "eeg_topology_ds005620.py", root / "scripts" / "fetch_real_datasets.py"]
    forbidden = {"download_file", "openneuro", "aws", "urlretrieve", "Popen"}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        names = {getattr(node.func, "attr", getattr(node.func, "id", "")) for node in calls}
        assert not names.intersection(forbidden), f"legacy transfer call in {path}: {names & forbidden}"


def test_json_outputs_are_finite_and_stable(tmp_path: Path) -> None:
    request, _, adapter = _request(tmp_path)
    first = json.dumps(plan([request], transfer_adapter=adapter), sort_keys=True, allow_nan=False)
    second = json.dumps(plan([request], transfer_adapter=adapter), sort_keys=True, allow_nan=False)
    assert first == second
