"""Shared helpers for streaming/BIDS ingest optimization tests.

Synthetic local fixtures only. No network. No API keys.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import types
from pathlib import Path

import pytest

_HAVE_MNE = all(importlib.util.find_spec(name) for name in ("mne", "mne_bids", "edfio"))
requires_mne = pytest.mark.skipif(not _HAVE_MNE, reason="requires mne, mne-bids, edfio")


@pytest.fixture
def fake_s3_modules(monkeypatch):
    """Install in-process boto3/botocore stubs so S3 helpers never touch the network."""

    class Config:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class TransferConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    botocore = types.ModuleType("botocore")
    botocore.UNSIGNED = "UNSIGNED"
    cfg = types.ModuleType("botocore.config")
    cfg.Config = Config
    boto3 = types.ModuleType("boto3")
    s3pkg = types.ModuleType("boto3.s3")
    xfer = types.ModuleType("boto3.s3.transfer")
    xfer.TransferConfig = TransferConfig

    holder = {"client": None}

    def client(*args, **kwargs):
        if holder["client"] is None:
            raise RuntimeError("fake S3 client not installed")
        return holder["client"]

    boto3.client = client

    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", cfg)
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setitem(sys.modules, "boto3.s3", s3pkg)
    monkeypatch.setitem(sys.modules, "boto3.s3.transfer", xfer)
    return holder


class FakePaginator:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def paginate(self, **kwargs):
        self.calls.append(dict(kwargs))
        pages = self.handler(kwargs)
        return iter(pages)


class FakeS3Client:
    def __init__(self, paginator: FakePaginator, download_impl=None, get_object_impl=None):
        self.paginator = paginator
        self.download_impl = download_impl
        self.get_object_impl = get_object_impl
        self.download_calls: list[tuple] = []
        self.get_object_calls: list[dict] = []

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return self.paginator

    def download_file(self, bucket, key, filename, Config=None):
        self.download_calls.append((bucket, key, filename))
        if self.download_impl is None:
            raise AssertionError("download_file must not be used for subject sync")
        self.download_impl(bucket, key, filename, Config)

    def get_object(self, **kwargs):
        self.get_object_calls.append(dict(kwargs))
        if self.get_object_impl is None:
            raise AssertionError("get_object not configured")
        return self.get_object_impl(**kwargs)


def ranged_body(payload: bytes, range_header: str) -> dict:
    """Return a mocked S3 get_object body for an inclusive bytes= Range."""
    start_s, end_s = range_header.removeprefix("bytes=").split("-", 1)
    start, end = int(start_s), int(end_s)
    return {"Body": io.BytesIO(payload[start : end + 1])}
