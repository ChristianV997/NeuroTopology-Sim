"""Hermetic contract tests for bounded DANDI/NWB access."""
from __future__ import annotations

import hashlib
import json

import pytest

from data.dandi_nwb_ingest import (
    IngestionState,
    IngestionContractError,
    LocalFileWindowSource,
    LocalMetadataSource,
    Provenance,
    WindowCache,
    WindowRequest,
    inspect_metadata,
    read_bounded_window,
    reject_full_recording_materialization,
    release_window,
    open_nwb_lazy,
    resolve_asset_blobs,
)


def _provenance(**kwargs):
    values = dict(dataset_identity="fixture-ds", object_identity="run-01", source_kind="local_fixture", source_uri="fixture://run-01", synthetic=True)
    values.update(kwargs)
    return Provenance(**values)


def _request(size=8, **kwargs):
    values = dict(provenance=_provenance(), start=0, stop=size, unit="bytes", expected_size=size, checksum_policy="sha256", expected_checksum=None, cache_budget_bytes=64, consumer_lease="consumer-a", eviction_policy="release_after_final_consumer", network_permission=False)
    values.update(kwargs)
    return WindowRequest(**values)


class FakeSource:
    def __init__(self, payload=b"abcdefgh", *, source_size=8, failures=0, short=False, interrupt=False):
        self.payload, self.source_size, self.failures = payload, source_size, failures
        self.short, self.interrupt, self.calls, self.closed = short, interrupt, 0, 0

    def size(self, request):
        return self.source_size

    def read_window(self, request):
        self.calls += 1
        if self.interrupt:
            raise InterruptedError("fixture interruption")
        if self.calls <= self.failures:
            raise OSError("transient fixture failure")
        return self.payload[:-1] if self.short else self.payload

    def close(self):
        self.closed += 1


def test_bounded_read_checksum_and_deterministic_close():
    source = FakeSource()
    result = read_bounded_window(source, _request(expected_checksum=hashlib.sha256(b"abcdefgh").hexdigest()))
    assert result.state is IngestionState.COMPLETE
    assert result.data == b"abcdefgh"
    assert result.checksum == hashlib.sha256(b"abcdefgh").hexdigest()
    assert source.closed == 1
    assert "data" not in result.to_dict()  # JSON never contains signal bytes


def test_oversized_window_is_blocked():
    result = read_bounded_window(FakeSource(), _request(size=9, stop=9, expected_size=9), max_window_bytes=8)
    assert result.state is IngestionState.BLOCKED
    assert "bounded" in result.error


def test_unknown_size_fails_closed():
    result = read_bounded_window(FakeSource(source_size=None), _request())
    assert result.state is IngestionState.FAILED
    assert "unknown" in result.error


def test_checksum_mismatch_has_no_checksum():
    result = read_bounded_window(FakeSource(), _request(expected_checksum="0" * 64))
    assert result.state is IngestionState.FAILED
    assert result.checksum is None
    assert result.to_dict()["checksum"] is None


def test_retry_then_success():
    source = FakeSource(failures=2)
    result = read_bounded_window(source, _request(), max_retries=2)
    assert result.state is IngestionState.COMPLETE
    assert result.attempts == 3
    assert source.closed == 3  # each retry owns and closes its read handle


def test_short_read_is_partial_and_resumable():
    result = read_bounded_window(FakeSource(short=True), _request())
    assert result.state is IngestionState.PARTIAL
    assert result.checksum is None
    assert result.resume_from == 7


def test_interruption_is_partial_and_closed():
    source = FakeSource(interrupt=True)
    result = read_bounded_window(source, _request())
    assert result.state is IngestionState.PARTIAL
    assert source.closed == 1


def test_cache_eviction_and_final_consumer_release():
    cache = WindowCache(8)
    first = read_bounded_window(FakeSource(), _request(consumer_lease="a"), cache=cache)
    assert cache.current_bytes == 8
    # The active lease prevents replacement until explicitly released.
    blocked = read_bounded_window(FakeSource(), _request(consumer_lease="b", provenance=_provenance(object_identity="run-02")), cache=cache)
    assert blocked.state is IngestionState.BLOCKED
    assert release_window(cache, first, final_consumer=True)
    assert cache.current_bytes == 0
    second = read_bounded_window(FakeSource(), _request(consumer_lease="b", provenance=_provenance(object_identity="run-02")), cache=cache)
    assert second.state is IngestionState.COMPLETE


def test_metadata_only_does_not_read_signal(tmp_path):
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"sampling_rate_hz": 100}), encoding="utf-8")
    result = inspect_metadata(LocalMetadataSource(metadata), "ds", "obj")
    assert result["state"] == "METADATA_ONLY"
    assert result["metadata"]["sampling_rate_hz"] == 100


def test_offline_mode_fails_closed():
    result = read_bounded_window(FakeSource(), _request(offline=True, network_permission=True))
    assert result.state is IngestionState.OFFLINE_BLOCKED


def test_incomplete_and_fallback_provenance_are_blocked():
    incomplete = _request(provenance=Provenance("ds", "obj", "dandi", "dandi://obj"))
    assert read_bounded_window(FakeSource(), incomplete).state is IngestionState.BLOCKED
    fallback = _request(provenance=_provenance(source_kind="filesystem_fallback", validated_dandi_nwb=True, synthetic=False))
    result = read_bounded_window(FakeSource(), fallback)
    assert result.state is IngestionState.BLOCKED
    assert "fallback" in result.error


def test_full_recording_materialization_is_rejected():
    with pytest.raises(IngestionContractError):
        reject_full_recording_materialization()


def test_remote_compatibility_paths_require_explicit_network_permission():
    with pytest.raises(IngestionContractError):
        open_nwb_lazy("https://example.invalid/object")
    with pytest.raises(IngestionContractError):
        resolve_asset_blobs("000000", "draft")


def test_local_file_source_is_bounded(tmp_path):
    path = tmp_path / "fixture.bin"
    path.write_bytes(b"0123456789")
    source = LocalFileWindowSource(path)
    result = read_bounded_window(source, _request(size=3, stop=3, expected_size=3, checksum_policy="none"))
    assert result.state is IngestionState.COMPLETE
    assert result.data == b"012"
    assert source.closed == 1


def test_result_is_finite_json():
    result = read_bounded_window(FakeSource(), _request())
    encoded = json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)
    assert "NaN" not in encoded and "Infinity" not in encoded
