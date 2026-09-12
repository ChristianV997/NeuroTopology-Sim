"""Hermetic tests for the P0 acquisition callers.

These tests use fixtures and the repository's mock transfer adapter only.  No
test contacts OpenNeuro, DANDI, AWS, or an arbitrary URL.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from data.bids_ingest import BIDSEEGRecord, inventory_from_records
from data.dandi_nwb_ingest import DandiAsset
from tools.data_access.chunk_cache import ChunkRange, MockTransferAdapter
from tools.fetch_ds000245 import BoundedAccessError, BoundedObjectRequest, fetch, plan
from tools.data_access.policy_enforcement.scanner import scan_paths


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "fmri_tda_ds000245.yml"


def _asset(size: int = 1024) -> DandiAsset:
    return DandiAsset(
        dandiset_id="000458",
        version="0.230317.0039",
        path="sub-mouse01/sub-mouse01_behavior+ecephys.nwb",
        subject_id="sub-mouse01",
        blob_url="https://dandiarchive.org/blobs/fixture",
        content_size=size,
    )


def _request(tmp_path: Path, *, allow_network: bool = False, chunk_sha256: str | None = None):
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
        chunk_sha256=chunk_sha256 if chunk_sha256 is not None else hashlib.sha256(selected).hexdigest(),
        cache_root=tmp_path / "cache",
        output_root=tmp_path / "output",
        max_cache_bytes=1024,
        chunk_range=ChunkRange(16, 31, total_file_size=len(content)),
        final_consumer="p0-test",
        eviction_metadata={
            "consumer_id": "p0-test",
            "final_consumer": "p0-test",
            "delete_after_final_consumer": True,
        },
        allow_network=allow_network,
    )
    return request, selected, adapter


def test_workflow_is_metadata_only_and_has_no_legacy_transfer_commands():
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "aws s3 cp" not in lowered
    assert "aws s3 sync" not in lowered
    assert "openneuro download" not in lowered
    assert "curl " not in lowered
    assert "wget " not in lowered
    assert "list-objects-v2" in lowered
    assert "allow_metadata_network" in lowered
    assert "data_materialized" in lowered


def test_workflow_does_not_run_signal_pipeline_or_atlas_transfer():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "dual_engine.fmri_tda_pipeline" not in text
    assert "atlas_url" not in text
    assert "metadata-only preflight" in text
    assert "data_materialized" in text


def test_dandi_run_defaults_to_offline_and_does_not_resolve_metadata(tmp_path, monkeypatch):
    import tools.stream_process_dandi000458 as streamer

    def should_not_resolve(*args, **kwargs):
        raise AssertionError("metadata resolver must not be called without permission")

    monkeypatch.setattr(streamer, "resolve_asset_blobs", should_not_resolve)
    with pytest.raises(PermissionError, match="allow-network"):
        streamer.run(str(tmp_path / "out"), 10.0, 1, 2, 1, None)
    assert not (tmp_path / "out").exists()


def test_dandi_process_defaults_to_offline_before_opening_nwb(monkeypatch, tmp_path):
    import tools.stream_process_dandi000458 as streamer

    def should_not_open(*args, **kwargs):
        raise AssertionError("NWB opener must not be called without permission")

    monkeypatch.setattr(streamer, "open_nwb_lazy", should_not_open)
    with pytest.raises(PermissionError, match="allow_network"):
        streamer.process_asset(_asset(), tmp_path, 10.0, 1, 2)


def test_dandi_explicit_permission_is_manifest_first_and_deterministic(tmp_path, monkeypatch):
    import tools.stream_process_dandi000458 as streamer

    assets = [_asset()]
    calls = []

    def fake_resolve(*args, **kwargs):
        calls.append((args, kwargs))
        return assets

    def fake_loop(items, out_dir, **kwargs):
        calls.append((list(items), out_dir, kwargs))

    processed = []

    def fake_process(*args, **kwargs):
        processed.append((args, kwargs))
        return {}

    monkeypatch.setattr(streamer, "resolve_asset_blobs", fake_resolve)
    monkeypatch.setattr(streamer.base_runner, "run_manifest_loop", fake_loop)
    monkeypatch.setattr(streamer, "process_asset", fake_process)
    out = tmp_path / "out"
    assert streamer.run(str(out), 10.0, 1, 2, 1, None, allow_network=True) == 0

    manifest = json.loads((out / "access_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_first"] is True
    assert manifest["data_materialization"] == "lazy_bounded_windows"
    assert manifest["network_accessed"] is True
    assert manifest["assets"][0]["expected_size_bytes"] == 1024
    assert manifest["assets"][0]["checksum_status"] == "unknown"
    assert manifest["assets"][0]["expected_checksum"] is None
    assert calls[0][1]["network_permission"] is True
    process_kwargs = calls[1][2]
    process_kwargs["process_fn"](assets[0])
    assert processed[0][1]["allow_network"] is True

    first = json.dumps(manifest, sort_keys=True, allow_nan=False)
    second = json.dumps(json.loads((out / "access_manifest.json").read_text(encoding="utf-8")), sort_keys=True, allow_nan=False)
    assert first == second


def test_dandi_manifest_rejects_unknown_size_and_contains_explicit_bounds():
    import tools.stream_process_dandi000458 as streamer

    with pytest.raises(ValueError, match="content size"):
        streamer._access_contract(_asset(size=0), allow_network=True)
    contract = streamer._access_contract(_asset(), allow_network=True)
    payload = contract.to_dict()
    assert payload["max_window_bytes"] == payload["cache_budget_bytes"]
    assert payload["eviction_policy"] == "release_after_final_consumer"
    assert payload["expected_checksum"] is None
    json.dumps(payload, allow_nan=False)


def test_dandi_output_paths_are_contained(tmp_path):
    import tools.stream_process_dandi000458 as streamer

    assert streamer._contained_output(tmp_path, "nested/result.json").parent == tmp_path / "nested"
    with pytest.raises(ValueError, match="escapes"):
        streamer._contained_output(tmp_path, "../escape.json")


def test_bids_fallback_inventory_is_not_claimed_as_validated_real_bids():
    record = BIDSEEGRecord(
        path="fixture/sub-01/eeg/sub-01_task-rest_eeg.edf",
        relative_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        subject_id="sub-01", session_id=None, task_label="rest", run_id=None,
        acq_label=None, extension=".edf", is_eeg_candidate=True,
        provenance="local_bids_unvalidated",
    )
    payload = inventory_from_records("fixture", [record])
    assert payload["provenance"] == "unvalidated_or_mixed"
    assert payload["eeg_candidates"][0]["provenance"] == "local_bids_unvalidated"


def test_bounded_plan_is_manifest_first_and_network_free(tmp_path):
    request, _, adapter = _request(tmp_path)
    payload = plan([request], transfer_adapter=adapter)
    assert payload["network_accessed"] is False
    assert payload["is_executable"] is True
    assert payload["plans"][0]["total_download_bytes"] == 16


def test_missing_chunk_checksum_is_explicitly_not_executable(tmp_path):
    request, _, adapter = _request(tmp_path)
    request = request.__class__(**{**request.__dict__, "chunk_sha256": None})
    payload = plan([request], transfer_adapter=adapter)
    assert payload["is_executable"] is False
    assert payload["plans"][0]["rejection_reason"] == "chunk_sha256 is required"
    with pytest.raises(BoundedAccessError, match="chunk_sha256"):
        fetch([request], transfer_adapter=adapter)


def test_bounded_full_object_request_is_rejected(tmp_path):
    with pytest.raises(BoundedAccessError, match="full-object"):
        BoundedObjectRequest(
            dataset_id="ds000245",
            bids_path="sub-01/func/sub-01_task-rest_bold.nii.gz",
            source_uri="mock://openneuro/full",
            expected_size_bytes=10,
            source_sha256="a" * 64,
            cache_root=tmp_path / "cache",
            output_root=tmp_path / "output",
            max_cache_bytes=100,
            chunk_range=ChunkRange(0, 9, total_file_size=10),
            final_consumer="consumer",
            eviction_metadata={
                "consumer_id": "consumer",
                "final_consumer": "consumer",
                "delete_after_final_consumer": True,
            },
        )


def test_bounded_transfer_requires_explicit_network_and_releases_cache(tmp_path):
    request, selected, adapter = _request(tmp_path, allow_network=False)
    blocked = fetch([request], transfer_adapter=adapter)
    assert blocked["results"][0]["error_code"] == "NETWORK_DISABLED"
    assert not list((tmp_path / "cache").glob("*.part*"))

    request, selected, adapter = _request(tmp_path, allow_network=True)
    seen = []
    result = fetch([request], transfer_adapter=adapter, consume=lambda path: seen.append(path.read_bytes()))
    assert result["results"][0]["success"] is True
    assert seen == [selected]
    assert result["results"][0]["cleanup"]["status"] == "deleted"


def test_owned_python_callers_have_no_direct_transfer_primitives():
    forbidden = {"download_file", "download_fileobj", "get_object", "urlopen", "urlretrieve", "copyfileobj"}
    for relative in ("data/bids_ingest.py", "tools/stream_process_dandi000458.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and (isinstance(node.func, (ast.Attribute, ast.Name)))
        }
        assert not names.intersection(forbidden), (relative, names.intersection(forbidden))


def test_owned_scanner_has_no_direct_remote_transfer_finding():
    report = scan_paths(
        ["tools/stream_process_dandi000458.py"],
        repository_root=ROOT,
    )
    assert report.compliant is True
    assert report.findings == []


def test_owned_data_bids_scanner_residuals_are_local_cache_heuristics_only():
    report = scan_paths(["data/bids_ingest.py"], repository_root=ROOT)
    assert report.compliant is False
    assert len(report.findings) == 8
    assert {item.rule for item in report.findings} <= {
        "MISSING_CACHE_BOUND", "MISSING_CHECKSUM", "MISSING_EVICTION"
    }
