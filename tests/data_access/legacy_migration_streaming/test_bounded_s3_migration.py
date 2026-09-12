"""Contract tests for non-OpenNeuro bounded streaming migration."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from validation.fast_tr_fixtures import fetch_hcp_ya_subject, fetch_nki_rs_subject
from validation.s3_fetchers import (
    BoundedAccessError,
    BoundedS3ObjectStore,
    ChecksumMismatchError,
)


class FakeS3:
    def __init__(self, objects: dict[tuple[str, str], bytes], *, checksums: bool = True) -> None:
        self.objects = objects
        self.checksums = checksums
        self.calls: list[tuple[str, str, str | None]] = []
        self.failures = 0
        self.permanent_failure_on_call: int | None = None

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        self.calls.append(("head", Bucket, Key))
        data = self.objects[(Bucket, Key)]
        result = {"ContentLength": len(data)}
        if self.checksums:
            result["ETag"] = hashlib.sha256(data).hexdigest()
        return result

    def get_object(self, *, Bucket: str, Key: str, Range: str) -> dict:
        self.calls.append(("range", Bucket, Range))
        call_number = sum(1 for call in self.calls if call[0] == "range")
        if self.failures:
            self.failures -= 1
            raise TimeoutError("fixture timeout")
        if self.permanent_failure_on_call == call_number:
            raise ValueError("fixture transfer failure")
        start, end = (int(value) for value in Range.removeprefix("bytes=").split("-"))
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)][start : end + 1])}


def test_network_is_fail_closed_and_no_s3_call_is_made(tmp_path: Path):
    client = FakeS3({("bucket", "file"): b"data"})
    store = BoundedS3ObjectStore(client, tmp_path, chunk_size=2)
    with pytest.raises(PermissionError):
        store.fetch_object("bucket", "file", tmp_path / "file", allow_network=False)
    assert client.calls == []


def test_transfer_is_manifest_first_bounded_and_checksum_verified(tmp_path: Path):
    content = b"abcdefghij"
    client = FakeS3({("bucket", "file"): content})
    store = BoundedS3ObjectStore(client, tmp_path, chunk_size=4)
    result = store.fetch_object("bucket", "file", tmp_path / "file", allow_network=True)
    assert Path(result.destination).read_bytes() == content
    assert result.checksum_status == "verified"
    assert [call[2] for call in client.calls if call[0] == "range"] == ["bytes=0-3", "bytes=4-7", "bytes=8-9"]
    assert not (tmp_path / "file.part").exists()
    manifest = json.loads((tmp_path / ".bounded_s3_manifest.json").read_text())
    assert manifest["records"]
    json.dumps(result.to_dict(), allow_nan=False)
    json.loads(result.to_json())


def test_checksum_mismatch_never_promotes_artifact(tmp_path: Path):
    client = FakeS3({("bucket", "file"): b"correct"})
    store = BoundedS3ObjectStore(client, tmp_path, chunk_size=3)
    with pytest.raises(ChecksumMismatchError):
        store.fetch_object("bucket", "file", tmp_path / "file", allow_network=True, expected_checksum="0" * 64)
    assert not (tmp_path / "file").exists()
    state = json.loads((tmp_path / "file.part.json").read_text())
    assert state["status"] == "corrupted"


def test_transient_retry_is_bounded(tmp_path: Path):
    client = FakeS3({("bucket", "file"): b"abcdef"})
    client.failures = 2
    store = BoundedS3ObjectStore(client, tmp_path, chunk_size=6, max_retries=3)
    result = store.fetch_object("bucket", "file", tmp_path / "file", allow_network=True)
    assert result.attempts == 3
    assert (tmp_path / "file").read_bytes() == b"abcdef"


def test_timeout_failure_preserves_resumable_partial_state(tmp_path: Path):
    client = FakeS3({("bucket", "file"): b"abcdefgh"})
    client.permanent_failure_on_call = 2
    store = BoundedS3ObjectStore(client, tmp_path, chunk_size=4, max_retries=1)
    with pytest.raises(BoundedAccessError):
        store.fetch_object("bucket", "file", tmp_path / "file", allow_network=True)
    assert not (tmp_path / "file").exists()
    assert (tmp_path / "file.part").exists()
    client.permanent_failure_on_call = None
    result = store.fetch_object("bucket", "file", tmp_path / "file", allow_network=True)
    assert (tmp_path / "file").read_bytes() == b"abcdefgh"
    assert result.completed_chunks == 2
    ranges = [call[2] for call in client.calls if call[0] == "range"]
    assert ranges.count("bytes=0-3") == 1


def test_unknown_size_is_rejected(tmp_path: Path):
    class UnknownSize(FakeS3):
        def head_object(self, **kwargs):
            self.calls.append(("head", kwargs["Bucket"], kwargs["Key"]))
            return {}

    with pytest.raises(BoundedAccessError, match="size is unknown"):
        BoundedS3ObjectStore(UnknownSize({("bucket", "file"): b"x"}), tmp_path).fetch_object(
            "bucket", "file", tmp_path / "file", allow_network=True
        )


def test_cache_budget_and_eviction_are_explicit(tmp_path: Path):
    client = FakeS3({("bucket", "a"): b"1234", ("bucket", "b"): b"5678"})
    store = BoundedS3ObjectStore(client, tmp_path, chunk_size=4, max_cache_bytes=4)
    store.fetch_object("bucket", "a", tmp_path / "a", allow_network=True)
    store.fetch_object("bucket", "b", tmp_path / "b", allow_network=True)
    assert not (tmp_path / "a").exists()
    assert (tmp_path / "b").read_bytes() == b"5678"

    too_small = BoundedS3ObjectStore(client, tmp_path / "small", max_cache_bytes=3)
    with pytest.raises(BoundedAccessError, match="exceeds cache budget"):
        too_small.fetch_object("bucket", "b", tmp_path / "small" / "b", allow_network=True)


def test_path_containment_is_enforced(tmp_path: Path):
    client = FakeS3({("bucket", "file"): b"x"})
    with pytest.raises(BoundedAccessError, match="escapes"):
        BoundedS3ObjectStore(client, tmp_path).fetch_object("bucket", "file", tmp_path / ".." / "outside", allow_network=True)


def test_fast_tr_helpers_are_plan_only_and_network_disabled_by_default():
    hcp = fetch_hcp_ya_subject("100206")
    nki = fetch_nki_rs_subject("A00008326")
    for plan in (hcp, nki):
        assert plan["status"] == "PLAN_ONLY_BOUNDED_ADAPTER_REQUIRED"
        assert plan["network_enabled"] is False
        assert plan["acquisition_policy"]["manifest_first"] is True
        assert plan["acquisition_policy"]["checksum_missing_is_unknown"] is True


def test_streaming_entrypoints_fail_closed_before_remote_metadata(monkeypatch, tmp_path: Path):
    import tools.stream_process_ds005917 as ds005917
    import tools.stream_process_ds006644 as ds006644

    class NoNetworkClient:
        def head_object(self, **kwargs):
            raise AssertionError("offline path must reject before head_object")

    monkeypatch.setattr(ds005917, "_s3_client", lambda: NoNetworkClient())
    monkeypatch.setattr(ds006644, "_s3_client", lambda: NoNetworkClient())
    with pytest.raises(PermissionError):
        ds005917.download_bold("sub-01", "ses-d2", tmp_path / "ds005917")
    with pytest.raises(PermissionError):
        ds006644.download_subject_bold("sub-01", tmp_path / "ds006644")
