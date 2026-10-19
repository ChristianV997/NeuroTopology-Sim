"""Ranged vs fail-closed behaviour for sync_s3_subject (mocked S3, no network)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.streaming import base_runner
from tests.performance.streaming_optimization.conftest import (
    FakePaginator,
    FakeS3Client,
    ranged_body,
)

_VHDR = """\
Brain Vision Data Exchange Header File Version 1.0
[Common Infos]
DataFile=sub-01_task-awake_eeg.eeg
MarkerFile=sub-01_task-awake_eeg.vmrk
DataFormat=BINARY
NumberOfChannels=2
SamplingInterval=1000
BinaryFormat=IEEE_FLOAT_32
"""
# 1 s * 1e6 us / 1000 us * 2 channels * 4 bytes = 8000
_REQUIRED_EEG_BYTES = 8000
_EEG_OBJECT_SIZE = 80_000
_VHDR_BYTES = _VHDR.encode("utf-8")
_EEG_BYTES = b"E" * _EEG_OBJECT_SIZE


def _contents(*objects: dict) -> list[dict]:
    return [{"Contents": list(objects)}]


def test_ranged_eeg_reuses_prefix_and_promotes_atomic_part(
    tmp_path, fake_s3_modules
):
    subject = "sub-01"
    vhdr_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.vhdr"
    eeg_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.eeg"
    dest_root = tmp_path / "work"
    eeg_target = dest_root / subject / "eeg" / "sub-01_task-awake_eeg.eeg"
    eeg_target.parent.mkdir(parents=True, exist_ok=True)
    stale = eeg_target.with_name(eeg_target.name + ".part")
    stale.write_bytes(b"NO")
    payloads = {vhdr_key: _VHDR_BYTES, eeg_key: _EEG_BYTES}

    def get_object_impl(**kwargs):
        return ranged_body(payloads[kwargs["Key"]], kwargs["Range"])

    def handler(kwargs):
        return _contents(
            {"Key": vhdr_key, "Size": len(_VHDR_BYTES)},
            {"Key": eeg_key, "Size": _EEG_OBJECT_SIZE},
        )

    client = FakeS3Client(FakePaginator(handler), get_object_impl=get_object_impl)
    fake_s3_modules["client"] = client
    base_runner.sync_s3_subject(
        "openneuro.org",
        "dsX",
        subject,
        dest_root,
        required_duration_seconds=1.0,
    )
    assert eeg_target.read_bytes() == _EEG_BYTES[:_REQUIRED_EEG_BYTES]
    assert not stale.exists()
    assert client.download_calls == []

    client.get_object_calls.clear()
    base_runner.sync_s3_subject(
        "openneuro.org",
        "dsX",
        subject,
        dest_root,
        required_duration_seconds=1.0,
    )
    assert client.get_object_calls == []
    assert client.download_calls == []
    tree = ast.parse(Path(base_runner.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"download_file", "download_fileobj"}
    ]
    assert calls == []


def test_eeg_uses_ranged_get_object_when_required_bytes_below_size(
    tmp_path, fake_s3_modules
):
    subject = "sub-01"
    vhdr_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.vhdr"
    eeg_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.eeg"
    payloads = {vhdr_key: _VHDR_BYTES, eeg_key: _EEG_BYTES}

    def get_object_impl(**kwargs):
        return ranged_body(payloads[kwargs["Key"]], kwargs["Range"])

    def handler(kwargs):
        return _contents(
            {"Key": vhdr_key, "Size": len(_VHDR_BYTES)},
            {"Key": eeg_key, "Size": _EEG_OBJECT_SIZE},
        )

    client = FakeS3Client(FakePaginator(handler), get_object_impl=get_object_impl)
    fake_s3_modules["client"] = client
    dest = base_runner.sync_s3_subject(
        "openneuro.org",
        "dsX",
        subject,
        tmp_path,
        required_duration_seconds=1.0,
    )
    eeg_path = dest / "eeg" / "sub-01_task-awake_eeg.eeg"
    assert eeg_path.read_bytes() == _EEG_BYTES[:_REQUIRED_EEG_BYTES]
    assert not eeg_path.with_name(eeg_path.name + ".part").exists()
    assert client.download_calls == []
    eeg_gets = [c for c in client.get_object_calls if c["Key"] == eeg_key]
    assert len(eeg_gets) == 1
    assert eeg_gets[0]["Range"] == f"bytes=0-{_REQUIRED_EEG_BYTES - 1}"


def test_eeg_fail_closed_without_computable_range_never_calls_download_file(
    tmp_path, fake_s3_modules
):
    subject = "sub-01"
    eeg_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.eeg"

    def get_object_impl(**kwargs):
        raise AssertionError("EEG without a range must not materialize bytes")

    def handler(kwargs):
        return _contents({"Key": eeg_key, "Size": _EEG_OBJECT_SIZE})

    client = FakeS3Client(FakePaginator(handler), get_object_impl=get_object_impl)
    fake_s3_modules["client"] = client
    with pytest.raises(ValueError, match="fail-closed"):
        base_runner.sync_s3_subject("openneuro.org", "dsX", subject, tmp_path)
    assert client.download_calls == []
    assert client.get_object_calls == []
    assert not (tmp_path / subject / "eeg" / "sub-01_task-awake_eeg.eeg").exists()


def test_eeg_fail_closed_when_required_bytes_covers_full_object(
    tmp_path, fake_s3_modules
):
    subject = "sub-01"
    vhdr_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.vhdr"
    eeg_key = f"dsX/{subject}/eeg/sub-01_task-awake_eeg.eeg"
    payloads = {vhdr_key: _VHDR_BYTES}

    def get_object_impl(**kwargs):
        assert kwargs["Key"] == vhdr_key
        return ranged_body(payloads[kwargs["Key"]], kwargs["Range"])

    def handler(kwargs):
        return _contents(
            {"Key": vhdr_key, "Size": len(_VHDR_BYTES)},
            {"Key": eeg_key, "Size": _REQUIRED_EEG_BYTES},
        )

    client = FakeS3Client(FakePaginator(handler), get_object_impl=get_object_impl)
    fake_s3_modules["client"] = client
    with pytest.raises(ValueError, match="fail-closed"):
        base_runner.sync_s3_subject(
            "openneuro.org",
            "dsX",
            subject,
            tmp_path,
            required_duration_seconds=1.0,
        )
    assert client.download_calls == []
    assert [c["Key"] for c in client.get_object_calls] == [vhdr_key]
    assert not (tmp_path / subject / "eeg" / "sub-01_task-awake_eeg.eeg").exists()


def test_metadata_over_cap_fail_closed_before_get_object(tmp_path, fake_s3_modules):
    subject = "sub-01"
    key = f"dsX/{subject}/too_big.json"

    def get_object_impl(**kwargs):
        raise AssertionError("over-cap metadata must not be materialized")

    def handler(kwargs):
        return _contents({"Key": key, "Size": base_runner.S3_METADATA_MAX_BYTES + 1})

    client = FakeS3Client(FakePaginator(handler), get_object_impl=get_object_impl)
    fake_s3_modules["client"] = client
    with pytest.raises(ValueError, match="byte cap"):
        base_runner.sync_s3_subject("openneuro.org", "dsX", subject, tmp_path)
    assert client.download_calls == []
    assert client.get_object_calls == []
