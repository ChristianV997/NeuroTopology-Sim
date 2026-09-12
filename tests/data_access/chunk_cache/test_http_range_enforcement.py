from __future__ import annotations

import hashlib
from unittest.mock import patch

from tools.data_access.chunk_cache import ChunkRange
from tools.data_access.chunk_cache.transfer import HTTPTransferAdapter


class _Response:
    def __init__(self, body: bytes, *, status: int, content_range: str, content_length: int | None = None):
        self._body = body
        self._offset = 0
        self.status = status
        self.headers = {
            "Content-Range": content_range,
            **({"Content-Length": str(content_length)} if content_length is not None else {}),
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        block = self._body[self._offset : self._offset + size]
        self._offset += len(block)
        return block


def test_http_adapter_rejects_server_that_ignores_range(tmp_path):
    response = _Response(b"0123456789", status=200, content_range="bytes 0-9/10", content_length=10)
    target = tmp_path / "chunk.bin"
    with patch("urllib.request.urlopen", return_value=response):
        result = HTTPTransferAdapter().transfer_chunk(
            "https://example.invalid/object",
            target,
            ChunkRange(2, 5, total_file_size=10),
            allow_network=True,
        )

    assert result.success is False
    assert "did not honor" in result.error_message
    assert not target.exists()


def test_http_adapter_rejects_mismatched_content_range(tmp_path):
    response = _Response(b"2345", status=206, content_range="bytes 0-3/10", content_length=4)
    target = tmp_path / "chunk.bin"
    with patch("urllib.request.urlopen", return_value=response):
        result = HTTPTransferAdapter().transfer_chunk(
            "https://example.invalid/object",
            target,
            ChunkRange(2, 5, total_file_size=10),
            allow_network=True,
        )

    assert result.success is False
    assert "different from the requested" in result.error_message
    assert not target.exists()


def test_http_adapter_copies_only_confirmed_range(tmp_path):
    content = b"2345"
    response = _Response(content, status=206, content_range="bytes 2-5/10", content_length=len(content))
    target = tmp_path / "chunk.bin"
    with patch("urllib.request.urlopen", return_value=response):
        result = HTTPTransferAdapter().transfer_chunk(
            "https://example.invalid/object",
            target,
            ChunkRange(2, 5, total_file_size=10),
            expected_checksum=hashlib.sha256(content).hexdigest(),
            allow_network=True,
        )

    assert result.success is True
    assert target.read_bytes() == content
    assert result.bytes_transferred == len(content)
