"""Offline test for tools/fetch_ds000245.py's skip-if-already-downloaded logic.

Network access itself is not tested here (that would require live S3); this
covers the one piece of decision logic worth protecting: a file already present
at the correct size must not be re-downloaded.
"""
from __future__ import annotations

from pathlib import Path

from tools.fetch_ds000245 import fetch


class _FakePaginator:
    def __init__(self, keys_and_sizes: list[tuple[str, int]]) -> None:
        self._items = keys_and_sizes

    def paginate(self, **_kwargs):
        yield {"Contents": [{"Key": k, "Size": s} for k, s in self._items]}


class _FakeClient:
    def __init__(self, keys_and_sizes: list[tuple[str, int]]) -> None:
        self._items = keys_and_sizes
        self.download_calls: list[str] = []

    def get_paginator(self, _name: str) -> _FakePaginator:
        return _FakePaginator(self._items)

    def download_file(self, _bucket: str, key: str, dest: str) -> None:
        self.download_calls.append(key)
        size = dict(self._items)[key]
        Path(dest).write_bytes(b"\0" * size)


def test_fetch_skips_already_present_file_with_matching_size(tmp_path, monkeypatch):
    import tools.fetch_ds000245 as mod

    key = "ds000245/sub-CTL01/func/sub-CTL01_task-rest_bold.nii.gz"
    rel = "sub-CTL01/func/sub-CTL01_task-rest_bold.nii.gz"
    size = 128
    existing = tmp_path / rel
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"\0" * size)

    client = _FakeClient([(key, size)])
    monkeypatch.setattr(mod, "_s3_client", lambda: client)

    result = fetch(tmp_path)
    assert result["skipped"] == [key]
    assert result["downloaded"] == []
    assert client.download_calls == []


def test_fetch_downloads_missing_file(tmp_path, monkeypatch):
    import tools.fetch_ds000245 as mod

    key = "ds000245/sub-CTL02/func/sub-CTL02_task-rest_bold.nii.gz"
    client = _FakeClient([(key, 256)])
    monkeypatch.setattr(mod, "_s3_client", lambda: client)

    result = fetch(tmp_path)
    assert result["downloaded"] == [key]
    assert client.download_calls == [key]
    assert (tmp_path / "sub-CTL02/func/sub-CTL02_task-rest_bold.nii.gz").stat().st_size == 256


def test_fetch_respects_limit(tmp_path, monkeypatch):
    import tools.fetch_ds000245 as mod

    items = [(f"ds000245/sub-CTL{i:02d}/func/sub-CTL{i:02d}_task-rest_bold.nii.gz", 64) for i in range(1, 6)]
    client = _FakeClient(items)
    monkeypatch.setattr(mod, "_s3_client", lambda: client)

    result = fetch(tmp_path, limit=2)
    assert len(result["downloaded"]) == 2
